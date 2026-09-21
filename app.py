"""MTG tuckbox generator inspired by the clean red-cut/white-score Jumpstart templates."""
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
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas
except ImportError:
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
    tuck: float = 25.0
    notch: float = 11.0

    @property
    def width(self): return self.cards * self.thickness + 2 * self.clearance
    @property
    def depth(self): return self.card_w + 2 * self.clearance
    @property
    def height(self): return self.card_h + 2 * self.clearance
    @property
    def bottom_flap(self): return min(self.depth * .62, self.height * .56)
    @property
    def dust_flap(self): return min(self.depth * .42, self.height * .38)
    @property
    def body_y(self): return self.bottom_flap
    @property
    def cut_width(self): return self.glue + 2 * self.depth + 2 * self.width
    @property
    def cut_height(self): return self.bottom_flap + self.height + self.tuck
    @property
    def page_width(self): return self.cut_width + 2 * self.bleed
    @property
    def page_height(self): return self.cut_height + 2 * self.bleed

    def panels(self):
        x, y = self.glue, self.body_y
        return {
            "back": (x, y, self.depth, self.height),
            "front": (x + self.depth + self.width, y, self.depth, self.height),
        }

    def body_panels(self):
        x, y = self.glue, self.body_y
        return [(x, y, self.depth, self.height, "back"),
                (x + self.depth, y, self.width, self.height, "side"),
                (x + self.depth + self.width, y, self.depth, self.height, "front"),
                (x + 2 * self.depth + self.width, y, self.width, self.height, "side")]

    def flaps(self):
        """Return shaped flap polygons and their score seam.

        The layout follows the practical Jumpstart-style construction: a side
        glue tab, front/back panels, short dust flaps, broad bottom flaps,
        and a top tuck flap with a thumb notch.
        """
        x, y = self.glue, self.body_y
        shoulder = min(6.0, self.depth / 7)
        dust = self.dust_flap
        front = x + self.depth + self.width
        left_side = x + self.depth
        right_side = x + 2 * self.depth + self.width
        top = y + self.height
        return [
            ([(x + shoulder, y), (x + self.depth - shoulder, y),
              (x + self.depth, y - self.bottom_flap), (x, y - self.bottom_flap)], "cut"),
            ([(front + shoulder, y), (front + self.depth - shoulder, y),
              (front + self.depth, y - self.bottom_flap), (front, y - self.bottom_flap)], "cut"),
            ([(left_side + 3, y), (left_side + self.width - 3, y),
              (left_side + self.width, y - dust + 4), (left_side + self.width - 4, y - dust),
              (left_side + 4, y - dust), (left_side, y - dust + 4)], "cut"),
            ([(right_side + 3, y), (right_side + self.width - 3, y),
              (right_side + self.width, y - dust + 4), (right_side + self.width - 4, y - dust),
              (right_side + 4, y - dust), (right_side, y - dust + 4)], "cut"),
            ([(x + 3, top), (x + self.depth - 3, top),
              (x + self.depth - 5, top + dust), (x + 5, top + dust)], "cut"),
            ([(front + 4, top), (front + self.depth - 4, top),
              (front + self.depth - 7, top + self.tuck),
              (front + self.depth / 2 + self.notch / 2, top + self.tuck),
              (front + self.depth / 2 + self.notch / 2, top + self.tuck - 4),
              (front + self.depth / 2 - self.notch / 2, top + self.tuck - 4),
              (front + self.depth / 2 - self.notch / 2, top + self.tuck),
              (front + 7, top + self.tuck)], "cut"),
            ([(left_side + 3, top), (left_side + self.width - 3, top),
              (left_side + self.width - 4, top + dust), (left_side + 4, top + dust)], "cut"),
            ([(right_side + 3, top), (right_side + self.width - 3, top),
              (right_side + self.width - 4, top + dust), (right_side + 4, top + dust)], "cut"),
        ]


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("MTG Tuckbox Generator")
        self.geometry("1240x820")
        self.minsize(1000, 680)
        self.dark = False
        self.box = Box()
        self.art_paths = {"front": None, "back": None}
        self.art_offsets = {"front": [0.0, 0.0], "back": [0.0, 0.0]}
        self.photos = []
        self.drag = None
        self.preview_scale = 1.0
        self.preview_origin = (0.0, 0.0)
        defaults = {"cards": 22, "card_w": 63, "card_h": 88, "thickness": .30,
                    "clearance": 2, "bleed": 3, "glue": 12, "tuck": 25, "notch": 11}
        self.vars = {key: ttk.StringVar(value=str(value)) for key, value in defaults.items()}
        self.cols = ttk.StringVar(value="1")
        self.rows = ttk.StringVar(value="1")
        self.gap = ttk.StringVar(value="5")
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill=BOTH, expand=True)
        self.sidebar = ttk.Frame(root, width=315); self.sidebar.pack(side=LEFT, fill=Y, padx=(0, 12)); self.sidebar.pack_propagate(False)
        right = ttk.Frame(root); right.pack(side=RIGHT, fill=BOTH, expand=True)
        header = ttk.Frame(self.sidebar); header.pack(fill=X, pady=(0, 10))
        ttk.Label(header, text="MTG Tuckbox Generator", font=("Segoe UI", 16, "bold"), bootstyle="primary").pack(side=LEFT)
        self.theme_button = ttk.Button(header, text="☾", width=3, command=self.toggle_theme, bootstyle="secondary-outline"); self.theme_button.pack(side=RIGHT)

        self.size_box = ttk.Labelframe(self.sidebar, text="Sizing options", padding=8, bootstyle="primary")
        self.size_toggle = ttk.Button(self.sidebar, text="Show sizing options", command=self.toggle_sizing, bootstyle="link")
        self.size_toggle.pack(anchor="w", pady=(0, 5))
        labels = {"cards":"Cards per pack", "card_w":"Card width (mm)", "card_h":"Card height (mm)", "thickness":"Thickness/card (mm)", "clearance":"Clearance (mm)", "bleed":"Bleed (mm)", "glue":"Glue tab (mm)", "tuck":"Tuck flap depth (mm)", "notch":"Thumb notch (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(self.size_box); row.pack(fill=X, pady=2)
            ttk.Label(row, text=labels[key], width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(self.size_box, text="Apply dimensions", command=self.apply, bootstyle="primary").pack(fill=X, pady=(7, 0))
        # Sizing is intentionally hidden on first launch.

        art = ttk.Labelframe(self.sidebar, text="Artwork placement", padding=8, bootstyle="secondary"); art.pack(fill=X, pady=6)
        ttk.Button(art, text="Load front artwork", command=lambda: self.load_art("front"), bootstyle="secondary").pack(fill=X, pady=2)
        ttk.Button(art, text="Load back artwork", command=lambda: self.load_art("back"), bootstyle="secondary").pack(fill=X, pady=2)
        ttk.Button(art, text="Reset artwork positions", command=self.reset_art, bootstyle="link").pack(fill=X, pady=2)
        self.art_label = ttk.Label(art, text="No artwork loaded", wraplength=285); self.art_label.pack(anchor="w", pady=4)
        ttk.Label(art, text="Drag directly on the artwork, not the panel background.", wraplength=285).pack(anchor="w")

        sheet = ttk.Labelframe(self.sidebar, text="Print sheet", padding=8, bootstyle="secondary"); sheet.pack(fill=X, pady=6)
        for label, var in (("Columns", self.cols), ("Rows", self.rows), ("Gap (mm)", self.gap)):
            row = ttk.Frame(sheet); row.pack(fill=X, pady=2); ttk.Label(row, text=label, width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(sheet, text="Save PDF sheet — A4", command=lambda: self.save_pdf(A4), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(sheet, text="Save PDF sheet — Letter", command=lambda: self.save_pdf(letter), bootstyle="success").pack(fill=X, pady=2)
        ttk.Button(sheet, text="Save SVG dieline", command=self.save_svg, bootstyle="info").pack(fill=X, pady=(6, 2))
        self.info = ttk.Label(self.sidebar, justify="left", wraplength=295); self.info.pack(anchor="w", pady=12)

        ttk.Label(right, text="Preview  •  red=cut  •  white/dark=score  •  blue=artwork", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 7))
        self.canvas = tk.Canvas(right, bg="#edf0f2", highlightthickness=1); self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.move_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _event: setattr(self, "drag", None))

    def toggle_sizing(self):
        if self.size_box.winfo_ismapped():
            self.size_box.pack_forget(); self.size_toggle.config(text="Show sizing options")
        else:
            self.size_box.pack(fill=X, before=self.size_toggle, pady=(0, 8)); self.size_toggle.config(text="Hide sizing options")

    def toggle_theme(self):
        self.dark = not self.dark
        self.style.theme_use("darkly" if self.dark else "flatly")
        self.theme_button.config(text="☀" if self.dark else "☾")
        self.canvas.config(bg="#1f2329" if self.dark else "#edf0f2")
        self.redraw()

    def apply(self):
        try:
            values = {key: float(value.get()) for key, value in self.vars.items()}; values["cards"] = int(values["cards"])
            if values["cards"] < 1 or values["bleed"] < 0 or any(values[key] <= 0 for key in values if key != "bleed"): raise ValueError
            self.box = Box(**values); self.redraw()
        except (ValueError, TypeError):
            messagebox.showerror("Invalid dimensions", "Enter positive numeric dimensions and at least one card.")

    def load_art(self, side):
        path = filedialog.askopenfilename(title=f"Choose {side} artwork", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        if not path: return
        if Image is None:
            messagebox.showerror("Missing dependency", "Install Pillow with: pip install -r requirements.txt"); return
        try:
            with Image.open(path) as image: image.verify()
        except Exception as exc:
            messagebox.showerror("Invalid image", f"Could not open image:\n{exc}"); return
        self.art_paths[side] = path; self.art_offsets[side] = [0.0, 0.0]
        self.art_label.config(text=f"Front: {Path(self.art_paths['front']).name if self.art_paths['front'] else 'none'}\nBack: {Path(self.art_paths['back']).name if self.art_paths['back'] else 'none'}")
        self.redraw()

    def reset_art(self):
        self.art_offsets = {"front": [0.0, 0.0], "back": [0.0, 0.0]}; self.redraw()

    def page_xy(self, x, y):
        return (self.preview_origin[0] + (x + self.box.bleed) * self.preview_scale,
                self.preview_origin[1] + (self.box.page_height - y - self.box.bleed) * self.preview_scale)

    def artwork_rect(self, side):
        x, y, width, height = self.box.panels()[side]
        ox, oy = self.art_offsets[side]
        return x + ox, y + oy, width, height

    def redraw(self):
        if not hasattr(self, "canvas"): return
        b = self.box; self.canvas.delete("all"); self.photos.clear()
        self.preview_scale = min(max(self.canvas.winfo_width() - 30, 100) / b.page_width, max(self.canvas.winfo_height() - 30, 100) / b.page_height)
        self.preview_origin = (15.0, 15.0)
        cut = "#dc3545" if not self.dark else "#ff6675"
        score = "#ffffff" if not self.dark else "#adb5bd"
        panel_fill = "#ffffff" if not self.dark else "#30343b"
        side_fill = "#f0f2f4" if not self.dark else "#272b31"
        def polygon(points, fill, outline=cut, width=2):
            coords = [value for point in points for value in self.page_xy(*point)]
            self.canvas.create_polygon(coords, fill=fill, outline=outline, width=width)
        for x, y, width, height, name in b.body_panels():
            polygon([(x,y),(x+width,y),(x+width,y+height),(x,y+height)], panel_fill if name in ("front", "back") else side_fill)
        for points, _kind in b.flaps(): polygon(points, side_fill)
        for x, y, width, height, name in b.body_panels():
            a, bb = self.page_xy(x + width/2, y + height/2)
            self.canvas.create_text(a, bb, text=name.upper(), fill="#6c757d", font=("Segoe UI", 10, "bold"))
        # white/grey score lines match the reference templates while remaining visible in dark mode.
        for x in (b.glue, b.glue+b.depth, b.glue+b.depth+b.width, b.glue+2*b.depth+b.width):
            a, bb = self.page_xy(x, 0); c, d = self.page_xy(x, b.page_height); self.canvas.create_line(a, bb, c, d, fill=score, dash=(7, 4), width=2)
        for y in (b.body_y, b.body_y+b.height):
            a, bb = self.page_xy(0, y); c, d = self.page_xy(b.page_width, y); self.canvas.create_line(a, bb, c, d, fill=score, dash=(7, 4), width=2)
        self.draw_art("front"); self.draw_art("back")
        for x, y in ((0,0), (b.cut_width,0), (0,b.cut_height), (b.cut_width,b.cut_height)):
            a, bb = self.page_xy(x, y); self.canvas.create_line(a-5, bb, a+5, bb, fill=cut); self.canvas.create_line(a, bb-5, a, bb+5, fill=cut)
        self.info.config(text=f"Cards per pack: {b.cards}\nInside: {b.width:.2f} W × {b.depth:.2f} D × {b.height:.2f} H mm\nDieline: {b.cut_width:.2f} × {b.cut_height:.2f} mm\nRed=cut • white/dark=score • drag artwork directly\nPrint at 100%; test-fold first.")

    def draw_art(self, side):
        path = self.art_paths[side]
        if not path or Image is None: return
        try:
            x, y, width, height = self.artwork_rect(side)
            with Image.open(path) as source: image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(image, (max(2, round(width*self.preview_scale)), max(2, round(height*self.preview_scale))), method=Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image); self.photos.append(photo)
            center_x, center_y = self.page_xy(x + width/2, y + height/2)
            self.canvas.create_image(center_x, center_y, image=photo, anchor="center", tags=("artwork", side))
        except Exception as exc:
            self.info.config(text=f"Artwork preview failed: {exc}")

    def start_drag(self, event):
        # Use actual canvas hit-testing, so the image itself—not an approximate
        # panel rectangle—is the drag target.
        item = self.canvas.find_withtag("current")
        if not item: return
        tags = self.canvas.gettags(item[0])
        for side in ("front", "back"):
            if side in tags:
                self.drag = (side, event.x, event.y); self.canvas.configure(cursor="fleur"); return

    def move_drag(self, event):
        if not self.drag: return
        side, previous_x, previous_y = self.drag
        self.art_offsets[side][0] += (event.x - previous_x) / self.preview_scale
        self.art_offsets[side][1] -= (event.y - previous_y) / self.preview_scale
        self.drag = (side, event.x, event.y); self.redraw()

    def svg_art(self, side):
        path = self.art_paths[side]
        if not path: return ""
        x, y, width, height = self.artwork_rect(side); o = self.box.bleed; H = self.box.page_height
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        mime = mimetypes.guess_type(path)[0] or "image/png"; clip_id = f"art-clip-{side}"
        return (f'<clipPath id="{clip_id}"><rect x="{x+o}" y="{H-y-o-height}" width="{width}" height="{height}"/></clipPath>'
                f'<image href="data:{mime};base64,{data}" x="{x+o}" y="{H-y-o-height}" width="{width}" height="{height}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})"/>')

    def save_svg(self):
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG files", "*.svg")])
        if not path: return
        try:
            b, W, H, o = self.box, self.box.page_width, self.box.page_height, self.box.bleed
            out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
            def polygon(points, stroke="#dc3545", dash=""):
                points_text = " ".join(f"{x+o},{H-y-o}" for x,y in points)
                dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<polygon points="{points_text}" fill="none" stroke="{stroke}" stroke-width=".25"{dash_attr}/>')
            for x,y,width,height,_ in b.body_panels(): polygon([(x,y),(x+width,y),(x+width,y+height),(x,y+height)])
            for points,_ in b.flaps(): polygon(points)
            out.extend([self.svg_art("front"), self.svg_art("back")])
            for x in (b.glue, b.glue+b.depth, b.glue+b.depth+b.width, b.glue+2*b.depth+b.width):
                out.append(f'<path d="M{x+o} {H-o}V{H-b.page_height+o}" fill="none" stroke="#ffffff" stroke-width=".2" stroke-dasharray="2,1"/>')
            for y in (b.body_y, b.body_y+b.height): out.append(f'<path d="M{o} {H-y-o}H{W-o}" fill="none" stroke="#ffffff" stroke-width=".2" stroke-dasharray="2,1"/>')
            out.append("</svg>"); Path(path).write_text("\n".join(out), encoding="utf-8")
            messagebox.showinfo("Saved", f"SVG saved to:\n{path}")
        except Exception as exc: messagebox.showerror("SVG export failed", str(exc))

    def save_pdf(self, pagesize):
        if Canvas is None: messagebox.showerror("Missing dependency", "Install reportlab with: pip install -r requirements.txt"); return
        try:
            columns, rows, gap = int(self.cols.get()), int(self.rows.get()), float(self.gap.get())
            if columns < 1 or rows < 1 or gap < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid sheet", "Columns/rows must be positive integers and gap non-negative."); return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not path: return
        try:
            b, page_w, page_h = self.box, pagesize[0], pagesize[1]; margin = 12*mm
            sheet_w = columns*b.page_width + (columns-1)*gap; sheet_h = rows*b.page_height + (rows-1)*gap
            scale = min((page_w-2*margin)/(sheet_w*mm), (page_h-2*margin)/(sheet_h*mm))
            left = margin + (page_w-2*margin-sheet_w*mm*scale)/2; bottom = margin + (page_h-2*margin-sheet_h*mm*scale)/2
            pdf = Canvas(path, pagesize=pagesize)
            def draw_one(px, py):
                def P(x,y): return px+(x+b.bleed)*mm*scale, py+(y+b.bleed)*mm*scale
                def polygon(points):
                    path_obj = pdf.beginPath(); path_obj.moveTo(*P(*points[0]))
                    for point in points[1:]: path_obj.lineTo(*P(*point))
                    path_obj.close(); pdf.setStrokeColorRGB(.86,.10,.18); pdf.setDash(); pdf.drawPath(path_obj, stroke=1, fill=0)
                for x,y,width,height,_ in b.body_panels(): polygon([(x,y),(x+width,y),(x+width,y+height),(x,y+height)])
                for points,_ in b.flaps(): polygon(points)
                if ImageReader:
                    for side in ("back", "front"):
                        if self.art_paths[side]:
                            x,y,width,height = self.artwork_rect(side)
                            pdf.drawImage(ImageReader(self.art_paths[side]), *P(x,y), width=width*mm*scale, height=height*mm*scale, preserveAspectRatio=False, mask="auto")
                pdf.setStrokeColorRGB(1, 1, 1); pdf.setDash(3, 2)
                for x in (b.glue, b.glue+b.depth, b.glue+b.depth+b.width, b.glue+2*b.depth+b.width): pdf.line(*P(x,0), *P(x,b.page_height))
                for y in (b.body_y, b.body_y+b.height): pdf.line(*P(0,y), *P(b.page_width,y))
                pdf.setDash()
            for row in range(rows):
                for column in range(columns): draw_one(left+column*(b.page_width+gap)*mm*scale, bottom+(rows-1-row)*(b.page_height+gap)*mm*scale)
            pdf.save(); messagebox.showinfo("Saved", f"PDF saved to:\n{path}")
        except Exception as exc: messagebox.showerror("PDF export failed", str(exc))


if __name__ == "__main__":
    App().mainloop()
