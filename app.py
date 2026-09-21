"""Printable straight-tuck MTG box generator.

The dieline is a single, connected blank: a glue tab, four body panels,
top and bottom tuck flaps, and dust flaps.  Cut lines are red and score
(fold) lines are grey dashed lines.
"""
from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:  # pragma: no cover
    Image = ImageOps = ImageTk = None

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas
except ImportError:  # pragma: no cover
    A4 = letter = mm = ImageReader = Canvas = None


@dataclass
class Box:
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
    def width(self):
        return max(1.0, self.cards * self.thickness + 2 * self.clearance)

    @property
    def depth(self):
        return self.card_w + 2 * self.clearance

    @property
    def height(self):
        return self.card_h + 2 * self.clearance

    @property
    def body_y(self):
        # Leave room below the body for the lower tuck flap.
        return self.depth + self.tuck_lip

    @property
    def sheet_w(self):
        return self.glue + 2 * self.width + 2 * self.depth + 2 * self.bleed

    @property
    def sheet_h(self):
        return self.body_y + self.height + self.depth + self.tuck_lip + 2 * self.bleed

    def panels(self):
        """Return artwork rectangles in bottom-left millimetre coordinates."""
        x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        return {
            "back": (x, y, w, h),
            "side_left": (x + w, y, d, h),
            "front": (x + w + d, y, w, h),
            "side_right": (x + 2 * w + d, y, d, h),
            "top": (x, y + h, w, d),
            "bottom": (x + w + d, y - d, w, d),
        }

    def body(self):
        return [(x, y, w, h, name) for name, (x, y, w, h) in self.panels().items()
                if name in {"back", "side_left", "front", "side_right"}]

    def cut_polygons(self):
        """Return only the outside cut edges, including the glue tab.

        The old layout left the glue area as empty paper and extended fold
        lines across the whole sheet.  That cannot be cut or folded into a
        box.  Every returned polygon is now a connected part of the blank.
        """
        p = self.panels()
        x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        dust = min(d * 0.42, h * 0.38)
        left, right = p["side_left"][0], p["side_right"][0]
        notch = max(2.0, min(self.notch, w - 4.0))
        chamfer = min(4.0, self.glue / 2)

        glue = [(0, y + chamfer), (chamfer, y), (x, y), (x, y + h),
                (chamfer, y + h), (0, y + h - chamfer)]
        top = [(x, y + h), (x + w, y + h), (x + w, y + h + d),
               (x + w - 7, y + h + d + self.tuck_lip),
               (x + w / 2 + notch / 2, y + h + d + self.tuck_lip),
               (x + w / 2 + notch / 2, y + h + d + self.tuck_lip - 4),
               (x + w / 2 - notch / 2, y + h + d + self.tuck_lip - 4),
               (x + w / 2 - notch / 2, y + h + d + self.tuck_lip),
               (x + 7, y + h + d + self.tuck_lip), (x, y + h + d)]
        bx, by = p["bottom"][:2]
        bottom = [(bx, by), (bx + w, by), (bx + w, by - d),
                  (bx + w, by - d - self.tuck_lip), (bx, by - d - self.tuck_lip),
                  (bx, by - d)]
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
        return [glue, top, bottom, *dust_polys]

    def fold_segments(self):
        """Return hinge segments; do not score through unrelated flaps."""
        p = self.panels()
        x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        return [
            ((x, y), (x, y + h)),
            ((x + w, y), (x + w, y + h)),
            ((x + w + d, y), (x + w + d, y + h)),
            ((x + 2 * w + d, y), (x + 2 * w + d, y + h)),
            ((x, y + h), (x + w, y + h)),
            ((x + w + d, y), (x + 2 * w + d, y)),
            ((x + w, y), (x + w + d, y)),
            ((x + 2 * w + d, y), (x + 2 * w + 2 * d, y)),
            ((x + w, y + h), (x + w + d, y + h)),
            ((x + 2 * w + d, y + h), (x + 2 * w + 2 * d, y + h)),
        ]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Tuckbox Generator")
        self.geometry("1180x780")
        self.box = Box()
        self.art = {name: None for name in self.box.panels()}
        self.photos = []
        self.scale, self.origin = 1.0, (15, 15)
        self.vars = {k: ttk.StringVar(value=str(v)) for k, v in {
            "cards": 22, "card_w": 63, "card_h": 88, "thickness": .30,
            "clearance": 2, "bleed": 3, "glue": 12, "tuck_lip": 19.05, "notch": 11}.items()}
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill=BOTH, expand=True)
        side = ttk.Frame(root, width=300); side.pack(side=LEFT, fill=Y, padx=(0, 12)); side.pack_propagate(False)
        view = ttk.Frame(root); view.pack(side=RIGHT, fill=BOTH, expand=True)
        ttk.Label(side, text="MTG Tuckbox Generator", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 10))
        sizing = ttk.Labelframe(side, text="Box dimensions (mm)", padding=8); sizing.pack(fill=X)
        labels = {"cards":"Cards", "card_w":"Card width", "card_h":"Card height", "thickness":"Thickness/card", "clearance":"Clearance", "bleed":"Bleed", "glue":"Glue tab", "tuck_lip":"Tuck lip", "notch":"Thumb notch"}
        for key, var in self.vars.items():
            row = ttk.Frame(sizing); row.pack(fill=X, pady=2)
            ttk.Label(row, text=labels[key], width=17).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=9).pack(side=RIGHT)
        ttk.Button(sizing, text="Apply dimensions", command=self.apply, bootstyle="primary").pack(fill=X, pady=(7, 0))
        art = ttk.Labelframe(side, text="Artwork", padding=8); art.pack(fill=X, pady=8)
        for label, face in (("Back","back"),("Left side","side_left"),("Front","front"),("Right side","side_right"),("Top flap","top"),("Bottom flap","bottom")):
            ttk.Button(art, text=f"Choose {label}", command=lambda f=face: self.choose_art(f)).pack(fill=X, pady=2)
        self.art_label = ttk.Label(art, text="No artwork loaded", wraplength=270); self.art_label.pack(anchor="w", pady=4)
        ttk.Button(side, text="Save SVG dieline", command=self.save_svg, bootstyle="info").pack(fill=X, pady=2)
        ttk.Button(side, text="Save PDF (A4)", command=lambda: self.save_pdf(A4), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(side, text="Save PDF (Letter)", command=lambda: self.save_pdf(letter), bootstyle="success").pack(fill=X, pady=2)
        self.info = ttk.Label(side, justify="left", wraplength=285); self.info.pack(anchor="w", pady=12)
        ttk.Label(view, text="Preview • red=cut • grey dashed=fold", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 7))
        self.canvas = tk.Canvas(view, bg="#edf0f2", highlightthickness=1); self.canvas.pack(fill=BOTH, expand=True); self.canvas.bind("<Configure>", lambda _: self.redraw())

    def apply(self):
        try:
            values = {k: float(v.get()) for k, v in self.vars.items()}; values["cards"] = int(values["cards"])
            if values["cards"] < 1 or values["bleed"] < 0 or any(v <= 0 for k, v in values.items() if k != "bleed"): raise ValueError
            old = self.art; self.box = Box(**values); self.art = {f: old.get(f) for f in self.box.panels()}; self.update_art_label(); self.redraw()
        except (ValueError, TypeError): messagebox.showerror("Invalid dimensions", "Enter positive dimensions and at least one card.")

    def choose_art(self, face):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff")])
        if not path or Image is None: return
        try:
            with Image.open(path) as im: im.verify()
            self.art[face] = str(Path(path).resolve()); self.update_art_label(); self.redraw()
        except Exception as exc: messagebox.showerror("Invalid artwork", str(exc))

    def update_art_label(self):
        self.art_label.config(text="\n".join(f"{f}: {Path(p).name}" for f, p in self.art.items() if p) or "No artwork loaded")

    def page_xy(self, x, y): return (self.origin[0] + (x + self.box.bleed) * self.scale, self.origin[1] + (self.box.sheet_h - y - self.box.bleed) * self.scale)

    def redraw(self):
        if not hasattr(self, "canvas"): return
        b = self.box; self.canvas.delete("all"); self.photos.clear()
        self.scale = min(max(self.canvas.winfo_width()-30,100)/b.sheet_w, max(self.canvas.winfo_height()-30,100)/b.sheet_h); self.origin=(15,15)
        def poly(points, fill="white", outline="#dc3545"):
            self.canvas.create_polygon([q for p in points for q in self.page_xy(*p)], fill=fill, outline=outline, width=2)
        for x,y,w,h,name in b.body(): poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)], "#fff" if name in {"front","back"} else "#f0f2f4")
        for points in b.cut_polygons(): poly(points, "#f0f2f4")
        for a, z in b.fold_segments(): self.canvas.create_line(*self.page_xy(*a), *self.page_xy(*z), fill="#6c757d", dash=(7,4), width=2)
        for face, path in self.art.items(): self.draw_art(face, path)
        self.info.config(text=f"Internal: {b.width:.1f} W × {b.depth:.1f} D × {b.height:.1f} H mm\nSheet: {b.sheet_w:.1f} × {b.sheet_h:.1f} mm\nArtwork: {sum(bool(p) for p in self.art.values())}/6")

    def draw_art(self, face, path):
        if not path or Image is None: return
        try:
            x,y,w,h = self.box.panels()[face]
            with Image.open(path) as source: image = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (max(2,round(w*self.scale)), max(2,round(h*self.scale))))
            photo=ImageTk.PhotoImage(image); self.photos.append(photo); self.canvas.create_image(*self.page_xy(x+w/2,y+h/2), image=photo, anchor="center")
        except Exception as exc: self.info.config(text=f"Artwork preview failed: {exc}")

    def save_svg(self):
        path=filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG files","*.svg")])
        if not path: return
        b=self.box; W,H=b.sheet_w,b.sheet_h; o=b.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
        def polygon(points): out.append('<polygon points="'+' '.join(f'{x+o},{H-y-o}' for x,y in points)+'" fill="none" stroke="#dc3545" stroke-width=".25"/>')
        for points in b.cut_polygons(): polygon(points)
        for x,y,w,h,_ in b.body(): polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
        for face,p in self.art.items():
            if p:
                x,y,w,h=b.panels()[face]; data=base64.b64encode(Path(p).read_bytes()).decode(); mime=mimetypes.guess_type(p)[0] or "image/jpeg"; out.append(f'<image href="data:{mime};base64,{data}" x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')
        for (x1,y1),(x2,y2) in b.fold_segments(): out.append(f'<path d="M{x1+o} {H-y1-o}L{x2+o} {H-y2-o}" fill="none" stroke="#777" stroke-dasharray="2,1"/>')
        Path(path).write_text("\n".join(out+["</svg>"]), encoding="utf-8"); messagebox.showinfo("Saved", f"SVG saved to:\n{path}")

    def save_pdf(self, pagesize):
        if Canvas is None: messagebox.showerror("Missing dependency", "Install dependencies with: pip install -r requirements.txt"); return
        path=filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files","*.pdf")])
        if not path: return
        try:
            b=self.box; pw,ph=pagesize; margin=12*mm; scale=min((pw-2*margin)/(b.sheet_w*mm),(ph-2*margin)/(b.sheet_h*mm)); px=margin+(pw-2*margin-b.sheet_w*mm*scale)/2; py=margin+(ph-2*margin-b.sheet_h*mm*scale)/2; pdf=Canvas(path,pagesize=pagesize)
            def P(x,y): return px+(x+b.bleed)*mm*scale, py+(y+b.bleed)*mm*scale
            def line(points):
                q=pdf.beginPath(); q.moveTo(*P(*points[0])); [q.lineTo(*P(*p)) for p in points[1:]]; q.close(); pdf.setStrokeColorRGB(.86,.1,.18); pdf.setDash(); pdf.drawPath(q,stroke=1,fill=0)
            for points in b.cut_polygons(): line(points)
            for x,y,w,h,_ in b.body(): line([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
            for face,p in self.art.items():
                if p:
                    x,y,w,h=b.panels()[face]; pdf.drawImage(ImageReader(p),*P(x,y),width=w*mm*scale,height=h*mm*scale,preserveAspectRatio=False,mask="auto")
            pdf.setStrokeColorRGB(.45,.45,.45); pdf.setDash(3,2)
            for a,z in b.fold_segments(): pdf.line(*P(*a),*P(*z))
            pdf.save(); messagebox.showinfo("Saved", f"PDF saved to:\n{path}")
        except Exception as exc: messagebox.showerror("PDF export failed", str(exc))


if __name__ == "__main__": App().mainloop()
