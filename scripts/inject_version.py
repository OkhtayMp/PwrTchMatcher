from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: inject_version.py VERSION", file=sys.stderr)
        return 2

    version = sys.argv[1].strip().lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(f"invalid version: {version}", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]

    (root / "VERSION").write_text(f"v{version}\n", encoding="utf-8")
    (root / "pwrtchmatcher" / "version.py").write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )

    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]+"\s*$',
        f'version = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not find project version in pyproject.toml")
    pyproject.write_text(updated, encoding="utf-8")

    print(f"Injected version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
