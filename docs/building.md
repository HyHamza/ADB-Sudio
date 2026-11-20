# Building & Packaging

## Running Tests & Linter

Install development dependencies and run the test suite and linter:

```powershell
pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

## Building a Standalone Windows Executable

ADB Studio includes a PyInstaller spec (`ADBStudio.spec`) that bundles `main.py` and `assets/` into a windowed single-file executable (`dist\ADBStudio.exe`).

```powershell
pip install pyinstaller
pyinstaller ADBStudio.spec
```

Output will be generated at `dist\ADBStudio.exe`.

## Building the Windows Installer

The Inno Setup script (`installer.iss`) packages `dist\ADBStudio.exe` into a standard Windows installer without requiring admin privileges (`PrivilegesRequired=lowest`).

1. Build `dist\ADBStudio.exe` using PyInstaller first.
2. Open `installer.iss` in [Inno Setup](https://jrsoftware.org/isinfo.php) (or run `iscc installer.iss` from the command line).
3. The installer will be created at `dist\installer\ADBStudio_Setup_1.0.0.exe`.
