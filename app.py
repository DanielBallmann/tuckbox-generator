"""Printable MTG tuckbox dieline generator.

The export code deliberately uses only standard-library SVG generation and ReportLab
for PDF output, with explicit error reporting instead of silently swallowing failures.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = ImageOps = ImageTk = None

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
except ImportError:
    A4 = letter = mm = Canvas = None


@dataclass
class Box:
    cards: int = 60
    card_w: float = 63.0
    card_h: float = 88.0
    card_thickness: float = 0.30
    clearance: float = 2.0
    bleed: float = 3.0
    glue_tab: float = 12.0
    flap_depth: float = 25.0

    @property
    def body_w(self) -> float:
        return self.cards * self.card_thickness + 2 * self.clearance

    @property
    def body_d(self) -> float:
        return self.card_w + 2 * self.clearance

    @property
    def body_h(self) -> float:
        return self.card_h + 2 * self.clearance

    @property
    def bottom_flap(self) -> float:
        return self.body_d * 0.55

    @property
    def side_flap(self) -> float:
        return min(self.body_d * 0.45, self.body_h * 0.42)

    @property
    def body_y(self) -> float:
        return self.bottom_flap

    @property
    def cut_w(self) -> float:
        return self.glue_tab + self.body_d + self.body_w + self.body_d + self.body_w

    @property
    def cut_h(self) -> float:
        return self.bottom_flap + self.body_h + self.flap_depth

    @property
    def page_w(self) -> float:
        return self.cut_w + 2 * self.bleed

    @property
    def page_h(self) -> float:
        return self.cut_h + 2 * self.bleed

    def panels(self):
        x, y = self.glue_tab, self.body_y
        return [
            (x, y, self.body_d, self.body_h, "back"),
            (x + self.body_d, y, self.body_w, self.body_h, "side"),
            (x + self.body_d + self.body_w, y, self.body_d, self.body_h, "front"),
            (x + 2 * self.body_d + self.body_w, y, self.body_w, self.body_h, "side"),
        ]

    def flaps(self):
        x, y = self.glue_tab, self.body_y
        # (x, y, width, height, type), using y as the lower edge.
        return [
            (x, y - self.bottom_flap, self.body_d, self.bottom_flap, "bottom-back"),
            (x + self.body_d + self.body_w, y - self.bottom_flap, self.body_d, self.bottom_flap, "bottom-front"),
            (x + self.body_d, y - self.side_flap, self.body_w, self.side_flap, "bottom-side"),
            (x + 2 * self.body_d + self.body_w, y - self.side_flap, self.body_w, self.side_flap, "bottom-side"),
            (x, y + self.body_h, self.body_d, self.flap_depth, "top-back"),
            (x + self.body_d + self.body_w, y + self.body_h, self.body_d, self.flap_depth, "top-tuck"),
            (x + self.body_d, y + self.body_h, self.body_w, self.side_flap, "top-side"),
            (x + 2 * self.body_d + self.body_w, y + self.body_h, self.body_w, self.side_flap, "top-side"),
        ]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Tuckbox Generator")
        self.geometry("1200x800")
        self.box = Box()
        self.front = None
        self.back = None
        self.vars = {k: tk.StringVar(value=str(v)) for k, v in {
            "cards": 60, "card_w": 63, "card_h": 88, "card_thickness": .30,
            "clearance": 2, "bleed": 3, "glue_tab": 12, "flap_depth": 25}.items()}
        self.cols = tk.StringVar(value="1")
        self.rows = tk.StringVar(value="1")
        self.gap = tk.StringVar(value="5")
        self.photos = []
        self.preview_scale = 1
        self.preview_origin = (0, 0)
        self.drag = None
        self.art_offset = {"front": [0.0, 0.0], "back": [0.0, 0.0]}
        self._ui()
        self.after(100, self.redraw)

    def _ui(self):
        root = ttk.Frame(self, padding=10); root.pack(fill="both", expand=True)
        left = ttk.Frame(root, width=300); left.pack(side="left", fill="y", padx=(0, 10)); left.pack_propagate(False)
        right = ttk.Frame(root); right.pack(side="right", fill="both", expand=True)
        ttk.Label(left, text="MTG tuckbox", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        labels = {"cards":"Cards", "card_w":"Card width (mm)", "card_h":"Card height (mm)", "card_thickness":"Thickness/card (mm)", "clearance":"Clearance (mm)", "bleed":"Bleed (mm)", "glue_tab":"Glue tab (mm)", "flap_depth":"Top tuck flap (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(left); row.pack(fill="x", pady=2)
            ttk.Label(row, text=labels[key], width=19).pack(side="left")
            ttk.Entry(row, textvariable=var, width=10).pack(side="right")
        ttk.Button(left, text="Apply dimensions", command=self.apply).pack(fill="x", pady=(7, 8))
        ttk.Separator(left).pack(fill="x", pady=5)
        ttk.Label(left, text="Artwork", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)
        ttk.Button(left, text="Load front artwork", command=lambda: self.load_art("front")).pack(fill="x", pady=2)
        ttk.Button(left, text="Load back artwork", command=lambda: self.load_art("back")).pack(fill="x", pady=2)
        ttk.Button(left, text="Reset artwork positions", command=self.reset_art).pack(fill="x", pady=2)
        self.art_label = ttk.Label(left, text="No artwork loaded", wraplength=280); self.art_label.pack(anchor="w", pady=5)
        ttk.Separator(left).pack(fill="x", pady=7)
        ttk.Label(left, text="Multiple boxes per page", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)
        for label, var in (("Columns", self.cols), ("Rows", self.rows), ("Gap (mm)", self.gap)):
            row = ttk.Frame(left); row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=19).pack(side="left"); ttk.Entry(row, textvariable=var, width=10).pack(side="right")
        ttk.Button(left, text="Save PDF sheet (A4)", command=lambda: self.save_pdf(A4)).pack(fill="x", pady=2)
        ttk.Button(left, text="Save PDF sheet (Letter)", command=lambda: self.save_pdf(letter)).pack(fill="x", pady=2)
        ttk.Button(left, text="Save SVG dieline", command=self.save_svg).pack(fill="x", pady=2)
        self.info = ttk.Label(left, justify="left", wraplength=285); self.info.pack(anchor="w", pady=12)
        ttk.Label(right, text="Solid black = cut   Blue dashed = fold   Red = trim", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
        self.canvas = tk.Canvas(right, background="#edf0f2", highlightthickness=1); self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.start_drag); self.canvas.bind("<B1-Motion>", self.move_drag); self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag", None))

    def apply(self):
        try:
            values = {k: float(v.get()) for k, v in self.vars.items()}
            values["cards"] = int(values["cards"])
            if values["cards"] < 1 or values["bleed"] < 0 or any(values[k] <= 0 for k in values if k != "bleed"):
                raise ValueError
            self.box = Box(**values)
            self.redraw()
        except (TypeError, ValueError):
            messagebox.showerror("Invalid dimensions", "Enter positive numeric dimensions and at least one card.")

    def load_art(self, side):
        path = filedialog.askopenfilename(title=f"Choose {side} artwork", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif")])
        if path:
            setattr(self, side, path)
            self.art_label.config(text=f"Front: {Path(self.front).name if self.front else 'none'}\nBack: {Path(self.back).name if self.back else 'none'}")
            self.redraw()

    def reset_art(self):
        self.art_offset = {"front": [0.0, 0.0], "back": [0.0, 0.0]}; self.redraw()

    def redraw(self):
        if not hasattr(self, "canvas"): return
        self.canvas.delete("all"); self.photos.clear(); b = self.box
        scale = min(max(self.canvas.winfo_width() - 30, 100) / b.page_w, max(self.canvas.winfo_height() - 30, 100) / b.page_h)
        self.preview_scale = scale; self.preview_origin = (15 + b.bleed * scale, 15 + b.bleed * scale)
        def xy(x, y): return self.preview_origin[0] + x * scale, self.preview_origin[1] + (b.page_h - y) * scale
        def rect(x, y, w, h, fill="#fff"):
            a, bb = xy(x + b.bleed, y + b.bleed); c, d = xy(x + b.bleed + w, y + b.bleed + h)
            self.canvas.create_rectangle(a, d, c, bb, fill=fill, outline="#111", width=2)
        for x, y, w, h, name in b.panels(): rect(x, y, w, h, "#fff" if name in ("front", "back") else "#f4f5f6")
        for x, y, w, h, _ in b.flaps(): rect(x, y, w, h, "#f8f8f8")
        for x, y, w, h, name in b.panels():
            a, bb = xy(x + b.bleed + w / 2, y + b.bleed + h / 2); self.canvas.create_text(a, bb, text=name.upper(), fill="#555", font=("Segoe UI", 10, "bold"))
        for x in (b.glue_tab, b.glue_tab + b.body_d, b.glue_tab + b.body_d + b.body_w, b.glue_tab + 2*b.body_d + b.body_w):
            a, bb = xy(x + b.bleed, 0); c, d = xy(x + b.bleed, b.page_h); self.canvas.create_line(a, bb, c, d, fill="#2865ad", dash=(6, 4))
        for y in (b.body_y, b.body_y + b.body_h):
            a, bb = xy(b.bleed, y + b.bleed); c, d = xy(b.page_w - b.bleed, y + b.bleed); self.canvas.create_line(a, bb, c, d, fill="#2865ad", dash=(6, 4))
        self._draw_art("front", self.front, b.glue_tab + b.body_d + b.body_w, b.body_y, b.body_d, b.body_h, xy)
        self._draw_art("back", self.back, b.glue_tab, b.body_y, b.body_d, b.body_h, xy)
        for x, y in ((0, 0), (b.cut_w, 0), (0, b.cut_h), (b.cut_w, b.cut_h)):
            a, bb = xy(x + b.bleed, y + b.bleed); self.canvas.create_oval(a-3, bb-3, a+3, bb+3, outline="#c33")
        self.info.config(text=f"Inside: {b.body_w:.2f} W × {b.body_d:.2f} D × {b.body_h:.2f} H mm\nCut size: {b.cut_w:.2f} × {b.cut_h:.2f} mm\nSheet: set rows/columns, then save PDF\nPrint at 100%; test-cut first.")

    def _draw_art(self, side, path, x, y, w, h, xy):
        if not path or Image is None: return
        try:
            image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            image.thumbnail((max(20, int(w*self.preview_scale)), max(20, int(h*self.preview_scale))), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image); self.photos.append(photo)
            ox, oy = self.art_offset[side]; a, bb = xy(x + w/2 + ox*w, y + h/2 + oy*h)
            self.canvas.create_image(a, bb, image=photo, anchor="center")
        except Exception:
            return

    def start_drag(self, event):
        b = self.box
        for side, path, x, y, w, h in (("front", self.front, b.glue_tab+b.body_d+b.body_w, b.body_y, b.body_d, b.body_h), ("back", self.back, b.glue_tab, b.body_y, b.body_d, b.body_h)):
            if path:
                ox, oy = self.art_offset[side]; cx = self.preview_origin[0] + (x+b.bleed+w/2+ox*w)*self.preview_scale; cy = self.preview_origin[1] + (b.page_h-(y+b.bleed+h/2+oy*h))*self.preview_scale
                if abs(event.x-cx) < w*self.preview_scale/2 and abs(event.y-cy) < h*self.preview_scale/2: self.drag = (side, event.x, event.y); return

    def move_drag(self, event):
        if not self.drag: return
        side, px, py = self.drag
        self.art_offset[side][0] += (event.x-px)/(self.preview_scale*self.box.body_d)
        self.art_offset[side][1] -= (event.y-py)/(self.preview_scale*self.box.body_h)
        self.drag = (side, event.x, event.y); self.redraw()

    def _svg_image(self, path, x, y, w, h, side, H):
        if not path: return ""
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        mime = mimetypes.guess_type(path)[0] or "image/png"
        ox, oy = self.art_offset[side]
        return f'<image href="data:{mime};base64,{data}" x="{x+ox*w-w/2+w/2}" y="{H-(y+oy*h+h/2)}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet"/>'

    def _save_path(self, title, extension, types):
        return filedialog.asksaveasfilename(title=title, defaultextension=extension, filetypes=types)

    def save_svg(self):
        path = self._save_path("Save tuckbox SVG", ".svg", [("SVG files", "*.svg")])
        if not path: return
        try:
            b = self.box; W, H = b.page_w, b.page_h; ox = oy = b.bleed; out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="white"/>']
            def r(x, y, w, h): out.append(f'<rect x="{x+ox}" y="{H-(y+oy+h)}" width="{w}" height="{h}" fill="none" stroke="#111" stroke-width="0.25"/>')
            for x, y, w, h, _ in b.panels(): r(x, y, w, h)
            for x, y, w, h, _ in b.flaps(): r(x, y, w, h)
            for x, y, w, h, name in b.panels():
                if name in ("front", "back"): out.append(self._svg_image(self.front if name == "front" else self.back, x+ox, y+oy, w, h, name, H))
            for x in (b.glue_tab, b.glue_tab+b.body_d, b.glue_tab+b.body_d+b.body_w, b.glue_tab+2*b.body_d+b.body_w): out.append(f'<path d="M{x+ox} {H-oy}V{H-b.page_h+oy}" stroke="#2865ad" stroke-width="0.2" stroke-dasharray="2,1"/>')
            for y in (b.body_y, b.body_y+b.body_h): out.append(f'<path d="M{ox} {H-y-oy}H{W-ox}" stroke="#2865ad" stroke-width="0.2" stroke-dasharray="2,1"/>')
            out.append('</svg>'); Path(path).write_text("\n".join(out), encoding="utf-8")
            messagebox.showinfo("Saved", f"SVG saved to:\n{path}")
        except Exception as exc: messagebox.showerror("SVG export failed", str(exc))

    def save_pdf(self, pagesize):
        if Canvas is None: messagebox.showerror("Missing dependency", "Install ReportLab with: pip install -r requirements.txt"); return
        try:
            cols, rows, gap = int(self.cols.get()), int(self.rows.get()), float(self.gap.get())
            if cols < 1 or rows < 1 or gap < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid sheet", "Columns and rows must be positive whole numbers; gap must be non-negative."); return
        path = self._save_path("Save tuckbox PDF", ".pdf", [("PDF files", "*.pdf")])
        if not path: return
        try:
            b = self.box; pw, ph = pagesize; margin = 12*mm; sheet_w = cols*b.page_w + (cols-1)*gap; sheet_h = rows*b.page_h + (rows-1)*gap
            scale = min((pw-2*margin)/(sheet_w*mm), (ph-2*margin)/(sheet_h*mm)); ox = margin + (pw-2*margin-sheet_w*mm*scale)/2; oy = margin + (ph-2*margin-sheet_h*mm*scale)/2
            pdf = Canvas(path, pagesize=pagesize)
            def line(x1, y1, x2, y2, fold=False):
                pdf.setStrokeColorRGB(.16, .4, .68) if fold else pdf.setStrokeColorRGB(.08, .08, .08); pdf.setDash(3, 2) if fold else pdf.setDash(); pdf.line(x1, y1, x2, y2)
            def draw_one(px, py):
                def rect(x, y, w, h): pdf.rect(px+(x+b.bleed)*mm*scale, py+(y+b.bleed)*mm*scale, w*mm*scale, h*mm*scale, stroke=1, fill=0)
                for x, y, w, h, _ in b.panels(): rect(x, y, w, h)
                for x, y, w, h, _ in b.flaps(): rect(x, y, w, h)
                for x in (b.glue_tab, b.glue_tab+b.body_d, b.glue_tab+b.body_d+b.body_w, b.glue_tab+2*b.body_d+b.body_w): line(px+(x+b.bleed)*mm*scale, py, px+(x+b.bleed)*mm*scale, py+b.page_h*mm*scale, True)
                for y in (b.body_y, b.body_y+b.body_h): line(px, py+(y+b.bleed)*mm*scale, px+b.page_w*mm*scale, py+(y+b.bleed)*mm*scale, True)
            for row in range(rows):
                for col in range(cols): draw_one(ox+col*(b.page_w+gap)*mm*scale, oy+(rows-1-row)*(b.page_h+gap)*mm*scale)
            pdf.save(); messagebox.showinfo("Saved", f"PDF saved to:\n{path}")
        except Exception as exc: messagebox.showerror("PDF export failed", str(exc))


if __name__ == "__main__":
    App().mainloop()
