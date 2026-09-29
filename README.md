# PWR / TCH Matcher

A small cross-platform PySide6 desktop application for matching PWR time windows against TCH fault timestamps and writing the matched ticket into a TCH result column.

## Downloads

Release builds are published automatically for the same five target families used by the BambooPass release layout: Windows x64, Linux x64, Linux ARM64, macOS Intel, and macOS ARM64.

| Platform | Download | SHA256 |
| --- | --- | --- |
| Windows x64 | [Download](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/pwr-tch-matcher-win-x64.exe) | [SHA256](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/SHA256SUMS-win-x64.txt) |
| Linux x64 | [Download](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/pwr-tch-matcher-linux-x64) | [SHA256](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/SHA256SUMS-linux-x64.txt) |
| Linux ARM64 | [Download](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/pwr-tch-matcher-linux-arm64) | [SHA256](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/SHA256SUMS-linux-arm64.txt) |
| macOS Intel | [Download](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/pwr-tch-matcher-macos-x64) | [SHA256](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/SHA256SUMS-macos-x64.txt) |
| macOS ARM64 | [Download](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/pwr-tch-matcher-macos-arm64) | [SHA256](https://github.com/OkhtayMp/pwr-tch-matcher/releases/latest/download/SHA256SUMS-macos-arm64.txt) |

All release binaries are intended to be standalone one-file executables; no Python installation is required on the target machine.

## Development

```bash
python -m venv .venv
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check pwrtchmatcher tests pwr_tch_matcher_entry.py
python pwr_tch_matcher_entry.py
```

## Local binary build

```bash
python -m pip install -r requirements-build.txt
python build.py
```

Use `--target` when building on a matching host:

```bash
python build.py --target linux-x64
```

## Release

Versions are kept in `VERSION`, `pwrtchmatcher/version.py`, and `pyproject.toml`. Releases use `vMAJOR.MINOR.PATCH` tags. The GitHub Actions release workflow builds all five target binaries in parallel, creates versioned and stable asset names, generates per-platform SHA256 files, and publishes them to the GitHub Release.

## Matching rule

For each TCH row:

```text
PWR Site == TCH Zone
PWR First Occurred <= TCH Fault Time <= PWR Cleared
```

If multiple PWR windows match, the first matching PWR row in the original file order is used.

The source CSV files are never overwritten by the application; the user chooses the final output path.

## License

PwrTchMatcher is proprietary software. Personal, non-commercial use is permitted at no charge under `LICENSE`.

Commercial or organizational use requires a paid commercial license of **USD 12,000 per legal entity per 12 months**, unless a separate written agreement states otherwise.

The software is not released under an open-source license.
