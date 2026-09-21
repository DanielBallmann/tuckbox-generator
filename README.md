# Tuckbox Generator

A standalone Tkinter desktop app that generates a physical tuckbox dieline for standard Magic: The Gathering cards.

## Features

- MTG defaults: 63 × 88 mm cards
- Automatic box width from card count and card thickness
- Adjustable clearance, bleed, glue tab, and tuck flap
- Real dieline layout: glue tab, back, side, front, side, top/bottom flaps, and dust flaps
- Solid cut lines and blue dashed fold lines
- SVG export in millimetres
- A4 and US Letter PDF export at fitted scale
- Live preview

## Install and run

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python app.py
```

Always print with **Actual size / 100% scale**. Make one test cut before producing a batch; card stock, sleeves, and printer tolerances vary.

## Geometry

The internal width is calculated as `card count × card thickness + 2 × clearance`. The standard MTG card face is 63 × 88 mm. The generated dieline includes a configurable glue tab and independent top/bottom closure flaps.

## License

MIT
