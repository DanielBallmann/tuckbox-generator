"""MTG straight-tuck-end box generator.

The drawing uses one continuous cut sheet: four body panels, a top tuck
flap, a bottom tuck flap, a glue tab, and chamfered dust flaps.  Artwork is
mapped to the physical faces so the preview and exported files fold into the
same box.
"""
from __future__ import annotations

import base64
import mimetypes
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import unquote, urlparse

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = ImageOps = ImageTk = None

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas
except ImportError:
    A4 = letter = mm = ImageReader = Canvas = None

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
BaseWindow = TkinterDnD.Tk if TkinterDnD else tk.Tk


@dataclass
class Box:
    """Physical box dimensions, in millimetres.

    ``width`` is the card-stack width, ``depth`` is the card width, and
    ``height`` is the card height.  The extra tuck lip makes the top and
    bottom closures long enough to hold the box shut after folding.
    """

    cards: int = 22
    card_w: float = 63.0
    card_h: float = 88.0
    thickness: float = 0.30
    clearance: float = 2.0
    bleed: float = 3.0
    glue: float = 12.0
    tuck_lip: float = 19.05
    notch: float = 11.0

    @property
    def width(self) -> float:
        return self.cards * self.thickness + 2 * self.clearance

    @property
    def depth(self) -> float:
        return self.card_w + 2 * self.clearance

    @property
    def height(self) -> float:
        return self.card_h + 2 * self.clearance

    @property
    def body_y(self) -> float:
        # The bottom edge is reserved for the bottom closure and dust flaps.
        return self.depth + self.tuck_lip

    @property
    def sheet_w(self) -> float:
        return self.glue + 2 * self.width + 2 * self.depth + 2 * self.bleed

    @property
    def sheet_h(self) -> float:
        return self.body_y + self.height + self.depth + 2 * self.bleed

    def panels(self) -> dict[str, tuple[float, float, float, float]]:
        """Return face rectangles in cut-sheet coordinates (origin at bottom)."""
        x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        return {
            "back": (x, y, w, h),
            "side_left": (x + w, y, d, h),
            "front": (x + w + d, y, w, h),
            "side_right": (x + 2 * w + d, y, d, h),
            # The top flap is hinged to the back panel.
            "top": (x, y + h, w, d),
            # The bottom flap is hinged to the front panel and tucks underneath.
            "bottom": (x + w + d, y - d, w, d),
        }

    def body(self):
        """Return the four upright panels used for artwork and scoring."""
        return [
            (x, y, w, h, name)
            for name, (x, y, w, h) in self.panels().items()
            if name in {"back", "side_left", "front", "side_right"}
        ]

    def cut_polygons(self):
        """Return the non-rectangular cut edges for the foldable dieline."""
        p = self.panels()
        x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        dust = min(d * 0.42, h * 0.38)
        left, right = p["side_left"][0], p["side_right"][0]

        # A thumb notch separates the tuck lip so the lid can be opened.
        notch = min(self.notch, max(2.0, w - 4.0))
        top = [
            (p["top"][0], p["top"][1]),
            (p["top"][0] + w, p["top"][1]),
            (p["top"][0] + w - 7, p["top"][1] + self.tuck_lip),
            (p["top"][0] + w / 2 + notch / 2, p["top"][1] + self.tuck_lip),
            (p["top"][0] + w / 2 + notch / 2, p["top"][1] + self.tuck_lip - 4),
            (p["top"][0] + w / 2 - notch / 2, p["top"][1] + self.tuck_lip - 4),
            (p["top"][0] + w / 2 - notch / 2, p["top"][1] + self.tuck_lip),
            (p["top"][0] + 7, p["top"][1] + self.tuck_lip),
        ]
        bottom = [
            (p["bottom"][0], p["bottom"][1]),
            (p["bottom"][0] + w, p["bottom"][1]),
            (p["bottom"][0] + w, p["bottom"][1] - self.tuck_lip),
            (p["bottom"][0], p["bottom"][1] - self.tuck_lip),
        ]
        dust_polys = [
            [(left + 2, y), (left + d - 2, y), (left + d, y - dust + 4),
             (left + d - 4, y - dust), (left + 4, y - dust), (left, y - dust + 4)],
            [(right + 2, y), (right + d - 2, y), (right + d, y - dust + 4),
             (right + d - 4, y - dust), (right + 4, y - dust), (right, y - dust + 4)],
            [(left + 2, y + h), (left + d - 2, y + h),
             (left + d - 4, y + h + dust), (left + 4, y + h + dust)],
            [(right + 2, y + h), (right + d - 2, y + h),
             (right + d - 4, y + h + dust), (right + 4, y + h + dust)],
        ]
        return [top, bottom, *dust_polys]


class App(BaseWindow):
    """Tkinter UI, preview renderer, and PDF/SVG exporter."""

    def __init__(self):
        super().__init__()
        self.style = ttk.Style(theme="flatly")
        self.title("MTG Tuckbox Generator")
        self.geometry("1240x820")
        self.minsize(1000, 680)
        self.dark = False
        self.box = Box()
        self.art = {face: None for face in self.box.panels()}
        self.photos = []  # Keep PhotoImage objects alive while Tk displays them.
        self.scale = 1.0
        self.origin = (15.0, 15.0)
        self.size_visible = False
        self.vars = {k: ttk.StringVar(value=str(v)) for k, v in {
            "cards": 22, "card_w": 63, "card_h": 88, "thickness": .30,
            "clearance": 2, "bleed": 3, "glue": 12, "tuck_lip": 19.05,
            "notch": 11}.items()}
        self.cols, self.rows, self.gap = ttk.StringVar(value="1"), ttk.StringVar(value="1"), ttk.StringVar(value="5")
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill=BOTH, expand=True)
        side = ttk.Frame(root, width=320); side.pack(side=LEFT, fill=Y, padx=(0, 12)); side.pack_propagate(False)
        view = ttk.Frame(root); view.pack(side=RIGHT, fill=BOTH, expand=True)
        header = ttk.Frame(side); header.pack(fill=X, pady=(0, 10))
        ttk.Label(header, text="MTG Tuckbox Generator", font=("Segoe UI", 16, "bold"), bootstyle="primary").pack(side=LEFT)
        ttk.Button(header, text="☾", width=3, command=self.toggle_theme, bootstyle="secondary-outline").pack(side=RIGHT)

        self.size_box = ttk.Labelframe(side, text="Sizing options", padding=8, bootstyle="primary")
        labels = {"cards":"Cards per pack", "card_w":"Card width (mm)", "card_h":"Card height (mm)", "thickness":"Thickness/card (mm)", "clearance":"Clearance (mm)", "bleed":"Bleed (mm)", "glue":"Glue tab (mm)", "tuck_lip":"Tuck lip (mm)", "notch":"Thumb notch (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(self.size_box); row.pack(fill=X, pady=2)
            ttk.Label(row, text=labels[key], width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(self.size_box, text="Apply dimensions", command=self.apply, bootstyle="primary").pack(fill=X, pady=(7, 0))
        self.size_button = ttk.Button(side, text="Show sizing options", command=self.toggle_size, bootstyle="link"); self.size_button.pack(anchor="w", pady=(0, 5))

        art = ttk.Labelframe(side, text="Artwork — fixed to faces", padding=8, bootstyle="secondary"); art.pack(fill=X, pady=6)
        for label, face in (("Back", "back"), ("Left side", "side_left"), ("Front", "front"), ("Right side", "side_right"), ("Top flap", "top"), ("Bottom flap", "bottom")):
            button = ttk.Button(art, text=f"Choose {label} artwork", command=lambda f=face: self.choose_art(f), bootstyle="secondary")
            button.pack(fill=X, pady=2); self.register_drop(button, face)
        self.art_label = ttk.Label(art, text="No artwork loaded", wraplength=290); self.art_label.pack(anchor="w", pady=4)
        ttk.Label(art, text="Drop an image onto its matching button. JPG/JPEG files with spaces in their names are supported.", wraplength=290).pack(anchor="w")

        sheet = ttk.Labelframe(side, text="Print sheet", padding=8, bootstyle="secondary"); sheet.pack(fill=X, pady=6)
        for label, var in (("Columns", self.cols), ("Rows", self.rows), ("Gap (mm)", self.gap)):
            row = ttk.Frame(sheet); row.pack(fill=X, pady=2); ttk.Label(row, text=label, width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(sheet, text="Save PDF sheet — A4", command=lambda: self.save_pdf(A4), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(sheet, text="Save PDF sheet — Letter", command=lambda: self.save_pdf(letter), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(sheet, text="Save SVG dieline", command=self.save_svg, bootstyle="info").pack(fill=X, pady=(6, 2))
        self.info = ttk.Label(side, justify="left", wraplength=300); self.info.pack(anchor="w", pady=12)
        ttk.Label(view, text="Preview • red=cut • grey dashed=score • artwork fixed to all faces", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 7))
        self.canvas = tk.Canvas(view, bg="#edf0f2", highlightthickness=1); self.canvas.pack(fill=BOTH, expand=True); self.canvas.bind("<Configure>", lambda _e: self.redraw())

    def register_drop(self, widget, face):
        """Register each artwork button separately; tkinterdnd2 is optional."""
        if DND_FILES is None:
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda event, f=face: self.drop_art(f, event.data))

    def drop_art(self, face, data):
        """Parse native Tk drop lists and file:// URLs, including quoted JPG paths."""
        try:
            paths = list(self.tk.splitlist(data))
        except tk.TclError:
            paths = [str(data)]
        if not paths:
            return
        raw = paths[0].strip().strip('{}')
        parsed = urlparse(raw)
        if parsed.scheme == "file":
            raw = unquote(parsed.path)
            # Windows file URLs commonly arrive as /C:/... .
            if len(raw) > 2 and raw[0] == "/" and raw[2] == ":":
                raw = raw[1:]
        self.set_art(face, raw)

    def choose_art(self, face):
        path = filedialog.askopenfilename(title=f"Choose {face} artwork", filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff")])
        if path:
            self.set_art(face, path)

    def set_art(self, face, path):
        """Validate artwork before changing state, avoiding broken JPG previews."""
        path_obj = Path(path).expanduser()
        if path_obj.suffix.lower() not in SUPPORTED:
            messagebox.showerror("Unsupported artwork", "Choose a JPG, PNG, WEBP, BMP, GIF, or TIFF image."); return
        if not path_obj.is_file():
            messagebox.showerror("Artwork not found", f"The dropped file does not exist:\n{path_obj}"); return
        if Image is None:
            messagebox.showerror("Missing Pillow", "Install dependencies with: pip install -r requirements.txt"); return
        try:
            # verify() catches truncated JPEGs, but the image must be reopened after it.
            with Image.open(path_obj) as image:
                image.verify()
            with Image.open(path_obj) as image:
                image.load()
        except Exception as exc:
            messagebox.showerror("Invalid image", str(exc)); return
        self.art[face] = str(path_obj.resolve())
        self.update_art_label(); self.redraw()

    def update_art_label(self):
        self.art_label.config(text="\n".join(f"{face}: {Path(path).name}" for face, path in self.art.items() if path) or "No artwork loaded")

    def toggle_size(self):
        if self.size_visible:
            self.size_box.pack_forget(); self.size_button.config(text="Show sizing options")
        else:
            self.size_box.pack(fill=X, before=self.size_button, pady=(0, 8)); self.size_button.config(text="Hide sizing options")
        self.size_visible = not self.size_visible

    def toggle_theme(self):
        self.dark = not self.dark; self.style.theme_use("darkly" if self.dark else "flatly"); self.canvas.configure(bg="#1f2329" if self.dark else "#edf0f2"); self.redraw()

    def apply(self):
        try:
            values = {k: float(v.get()) for k, v in self.vars.items()}; values["cards"] = int(values["cards"])
            if values["cards"] < 1 or any(v <= 0 for k, v in values.items() if k != "bleed") or values["bleed"] < 0:
                raise ValueError
            previous = self.art; self.box = Box(**values); self.art = {face: previous.get(face) for face in self.box.panels()}
            self.update_art_label(); self.redraw()
        except (ValueError, TypeError):
            messagebox.showerror("Invalid dimensions", "Enter positive dimensions and at least one card.")

    def page_xy(self, x, y):
        return (self.origin[0] + (x + self.box.bleed) * self.scale, self.origin[1] + (self.box.sheet_h - y - self.box.bleed) * self.scale)

    def redraw(self):
        if not hasattr(self, "canvas"): return
        b = self.box; self.canvas.delete("all"); self.photos.clear()
        self.scale = min(max(self.canvas.winfo_width() - 30, 100) / b.sheet_w, max(self.canvas.winfo_height() - 30, 100) / b.sheet_h); self.origin = (15.0, 15.0)
        cut, score = ("#ff6675", "#adb5bd") if self.dark else ("#dc3545", "#6c757d")
        panel, side = (("#30343b", "#272b31") if self.dark else ("#ffffff", "#f0f2f4"))

        def poly(points, fill, outline=cut):
            coords = [n for p in points for n in self.page_xy(*p)]; self.canvas.create_polygon(coords, fill=fill, outline=outline, width=2)

        for x, y, w, h, name in b.body():
            poly([(x, y), (x+w, y), (x+w, y+h), (x, y+h)], panel if name in ("front", "back") else side)
        for points in b.cut_polygons(): poly(points, side)

        # Fold lines run through the panel seams and the two closure hinges.
        seam_x = (b.glue, b.glue+b.width, b.glue+b.width+b.depth, b.glue+2*b.width+b.depth)
        for x in seam_x:
            a, bb = self.page_xy(x, 0); c, d = self.page_xy(x, b.sheet_h); self.canvas.create_line(a, bb, c, d, fill=score, dash=(7, 4), width=2)
        for y in (b.body_y, b.body_y+b.height):
            a, bb = self.page_xy(0, y); c, d = self.page_xy(b.sheet_w, y); self.canvas.create_line(a, bb, c, d, fill=score, dash=(7, 4), width=2)
        for face, path in self.art.items(): self.draw_art(face, path)
        self.info.config(text=f"Cards per pack: {b.cards}\nInternal: {b.width:.1f} W × {b.depth:.1f} D × {b.height:.1f} H mm\nStraight-tuck sheet: {b.sheet_w:.1f} × {b.sheet_h:.1f} mm\nArtwork faces: {sum(bool(p) for p in self.art.values())}/6")

    def draw_art(self, face, path):
        """Draw a fresh, EXIF-corrected RGB copy so JPEG mode/orientation is safe."""
        if not path or Image is None: return
        try:
            x, y, w, h = self.box.panels()[face]
            with Image.open(path) as source:
                image = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (max(2, round(w*self.scale)), max(2, round(h*self.scale))), method=Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image); self.photos.append(photo)
            cx, cy = self.page_xy(x+w/2, y+h/2); self.canvas.create_image(cx, cy, image=photo, anchor="center")
        except Exception as exc:
            self.info.config(text=f"Artwork preview failed: {exc}")

    def svg_art(self, face):
        path = self.art[face]
        if not path: return ""
        x, y, w, h = self.box.panels()[face]; data = base64.b64encode(Path(path).read_bytes()).decode("ascii"); mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        return f'<image href="data:{mime};base64,{data}" x="{x+self.box.bleed}" y="{self.box.sheet_h-y-self.box.bleed-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>'

    def save_svg(self):
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG files", "*.svg")])
        if not path: return
        b, W, H, o = self.box, self.box.sheet_w, self.box.sheet_h, self.box.bleed
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
        def polygon(points): out.append(f'<polygon points="{" ".join(f"{x+o},{H-y-o}" for x, y in points)}" fill="none" stroke="#dc3545" stroke-width=".25"/>')
        for x, y, w, h, _ in b.body(): polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
        for points in b.cut_polygons(): polygon(points)
        out.extend(self.svg_art(face) for face in self.art)
        for x in (b.glue, b.glue+b.width, b.glue+b.width+b.depth, b.glue+2*b.width+b.depth): out.append(f'<path d="M{x+o} {H-o}V{H-b.sheet_h+o}" fill="none" stroke="#777" stroke-dasharray="2,1"/>')
        for y in (b.body_y, b.body_y+b.height): out.append(f'<path d="M{o} {H-y-o}H{W-o}" fill="none" stroke="#777" stroke-dasharray="2,1"/>')
        Path(path).write_text("\n".join(out + ["</svg>"]), encoding="utf-8"); messagebox.showinfo("Saved", f"SVG saved to:\n{path}")

    def save_pdf(self, pagesize):
        if Canvas is None or ImageReader is None:
            messagebox.showerror("Missing dependency", "Install dependencies with: pip install -r requirements.txt"); return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not path: return
        try:
            cols, rows, gap = int(self.cols.get()), int(self.rows.get()), float(self.gap.get())
            if cols < 1 or rows < 1 or gap < 0: raise ValueError
            b = self.box; pw, ph = pagesize; margin = 12 * mm; sw = cols*b.sheet_w + (cols-1)*gap; sh = rows*b.sheet_h + (rows-1)*gap
            scale = min((pw-2*margin)/(sw*mm), (ph-2*margin)/(sh*mm)); left = margin + (pw-2*margin-sw*mm*scale)/2; bottom = margin + (ph-2*margin-sh*mm*scale)/2; pdf = Canvas(path, pagesize=pagesize)
            def draw_one(px, py):
                def P(x, y): return px+(x+b.bleed)*mm*scale, py+(y+b.bleed)*mm*scale
                def outline(points):
                    q = pdf.beginPath(); q.moveTo(*P(*points[0])); [q.lineTo(*P(*point)) for point in points[1:]]; q.close(); pdf.setStrokeColorRGB(.86,.1,.18); pdf.setDash(); pdf.drawPath(q, stroke=1, fill=0)
                for x, y, w, h, _ in b.body(): outline([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
                for points in b.cut_polygons(): outline(points)
                for face, image_path in self.art.items():
                    if image_path:
                        x, y, w, h = b.panels()[face]; pdf.drawImage(ImageReader(image_path), *P(x, y), width=w*mm*scale, height=h*mm*scale, preserveAspectRatio=False, mask="auto")
                pdf.setStrokeColorRGB(.45,.45,.45); pdf.setDash(3,2)
                for x in (b.glue, b.glue+b.width, b.glue+b.width+b.depth, b.glue+2*b.width+b.depth): pdf.line(*P(x,0), *P(x,b.sheet_h))
                for y in (b.body_y, b.body_y+b.height): pdf.line(*P(0,y), *P(b.sheet_w,y))
                pdf.setDash()
            for row in range(rows):
                for col in range(cols): draw_one(left+col*(b.sheet_w+gap)*mm*scale, bottom+(rows-1-row)*(b.sheet_h+gap)*mm*scale)
            pdf.save(); messagebox.showinfo("Saved", f"PDF saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("PDF export failed", str(exc))


if __name__ == "__main__":
    App().mainloop()
