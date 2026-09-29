from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import polars as pl

from .constants import CREATE_COLUMN, INTERNAL
from .core import has_utf8_bom, parse_datetime_expr, read_csv_header, safe_unlink


def process_files(
    pwr_path: Path,
    pwr_mapping: dict[str, str | None],
    pwr_separator: str,
    tch_path: Path,
    tch_mapping: dict[str, str | None],
    tch_separator: str,
    output_path: Path,
    *,
    progress: Callable[[int, str], None] = lambda _value, _text: None,
) -> dict[str, object]:
    started = time.perf_counter()

    if pwr_path.resolve() == tch_path.resolve():
        raise ValueError("PWR and TCH must be different files.")

    p_site = str(pwr_mapping["site"])
    p_start = str(pwr_mapping["start"])
    p_end = str(pwr_mapping["end"])

    t_site = str(tch_mapping["site"])
    t_fault = str(tch_mapping["fault_time"])
    t_ticket = str(tch_mapping["ticket"])

    target = str(tch_mapping["target"])
    target_name = "power TT" if target == CREATE_COLUMN else target

    if target_name in {t_site, t_fault, t_ticket}:
        raise ValueError("The result column must be different from the TCH input columns.")

    if not pwr_path.is_file() or not tch_path.is_file():
        raise FileNotFoundError("One of the selected CSV files no longer exists.")

    # Re-read only the headers before a long operation. This catches a file
    # being replaced/edited after the user made the column selections.
    pwr_columns, pwr_separator_now = read_csv_header(pwr_path)
    tch_columns, tch_separator_now = read_csv_header(tch_path)

    if any(name not in pwr_columns for name in (p_site, p_start, p_end)):
        raise ValueError("A selected PWR column no longer exists in the file.")
    if any(name not in tch_columns for name in (t_site, t_fault, t_ticket)):
        raise ValueError("A selected TCH column no longer exists in the file.")
    if target != CREATE_COLUMN and target_name not in tch_columns:
        raise ValueError("The selected TCH result column no longer exists in the file.")

    # Use the current separators, not stale values from the earlier preview.
    pwr_separator = pwr_separator_now
    tch_separator = tch_separator_now

    # Read only the three PWR columns needed for matching. This avoids loading
    # unrelated columns from a large PWR file.
    progress(8, "Reading PWR…")
    pwr = pl.read_csv(
        pwr_path,
        separator=pwr_separator,
        columns=[p_site, p_start, p_end],
        infer_schema=False,
        encoding="utf8-lossy",
        low_memory=False,
        row_index_name=INTERNAL["pwr_row"],
    )

    pwr = (
        pwr.with_columns(
            [
                pl.col(p_site).cast(pl.String).str.strip_chars().alias(INTERNAL["pwr_site"]),
                parse_datetime_expr(p_start).alias("__pwr_start_dt"),
                parse_datetime_expr(p_end).alias("__pwr_end_dt"),
            ]
        )
        .with_columns(
            [
                pl.min_horizontal("__pwr_start_dt", "__pwr_end_dt").alias(INTERNAL["pwr_from"]),
                pl.max_horizontal("__pwr_start_dt", "__pwr_end_dt").alias(INTERNAL["pwr_to"]),
            ]
        )
        .select(
            [
                INTERNAL["pwr_row"],
                INTERNAL["pwr_site"],
                INTERNAL["pwr_from"],
                INTERNAL["pwr_to"],
            ]
        )
        .filter(
            pl.col(INTERNAL["pwr_site"]).is_not_null()
            & (pl.col(INTERNAL["pwr_site"]).str.len_chars() > 0)
            & pl.col(INTERNAL["pwr_from"]).is_not_null()
            & pl.col(INTERNAL["pwr_to"]).is_not_null()
        )
    )

    if pwr.height == 0:
        raise ValueError("No valid PWR rows remain after reading site and time columns.")

    progress(24, "Reading TCH…")
    tch = pl.read_csv(
        tch_path,
        separator=tch_separator,
        infer_schema=False,
        encoding="utf8-lossy",
        low_memory=False,
        row_index_name=INTERNAL["tch_row"],
    )

    if target == CREATE_COLUMN:
        if target_name in tch.columns:
            raise ValueError(f"Column '{target_name}' already exists.")
        tch = tch.with_columns(pl.lit(None, dtype=pl.String).alias(target_name))

    # Build only the small TCH side needed for matching.
    tch_key = tch.select(
        [
            INTERNAL["tch_row"],
            pl.col(t_site).cast(pl.String).str.strip_chars().alias(INTERNAL["tch_site"]),
            parse_datetime_expr(t_fault).alias(INTERNAL["tch_fault"]),
            pl.col(t_ticket).cast(pl.String).alias(INTERNAL["tch_ticket"]),
        ]
    ).filter(
        pl.col(INTERNAL["tch_site"]).is_not_null()
        & (pl.col(INTERNAL["tch_site"]).str.len_chars() > 0)
        & pl.col(INTERNAL["tch_fault"]).is_not_null()
        & pl.col(INTERNAL["tch_ticket"]).is_not_null()
        & (pl.col(INTERNAL["tch_ticket"]).str.strip_chars().str.len_chars() > 0)
    )

    valid_tch = tch_key.height
    if valid_tch == 0:
        raise ValueError("No valid TCH rows remain after reading site, fault time and Ticket ID.")

    progress(55, "Matching site and time windows…")

    # join_where is used on materialized DataFrames, not inside sink_csv.
    # This avoids depending on a streaming path for the experimental/partial-
    # streaming non-equi join implementation.
    matches = (
        tch_key.join_where(
            pwr,
            pl.col(INTERNAL["tch_site"]) == pl.col(INTERNAL["pwr_site"]),
            pl.col(INTERNAL["tch_fault"]) >= pl.col(INTERNAL["pwr_from"]),
            pl.col(INTERNAL["tch_fault"]) <= pl.col(INTERNAL["pwr_to"]),
        )
        .group_by(INTERNAL["tch_row"])
        .agg(
            pl.col(INTERNAL["tch_ticket"])
            .sort_by(INTERNAL["pwr_row"])
            .first()
            .alias(INTERNAL["match_ticket"])
        )
    )

    match_count = matches.height
    progress(76, f"Found {match_count:,} matches…")

    # Attach the single chosen ticket to the full TCH table.
    joined = tch.join(matches, on=INTERNAL["tch_row"], how="left")

    if target == CREATE_COLUMN:
        joined = joined.with_columns(pl.col(INTERNAL["match_ticket"]).alias(target_name))
    else:
        joined = joined.with_columns(
            pl.coalesce(
                [
                    pl.col(INTERNAL["match_ticket"]),
                    pl.col(target_name).cast(pl.String),
                ]
            ).alias(target_name)
        )

    # The internal TCH site/fault/ticket columns live only in `tch_key`;
    # they are not present in `joined`. Drop only columns that actually exist
    # in the final TCH frame.
    result = joined.sort(INTERNAL["tch_row"]).drop(
        [
            INTERNAL["tch_row"],
            INTERNAL["match_ticket"],
        ]
    )

    progress(91, "Writing result…")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".write-part")
    safe_unlink(temp_path)

    try:
        result.write_csv(
            temp_path,
            separator=tch_separator,
            include_bom=has_utf8_bom(tch_path),
        )
        temp_path.replace(output_path)
    except Exception:
        safe_unlink(temp_path)
        raise

    elapsed = time.perf_counter() - started
    progress(100, "Complete")

    return {
        "output": str(output_path),
        "matches": match_count,
        "elapsed": elapsed,
        "tch_rows": tch.height,
        "valid_tch_rows": valid_tch,
        "separator": tch_separator,
        "result_column": target_name,
    }


# -----------------------------------------------------------------------------
# Main window
# -----------------------------------------------------------------------------
