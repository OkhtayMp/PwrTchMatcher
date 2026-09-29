from __future__ import annotations

from pwrtchmatcher.core import guess_column, normalize_name, validate_mapping


def test_normalize_name() -> None:
    assert normalize_name(" Fault_First_Occur_Time ") == "fault first occur time"


def test_guess_column_exact_then_partial() -> None:
    columns = ["Site Name", "First Occurred On", "Cleared On"]
    assert guess_column(columns, ("Site",)) == "Site Name"
    assert guess_column(columns, ("First Occurred",)) == "First Occurred On"


def test_validate_mapping() -> None:
    assert (
        validate_mapping({"site": "A", "start": "B", "end": "C"}, ("site", "start", "end")) is None
    )
    assert validate_mapping({"site": "A", "start": "A", "end": "C"}, ("site", "start", "end"))
