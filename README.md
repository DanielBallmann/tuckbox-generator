# Tuckbox Generator

A standalone Python desktop application for generating printable tuckboxes sized for Magic: The Gathering cards.

Features:
- Tkinter desktop interface
- MTG default card size presets (63 × 88 mm)
- Adjustable card count, thickness, clearance, and bleed
- Front/back artwork support
- Print-ready SVG and PDF export
- Live layout preview

## Requirements

- Python 3.10+
- pip

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

## Default sizing

- Card width: 63 mm
- Card height: 88 mm
- Card thickness: 0.30 mm
- Clearance: 2 mm
- Bleed: 3 mm

## Output

The app can export a simple print-ready SVG and PDF layout using the current artwork and dimensions.

## License

MIT
