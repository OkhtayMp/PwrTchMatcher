from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: make_checksums.py TARGET RELEASE_DIR", file=sys.stderr)
        return 2

    target = sys.argv[1]
    release_dir = Path(sys.argv[2])
    files = sorted(
        p for p in release_dir.iterdir()
        if p.is_file()
        and p.name.startswith("pwr-tch-matcher")
        and f"-{target}" in p.name
        and not p.name.startswith("SHA256SUMS-")
    )
    if not files:
        raise RuntimeError(f"No release binaries found for {target}")

    output = release_dir / f"SHA256SUMS-{target}.txt"
    with output.open("w", encoding="utf-8") as handle:
        for path in files:
            handle.write(f"{sha256(path)}  {path.name}\n")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
