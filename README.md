# Tuckbox Generator

Tkinter desktop application for designing printable Magic: The Gathering tuckboxes.

## Included

- Standard MTG card dimensions: 63 × 88 mm
- Presets for 60, 75, 90, and 100 cards
- Unsleeved, standard-sleeve, and thick-sleeve profiles
- Automatic stack-width calculation from card count and thickness
- Front/back artwork import with live drag-to-position preview
- Configurable artwork scale and position state
- Dieline with glue tab, front/back/side panels, tuck flap, dust flaps, cut and fold lines
- Red trim/registration marks
- SVG export with embedded artwork
- A4 and US Letter PDF dieline export

## Install

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Print exports at **Actual size / 100%**. Always make a test cut first: card stock, sleeve brands, and printer tolerances vary. Imported artwork can be dragged over the front or back panel in the preview; use Reset artwork positions to return it to center.

## Geometry

The internal stack width is `cards × thickness + 2 × clearance`. The other internal dimensions are the 63 × 88 mm MTG card face plus clearance. Sleeve profiles provide practical starting values, but measure your own stack for production work.

## License

MIT
