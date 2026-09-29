from __future__ import annotations

import csv
from pathlib import Path

from pwrtchmatcher.constants import CREATE_COLUMN
from pwrtchmatcher.matcher import process_files


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)


def test_process_files_exact_window_and_original_order(tmp_path: Path) -> None:
    pwr = tmp_path / "Power.csv"
    tch = tmp_path / "TCH.csv"
    out = tmp_path / "matched.csv"

    write_csv(
        pwr,
        [
            ["Site Name", "First Occurred On", "Cleared On"],
            ["A", "9/10/2026 10:00", "9/10/2026 11:00"],
            ["A", "9/10/2026 20:00", "9/10/2026 21:00"],
            ["B", "9/10/2026 09:00", "9/10/2026 09:30"],
        ],
    )
    write_csv(
        tch,
        [
            ["Zone", "Fault First Occur Time", "Ticket ID"],
            ["A", "9/10/2026 10:00", "TT-1"],
            ["A", "9/10/2026 20:30", "TT-2"],
            ["B", "9/10/2026 10:00", "TT-3"],
        ],
    )

    result = process_files(
        pwr,
        {"site": "Site Name", "start": "First Occurred On", "end": "Cleared On"},
        ",",
        tch,
        {
            "site": "Zone",
            "fault_time": "Fault First Occur Time",
            "ticket": "Ticket ID",
            "target": CREATE_COLUMN,
        },
        ",",
        out,
    )

    assert result["matches"] == 2
    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["power TT"] for row in rows] == ["TT-1", "TT-2", ""]
