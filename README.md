AI-Generated Tool for testing!

# Tuckbox Generator

Tkinter desktop application for designing printable Magic: The Gathering tuckboxes.

## Features

- Standard MTG dimensions: 63 × 88 mm
- 60, 75, 90, and 100-card presets
- Unsleeved, standard-sleeve, and thick-sleeve profiles
- Front/back artwork import with drag positioning
- Dieline with glue tab, flaps, cut lines, fold lines, and trim marks
- SVG export with embedded artwork
- Single-box PDF export
- Multiple-box-per-page PDF sheets for A4 and US Letter
- Portable Windows executable build using PyInstaller

## Run from source

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

## Build a portable Windows executable

On Windows, open Command Prompt in the repository and run:

```bat
build_windows.bat
```

The script installs the build dependency and creates:

```text
portable\\TuckboxGenerator.exe
```

You can also run the GitHub Actions workflow manually from **Actions → Build Windows portable executable**, or push a tag such as `v1.0.0`. The workflow publishes a downloadable ZIP artifact.

Print exports at **Actual size / 100%** and make a test cut first because stock, sleeves, and printer tolerances vary.

## License

MIT
