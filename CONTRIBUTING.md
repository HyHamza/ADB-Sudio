# Contributing to ADB Studio

Contributions, bug reports, and pull requests are welcome.

## Development Setup

```powershell
git clone https://github.com/HyHamza/ADB-Sudio.git
cd ADB-Sudio
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Running Checks

Before opening a pull request, make sure tests and linting pass:

```powershell
python -m pytest
python -m ruff check .
```

## Guidelines

- Keep ADB command wrappers in `adb_studio/adb_client.py` and UI logic in `adb_studio/ui/`.
- Add unit tests in `tests/` for new ADB parsing or client behavior (mock subprocess calls rather than requiring a physical device).
- Keep commits focused and descriptive.
