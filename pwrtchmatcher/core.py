from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from .constants import DATE_FORMATS, INTERNAL

def normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def detect_separator(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(128 * 1024)

    if not sample.strip():
        raise ValueError("The CSV file is empty.")

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        if dialect.delimiter in {",", ";", "\t", "|"}:
            return dialect.delimiter
    except csv.Error:
        pass

    best = ","
    best_width = 1
    for delimiter in (",", ";", "\t", "|"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.reader(handle, delimiter=delimiter), [])
            if len(row) > best_width:
                best = delimiter
                best_width = len(row)
        except (OSError, csv.Error, UnicodeError):
            pass
    return best


def read_csv_header(path: Path) -> tuple[list[str], str]:
    """Read only the CSV header and return its columns and separator."""
    separator = detect_separator(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle, delimiter=separator), [])

    columns = [str(value).strip() for value in header]
    if not columns:
        raise ValueError("The CSV has no header row.")
    if any(not column for column in columns):
        raise ValueError("The CSV contains an empty column name.")

    seen: set[str] = set()
    duplicates: list[str] = []
    for column in columns:
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    if duplicates:
        raise ValueError("Duplicate column names: " + ", ".join(duplicates[:6]))

    return columns, separator


def guess_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {normalize_name(column): column for column in columns}

    for candidate in candidates:
        match = normalized.get(normalize_name(candidate))
        if match is not None:
            return match

    for candidate in candidates:
        needle = normalize_name(candidate)
        for normalized_column, original in normalized.items():
            if needle in normalized_column:
                return original
    return None


def validate_mapping(mapping: dict[str, str | None], required: tuple[str, ...]) -> str | None:
    values = [mapping.get(key) for key in required]
    if any(not value for value in values):
        return "Choose all required columns."
    if len(values) != len(set(values)):
        return "Each field must use a different column."
    return None


def parse_datetime_expr(column_name: str) -> pl.Expr:
    value = pl.col(column_name).cast(pl.String).str.strip_chars()
    return pl.coalesce(
        [value.str.strptime(pl.Datetime, fmt, strict=False) for fmt in DATE_FORMATS]
    )


def has_utf8_bom(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(3) == b"\xef\xbb\xbf"


def safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# -----------------------------------------------------------------------------
# Worker
# -----------------------------------------------------------------------------

