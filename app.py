"""MTG tuckbox generator with a consistent artwork coordinate system.

Artwork is always positioned relative to the actual front/back panel rectangle.
Preview, SVG, and PDF use the same panel origin and offset values.
"""
from __future__ import annotations

import base64
import mimetypes
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = ImageOps = ImageTk = None

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
except ImportError:
    A4 = letter = ImageReader = mm = Canvas = None


@dataclass
class Box:
    cards: int = 60
    card_w: float = 63.0
    card_h: float = 88.0
    thickness: float = 0.30
    clearance: float = 2.0
    bleed: float = 3.0
    glue: float = 12.0
    tuck: float = 25.0

    @property
    def panel_w(self): return self.cards * self.thickness + 2 * self.clearance
    @property
    def panel_d(self): return self.card_w + 2 * self.clearance
    @property
    def panel_h(self): return self.card_h + 2 * self.clearance
    @property
    def bottom_depth(self): return min(self.panel_d * .62, self.panel_h * .56)
    @property
    def dust_depth(self): return min(self.panel_d * .42, self.panel_h * .38)
    @property
    def body_y(self): return self.bottom_depth
    @property
    def cut_w(self): return self.glue + 2 * self.panel_d + 2 * self.panel_w
    @property
    def cut_h(self): return self.bottom_depth + self.panel_h + self.tuck
    @property
    def page_w(self): return self.cut_w + 2 * self.bleed
    @property
    def page_h(self): return self.cut_h + 2 * self.bleed

    def panels(self):
        x, y = self.glue, self.body_y
        return {
            "back": (x, y, self.panel_d, self.panel_h),
            "front": (x + self.panel_d + self.panel_w, y, self.panel_d, self.panel_h),
        }

    def all_panels(self):
        x, y = self.glue, self.body_y
        return [(x, y, self.panel_d, self.panel_h, "back"),
                (x + self.panel_d, y, self.panel_w, self.panel_h, "side"),
                (x + self.panel_d + self.panel_w, y, self.panel_d, self.panel_h, "front"),
                (x + 2 * self.panel_d + self.panel_w, y, self.panel_w, self.panel_h, "side")]

    def flaps(self):
        c, x, y = self, self.glue, self.body_y
        main, dust, shoulder = c.bottom_depth, c.dust_depth, min(6.0, c.panel_d / 7)
        front = x + c.panel_d + c.panel_w
        left_side, right_side = x + c.panel_d, x + 2 * c.panel_d + c.panel_w
        return [
            ([(x + shoulder, y), (x + c.panel_d - shoulder, y), (x + c.panel_d, y - main), (x, y - main)], "bottom"),
            ([(front + shoulder, y), (front + c.panel_d - shoulder, y), (front + c.panel_d, y - main), (front, y - main)], "bottom"),
            ([(left_side + 3, y), (left_side + c.panel_w - 3, y), (left_side + c.panel_w, y - dust + 4), (left_side + c.panel_w - 4, y - dust), (left_side + 4, y - dust), (left_side, y - dust + 4)], "dust"),
            ([(right_side + 3, y), (right_side + c.panel_w - 3, y), (right_side + c.panel_w, y - dust + 4), (right_side + c.panel_w - 4, y - dust), (right_side + 4, y - dust), (right_side, y - dust + 4)], "dust"),
            ([(x + 3, y + c.panel_h), (x + c.panel_d - 3, y + c.panel_h), (x + c.panel_d - 5, y + c.panel_h + dust), (x + 5, y + c.panel_h + dust)], "dust"),
            ([(front + 4, y + c.panel_h), (front + c.panel_d - 4, y + c.panel_h), (front + c.panel_d - 7, y + c.panel_h + c.tuck), (front + c.panel_d / 2 + 5, y + c.panel_h + c.tuck), (front + c.panel_d / 2, y + c.panel_h + c.tuck + 4), (front + c.panel_d / 2 - 5, y + c.panel_h + c.tuck), (front + 7, y + c.panel_h + c.tuck)], "tuck"),
            ([(left_side + 3, y + c.panel_h), (left_side + c.panel_w - 3, y + c.panel_h), (left_side + c.panel_w - 4, y + c.panel_h + dust), (left_side + 4, y + c.panel_h + dust)], "dust"),
            ([(right_side + 3, y + c.panel_h), (right_side + c.panel_w - 3, y + c.panel_h), (right_side + c.panel_w - 4, y + c.panel_h + dust), (right_side + 4, y + c.panel_h + dust)], "dust"),
        ]


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("MTG Tuckbox Generator")
        self.geometry("1240x820")
        self.minsize(1000, 680)
        self.box = Box()
        self.art_paths = {"front": None, "back": None}
        self.art_offsets = {"front": [0.0, 0.0], "back": [0.0, 0.0]}
        self.photos = []
        self.drag = None
        self.preview_scale = 1.0
        self.preview_origin = (0.0, 0.0)
        self.vars = {k: ttk.StringVar(value=str(v)) for k, v in {
            "cards": 60, "card_w": 63, "card_h": 88, "thickness": .30,
            "clearance": 2, "bleed": 3, "glue": 12, "tuck": 25}.items()}
        self.cols, self.rows, self.gap = ttk.StringVar(value="1"), ttk.StringVar(value="1"), ttk.StringVar(value="5")
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill=BOTH, expand=True)
        left = ttk.Frame(root, width=310); left.pack(side=LEFT, fill=Y, padx=(0, 12)); left.pack_propagate(False)
        right = ttk.Frame(root); right.pack(side=RIGHT, fill=BOTH, expand=True)
        ttk.Label(left, text="MTG Tuckbox Generator", font=("Segoe UI", 16, "bold"), bootstyle="primary").pack(anchor="w", pady=(0, 10))
        labels = {"cards":"Cards", "card_w":"Card width (mm)", "card_h":"Card height (mm)", "thickness":"Thickness/card (mm)", "clearance":"Clearance (mm)", "bleed":"Bleed (mm)", "glue":"Glue tab (mm)", "tuck":"Tuck flap depth (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(left); row.pack(fill=X, pady=2)
            ttk.Label(row, text=labels[key], width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(left, text="Apply dimensions", command=self.apply, bootstyle="primary").pack(fill=X, pady=(8, 10))
        ttk.Separator(left).pack(fill=X, pady=5)
        ttk.Label(left, text="Artwork placement", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)
        ttk.Button(left, text="Load front artwork", command=lambda: self.load_art("front"), bootstyle="secondary").pack(fill=X, pady=2)
        ttk.Button(left, text="Load back artwork", command=lambda: self.load_art("back"), bootstyle="secondary").pack(fill=X, pady=2)
        ttk.Button(left, text="Reset artwork positions", command=self.reset_art, bootstyle="link").pack(fill=X, pady=2)
        self.art_label = ttk.Label(left, text="No artwork loaded", wraplength=290); self.art_label.pack(anchor="w", pady=5)
        ttk.Label(left, text="Drag artwork inside its panel in the preview. Images are clipped to the exact panel bounds.", wraplength=290).pack(anchor="w", pady=3)
        ttk.Separator(left).pack(fill=X, pady=6)
        ttk.Label(left, text="Print sheet", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)
        for label, var in (("Columns", self.cols), ("Rows", self.rows), ("Gap (mm)", self.gap)):
            row = ttk.Frame(left); row.pack(fill=X, pady=2); ttk.Label(row, text=label, width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(left, text="Save PDF sheet — A4", command=lambda: self.save_pdf(A4), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(left, text="Save PDF sheet — Letter", command=lambda: self.save_pdf(letter), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(left, text="Save SVG dieline", command=self.save_svg, bootstyle="info").pack(fill=X, pady=(8, 2))
        self.info = ttk.Label(left, justify="left", wraplength=295); self.info.pack(anchor="w", pady=14)
        ttk.Label(right, text="Preview  •  black=cut  •  blue dashed=fold  •  red=trim", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 7))
        self.canvas = tk.Canvas(right, bg="#edf0f2", highlightthickness=1); self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.start_drag); self.canvas.bind("<B1-Motion>", self.move_drag); self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag", None))

    def apply(self):
        try:
            values = {k: float(v.get()) for k, v in self.vars.items()}; values["cards"] = int(values["cards"])
            if values["cards"] < 1 or values["bleed"] < 0 or any(values[k] <= 0 for k in values if k != "bleed"): raise ValueError
            self.box = Box(**values); self.redraw()
        except (ValueError, TypeError): messagebox.showerror("Invalid dimensions", "Enter positive numeric dimensions and at least one card.")

    def load_art(self, side):
        path = filedialog.askopenfilename(title=f"Choose {side} artwork", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        if not path: return
        if Image is None:
            messagebox.showerror("Missing dependency", "Install Pillow with: pip install -r requirements.txt"); return
        try:
            with Image.open(path) as image: image.verify()
        except Exception as exc:
            messagebox.showerror("Invalid image", f"Could not open the selected image:\n{exc}"); return
        self.art_paths[side] = path; self.art_offsets[side] = [0.0, 0.0]
        self.art_label.config(text=f"Front: {Path(self.art_paths['front']).name if self.art_paths['front'] else 'none'}\nBack: {Path(self.art_paths['back']).name if self.art_paths['back'] else 'none'}")
        self.redraw()

    def reset_art(self):
        self.art_offsets = {"front": [0.0, 0.0], "back": [0.0, 0.0]}; self.redraw()

    def page_xy(self, x, y):
        return (self.preview_origin[0] + (x + self.box.bleed) * self.preview_scale,
                self.preview_origin[1] + (self.box.page_h - y - self.box.bleed) * self.preview_scale)

    def panel_art_rect(self, side):
        x, y, w, h = self.box.panels()[side]
        ox, oy = self.art_offsets[side]
        return x + ox, y + oy, w, h

    def redraw(self):
        if not hasattr(self, "canvas"): return
        b = self.box; self.canvas.delete("all"); self.photos.clear()
        self.preview_scale = min(max(self.canvas.winfo_width() - 30, 100) / b.page_w, max(self.canvas.winfo_height() - 30, 100) / b.page_h)
        self.preview_origin = (15.0, 15.0)
        def polygon(points, fill="#fff"):
            coords = [n for point in points for n in self.page_xy(*point)]
            self.canvas.create_polygon(coords, fill=fill, outline="#111", width=2)
        for x, y, w, h, name in b.all_panels(): polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)], "#fff" if name in ("front", "back") else "#f4f5f6")
        for points, _kind in b.flaps(): polygon(points, "#f8f8f8")
        for x, y, w, h, name in b.all_panels():
            a, bb = self.page_xy(x+w/2, y+h/2); self.canvas.create_text(a, bb, text=name.upper(), fill="#555", font=("Segoe UI", 10, "bold"))
        for x in (b.glue, b.glue+b.panel_d, b.glue+b.panel_d+b.panel_w, b.glue+2*b.panel_d+b.panel_w):
            a, bb = self.page_xy(x, 0); c, d = self.page_xy(x, b.page_h); self.canvas.create_line(a, bb, c, d, fill="#2865ad", dash=(6,4))
        for y in (b.body_y, b.body_y+b.panel_h):
            a, bb = self.page_xy(0, y); c, d = self.page_xy(b.page_w, y); self.canvas.create_line(a, bb, c, d, fill="#2865ad", dash=(6,4))
        self.draw_art("front"); self.draw_art("back")
        for x, y in ((0,0), (b.cut_w,0), (0,b.cut_h), (b.cut_w,b.cut_h)):
            a, bb = self.page_xy(x, y); self.canvas.create_oval(a-3, bb-3, a+3, bb+3, outline="#c33")
        self.info.config(text=f"Inside: {b.panel_w:.2f} W × {b.panel_d:.2f} D × {b.panel_h:.2f} H mm\nDieline: {b.cut_w:.2f} × {b.cut_h:.2f} mm\nArtwork is aligned to front/back panels\nPrint at 100%; test-fold first.")

    def draw_art(self, side):
        path = self.art_paths[side]
        if not path or Image is None: return
        try:
            x, y, w, h = self.panel_art_rect(side)
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
            # Fit to the exact panel rectangle. This removes the old center/bleed mismatch.
            image = ImageOps.fit(image, (max(2, round(w*self.preview_scale)), max(2, round(h*self.preview_scale))), method=Image.Resampling.LANCZOS, centering=(.5, .5))
            photo = ImageTk.PhotoImage(image); self.photos.append(photo)
            a, bb = self.page_xy(x+w/2, y+h/2); self.canvas.create_image(a, bb, image=photo, anchor="center")
        except Exception as exc:
            self.info.config(text=f"Artwork preview failed: {exc}")

    def start_drag(self, event):
        for side, path in self.art_paths.items():
            if not path: continue
            x, y, w, h = self.panel_art_rect(side); a, bb = self.page_xy(x+w/2, y+h/2)
            if abs(event.x-a) <= w*self.preview_scale/2 and abs(event.y-bb) <= h*self.preview_scale/2:
                self.drag = (side, event.x, event.y); return

    def move_drag(self, event):
        if not self.drag: return
        side, px, py = self.drag
        self.art_offsets[side][0] += (event.x-px) / self.preview_scale
        self.art_offsets[side][1] -= (event.y-py) / self.preview_scale
        self.drag = (side, event.x, event.y); self.redraw()

    def svg_image(self, side, page_h):
        path = self.art_paths[side]
        if not path: return ""
        x, y, w, h = self.panel_art_rect(side); o = self.box.bleed
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        mime = mimetypes.guess_type(path)[0] or "image/png"
        clip_id = f"clip-{side}"
        return (f'<clipPath id="{clip_id}"><rect x="{x+o}" y="{page_h-y-o-h}" width="{w}" height="{h}"/></clipPath>'
                f'<image href="data:{mime};base64,{data}" x="{x+o}" y="{page_h-y-o-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})"/>')

    def save_svg(self):
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG files", "*.svg")])
        if not path: return
        try:
            b, W, H, o = self.box, self.box.page_w, self.box.page_h, self.box.bleed
            out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
            def poly(points, stroke="#111", dash=""):
                p = " ".join(f"{x+o},{H-y-o}" for x,y in points); extra = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<polygon points="{p}" fill="none" stroke="{stroke}" stroke-width=".25"{extra}/>')
            for x,y,w,h,_ in b.all_panels(): poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
            for points,_ in b.flaps(): poly(points)
            out += [self.svg_image("front", H), self.svg_image("back", H)]
            for x in (b.glue, b.glue+b.panel_d, b.glue+b.panel_d+b.panel_w, b.glue+2*b.panel_d+b.panel_w): out.append(f'<path d="M{x+o} {H-o}V{H-b.page_h+o}" fill="none" stroke="#2865ad" stroke-width=".2" stroke-dasharray="2,1"/>')
            for y in (b.body_y, b.body_y+b.panel_h): out.append(f'<path d="M{o} {H-y-o}H{W-o}" fill="none" stroke="#2865ad" stroke-width=".2" stroke-dasharray="2,1"/>')
            out.append("</svg>"); Path(path).write_text("\n".join(out), encoding="utf-8")
            messagebox.showinfo("Saved", f"SVG saved to:\n{path}")
        except Exception as exc: messagebox.showerror("SVG export failed", str(exc))

    def save_pdf(self, pagesize):
        if Canvas is None: messagebox.showerror("Missing dependency", "Install reportlab with: pip install -r requirements.txt"); return
        try:
            cols, rows, gap = int(self.cols.get()), int(self.rows.get()), float(self.gap.get())
            if cols < 1 or rows < 1 or gap < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid sheet", "Columns/rows must be positive integers and gap non-negative."); return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not path: return
        try:
            b, pw, ph = self.box, pagesize[0], pagesize[1]; margin = 12*mm
            sheet_w = cols*b.page_w + (cols-1)*gap; sheet_h = rows*b.page_h + (rows-1)*gap
            scale = min((pw-2*margin)/(sheet_w*mm), (ph-2*margin)/(sheet_h*mm))
            left = margin + (pw-2*margin-sheet_w*mm*scale)/2; bottom = margin + (ph-2*margin-sheet_h*mm*scale)/2
            pdf = Canvas(path, pagesize=pagesize)
            def draw_one(px, py):
                def P(x,y): return px+(x+b.bleed)*mm*scale, py+(y+b.bleed)*mm*scale
                def polygon(points):
                    q = pdf.beginPath(); q.moveTo(*P(*points[0]))
                    for point in points[1:]: q.lineTo(*P(*point))
                    q.close(); pdf.setStrokeColorRGB(.08,.08,.08); pdf.setDash(); pdf.drawPath(q, stroke=1, fill=0)
                for x,y,w,h,_ in b.all_panels(): polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
                for points,_ in b.flaps(): polygon(points)
                for side in ("back", "front"):
                    path_img = self.art_paths[side]
                    if path_img:
                        x,y,w,h = self.panel_art_rect(side)
                        try:
                            # ReportLab's origin is bottom-left; P() is the panel's bottom-left.
                            pdf.drawImage(ImageReader(path_img), *P(x, y), width=w*mm*scale, height=h*mm*scale, preserveAspectRatio=False, mask="auto")
                        except Exception as exc: raise RuntimeError(f"Could not place {side} artwork: {exc}") from exc
                pdf.setStrokeColorRGB(.16,.4,.68); pdf.setDash(3,2)
                for x in (b.glue, b.glue+b.panel_d, b.glue+b.panel_d+b.panel_w, b.glue+2*b.panel_d+b.panel_w): pdf.line(*P(x,0), *P(x,b.page_h))
                for y in (b.body_y, b.body_y+b.panel_h): pdf.line(*P(0,y), *P(b.page_w,y))
                pdf.setDash()
            for row in range(rows):
                for col in range(cols): draw_one(left+col*(b.page_w+gap)*mm*scale, bottom+(rows-1-row)*(b.page_h+gap)*mm*scale)
            pdf.save(); messagebox.showinfo("Saved", f"PDF saved to:\n{path}")
        except Exception as exc: messagebox.showerror("PDF export failed", str(exc))


if __name__ == "__main__": App().mainloop()
