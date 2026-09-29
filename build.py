from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "pwr_tch_matcher_entry.py"
DIST = ROOT / "dist"

TARGETS = {
    "windows-x64": ("pwr-tch-matcher-win-x64.exe", True),
    "linux-x64": ("pwr-tch-matcher-linux-x64", False),
    "linux-arm64": ("pwr-tch-matcher-linux-arm64", False),
    "macos-x64": ("pwr-tch-matcher-macos-x64", False),
    "macos-arm64": ("pwr-tch-matcher-macos-arm64", False),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local PWR/TCH Matcher binary with Nuitka")
    parser.add_argument("--target", choices=sorted(TARGETS), default=None)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.clean:
        shutil.rmtree(DIST, ignore_errors=True)

    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()
    detected = (
        "windows-x64" if system == "windows" else
        "macos-arm64" if system == "darwin" and machine in {"arm64", "aarch64"} else
        "macos-x64" if system == "darwin" else
        "linux-arm64" if machine in {"arm64", "aarch64"} else
        "linux-x64"
    )

    target = args.target or detected
    if target != detected:
        raise SystemExit(
            f"Local build target {target!r} does not match this host ({detected!r}). "
            "Use GitHub Actions for cross-platform builds."
        )

    output_name, is_windows = TARGETS[target]
    DIST.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=onefile",
        "--enable-plugin=pyside6",
        "--assume-yes-for-downloads",
        "--follow-imports",
        "--include-package=pwrtchmatcher",
        "--include-package=polars",
        f"--output-dir={DIST}",
        f"--output-filename={output_name}",
    ]
    if is_windows:
        cmd.append("--windows-console-mode=disable")
    cmd.append(str(ENTRY))

    print("Building:", target)
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("Output:", DIST / output_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
