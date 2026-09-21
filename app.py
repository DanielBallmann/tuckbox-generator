"""MTG tuckbox generator with single-box and multi-box print-sheet exports."""
from __future__ import annotations

import base64
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
    from reportlab.pdfgen import canvas as pdf_canvas
except ImportError:
    A4 = letter = mm = pdf_canvas = None

PRESETS = {"60 cards": 60, "75 cards": 75, "90 cards": 90, "100 cards": 100}
PROFILES = {"Unsleeved": (0.30, 2.0), "Standard sleeves": (0.65, 2.5), "Thick sleeves": (0.85, 3.0)}


@dataclass
class Config:
    cards: int = 60
    card_w: float = 63.0
    card_h: float = 88.0
    thickness: float = 0.30
    clearance: float = 2.0
    bleed: float = 3.0
    glue: float = 12.0
    tuck: float = 25.0

    @property
    def width(self): return self.cards * self.thickness + 2 * self.clearance
    @property
    def depth(self): return self.card_w + 2 * self.clearance
    @property
    def height(self): return self.card_h + 2 * self.clearance
    @property
    def bottom(self): return self.height * .72
    @property
    def side_flap(self): return self.height * .34
    @property
    def total_w(self): return self.glue + self.depth + self.width + self.depth + self.width
    @property
    def total_h(self): return self.bottom + self.height + self.tuck


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Tuckbox Generator")
        self.geometry("1300x860")
        self.minsize(1080, 720)
        self.cfg = Config()
        self.front_path = self.back_path = None
        self.art = {"front": [0.0, 0.0, 1.0], "back": [0.0, 0.0, 1.0]}
        self.drag = None
        self.scale = 1.0
        self.origin = (0, 0)
        self._photos = []
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill="both", expand=True)
        controls = ttk.Frame(root, width=315); controls.pack(side="left", fill="y", padx=(0, 12)); controls.pack_propagate(False)
        pane = ttk.Frame(root); pane.pack(side="right", fill="both", expand=True)
        ttk.Label(controls, text="Tuckbox settings", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.preset = tk.StringVar(value="60 cards"); self.profile = tk.StringVar(value="Unsleeved")
        for label, var, values in [("Deck preset", self.preset, list(PRESETS)), ("Sleeve profile", self.profile, list(PROFILES))]:
            row = ttk.Frame(controls); row.pack(fill="x", pady=4); ttk.Label(row, text=label, width=19).pack(side="left")
            box = ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=15); box.pack(side="right")
            box.bind("<<ComboboxSelected>>", lambda _e: self.apply_preset())
        self.vars = {k: tk.StringVar(value=str(v)) for k, v in {"cards": 60, "card_w": 63, "card_h": 88, "thickness": .30, "clearance": 2, "bleed": 3, "glue": 12, "tuck": 25}.items()}
        labels = {"cards":"Cards", "card_w":"Card width (mm)", "card_h":"Card height (mm)", "thickness":"Stack thickness/card", "clearance":"Clearance (mm)", "bleed":"Bleed (mm)", "glue":"Glue tab (mm)", "tuck":"Top tuck depth (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(controls); row.pack(fill="x", pady=2); ttk.Label(row, text=labels[key], width=20).pack(side="left"); ttk.Entry(row, textvariable=var, width=11).pack(side="right")
        ttk.Button(controls, text="Apply settings", command=self.apply).pack(fill="x", pady=(7, 9))
        ttk.Separator(controls).pack(fill="x", pady=5)
        ttk.Label(controls, text="Artwork (drag in preview)", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=7)
        ttk.Button(controls, text="Choose front artwork", command=lambda: self.choose("front")).pack(fill="x", pady=2)
        ttk.Button(controls, text="Choose back artwork", command=lambda: self.choose("back")).pack(fill="x", pady=2)
        self.art_label = ttk.Label(controls, text="No artwork selected", wraplength=295); self.art_label.pack(anchor="w", pady=5)
        ttk.Button(controls, text="Reset artwork positions", command=self.reset_art).pack(fill="x", pady=2)
        ttk.Separator(controls).pack(fill="x", pady=8)
        ttk.Label(controls, text="Print sheet", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.sheet_cols = tk.StringVar(value="1"); self.sheet_rows = tk.StringVar(value="1"); self.sheet_gap = tk.StringVar(value="5")
        for text, var in [("Columns", self.sheet_cols), ("Rows", self.sheet_rows), ("Gap (mm)", self.sheet_gap)]:
            row = ttk.Frame(controls); row.pack(fill="x", pady=2); ttk.Label(row, text=text, width=19).pack(side="left"); ttk.Entry(row, textvariable=var, width=11).pack(side="right")
        ttk.Label(controls, text="Sheet export repeats the dieline in a grid and auto-fits it to the selected paper.", wraplength=295).pack(anchor="w", pady=4)
        ttk.Button(controls, text="Export multi-box PDF (A4)", command=lambda: self.export_pdf(A4, "A4", True)).pack(fill="x", pady=2)
        ttk.Button(controls, text="Export multi-box PDF (Letter)", command=lambda: self.export_pdf(letter, "Letter", True)).pack(fill="x", pady=2)
        ttk.Button(controls, text="Export single-box SVG", command=self.export_svg).pack(fill="x", pady=(8, 2))
        ttk.Button(controls, text="Export single-box PDF (A4)", command=lambda: self.export_pdf(A4, "A4", False)).pack(fill="x", pady=2)
        self.info = ttk.Label(controls, justify="left", wraplength=295); self.info.pack(anchor="w", pady=14)
        ttk.Label(pane, text="Preview — black solid=cut, blue dashed=fold, red=trim marks", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 8))
        self.canvas = tk.Canvas(pane, bg="#edf0f2", highlightthickness=1); self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw()); self.canvas.bind("<ButtonPress-1>", self.start_drag); self.canvas.bind("<B1-Motion>", self.move_drag); self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag", None))

    def apply_preset(self):
        self.vars["cards"].set(str(PRESETS[self.preset.get()])); thickness, clearance = PROFILES[self.profile.get()]
        self.vars["thickness"].set(str(thickness)); self.vars["clearance"].set(str(clearance)); self.apply()

    def apply(self):
        try:
            d = {k: float(v.get()) for k, v in self.vars.items()}; d["cards"] = int(d["cards"])
            if d["cards"] < 1 or any(d[k] <= 0 for k in ("card_w", "card_h", "thickness", "clearance", "glue", "tuck")) or d["bleed"] < 0: raise ValueError
            self.cfg = Config(**d); self.redraw()
        except (ValueError, TypeError): messagebox.showerror("Invalid settings", "Use positive dimensions and at least one card.")

    def choose(self, side):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")])
        if path:
            setattr(self, side + "_path", path); self.art_label.config(text=f"Front: {os.path.basename(self.front_path) if self.front_path else 'none'}\nBack: {os.path.basename(self.back_path) if self.back_path else 'none'}"); self.redraw()

    def reset_art(self): self.art = {"front": [0, 0, 1], "back": [0, 0, 1]}; self.redraw()

    def panels(self):
        c = self.cfg; x, y = c.glue, c.bottom
        return [(x, y, c.depth, c.height, "back"), (x+c.depth, y, c.width, c.height, "side"), (x+c.depth+c.width, y, c.depth, c.height, "front"), (x+c.depth*2+c.width, y, c.width, c.height, "side")]

    def flaps(self):
        c = self.cfg; x, y = c.glue, c.bottom
        return [(x, y-c.bottom, c.depth, c.bottom), (x+c.depth+c.width, y-c.bottom, c.depth, c.bottom), (x+c.depth, y-c.side_flap, c.width, c.side_flap), (x+c.depth*2+c.width, y-c.side_flap, c.width, c.side_flap), (x, y+c.height, c.depth, c.tuck), (x+c.depth+c.width, y+c.height, c.depth, c.side_flap), (x+c.depth, y+c.height, c.width, c.side_flap), (x+c.depth*2+c.width, y+c.height, c.width, c.side_flap)]

    def redraw(self):
        if not hasattr(self, "canvas"): return
        self.canvas.delete("all"); self._photos.clear(); c = self.cfg
        usable_w, usable_h = max(self.canvas.winfo_width()-40, 100), max(self.canvas.winfo_height()-40, 100)
        self.scale = min(usable_w/(c.total_w+2*c.bleed), usable_h/(c.total_h+2*c.bleed)); self.origin = (20+c.bleed*self.scale, 20+c.bleed*self.scale)
        def xy(x, y): return self.origin[0]+x*self.scale, self.origin[1]+(c.total_h-y)*self.scale
        def box(x, y, w, h, fill="#fff", outline="#222"):
            a,b=xy(x,y); d,e=xy(x+w,y+h); self.canvas.create_rectangle(a,e,d,b,fill=fill,outline=outline,width=2)
        for x,y,w,h,label in self.panels(): box(x,y,w,h,"#fff" if label in ("front","back") else "#f5f6f7")
        for x,y,w,h in self.flaps(): box(x,y,w,h,"#f8f8f8")
        for x in [c.glue, c.glue+c.depth, c.glue+c.depth+c.width, c.glue+c.depth*2+c.width]:
            a,b=xy(x,0); d,e=xy(x,c.total_h); self.canvas.create_line(a,b,d,e,fill="#2865ad",dash=(7,5))
        for y in [c.bottom, c.bottom+c.height]:
            a,b=xy(0,y); d,e=xy(c.total_w,y); self.canvas.create_line(a,b,d,e,fill="#2865ad",dash=(7,5))
        self.draw_art("front", self.front_path, c.glue+c.depth+c.width, c.bottom, c.depth, c.height, xy); self.draw_art("back", self.back_path, c.glue, c.bottom, c.depth, c.height, xy)
        for x,y in [(0,0),(c.total_w,0),(0,c.total_h),(c.total_w,c.total_h)]: a,b=xy(x,y); self.canvas.create_oval(a-3,b-3,a+3,b+3,outline="#c33")
        try: cols, rows, gap = int(self.sheet_cols.get()), int(self.sheet_rows.get()), float(self.sheet_gap.get())
        except ValueError: cols, rows, gap = 1, 1, 5
        self.info.config(text=f"Internal: {c.width:.2f} W × {c.depth:.2f} D × {c.height:.2f} H mm\nDieline: {c.total_w:.2f} × {c.total_h:.2f} mm\nSheet: {max(cols,1)} × {max(rows,1)} boxes, {max(gap,0):.1f} mm gap\nPrint at 100%; make a test cut.")

    def draw_art(self, side, path, x, y, w, h, xy):
        if not path or Image is None: return
        try:
            img = ImageOps.exif_transpose(Image.open(path)).convert("RGB"); zoom, ox, oy = self.art[side]
            img.thumbnail((max(20,int(w*self.scale*zoom)), max(20,int(h*self.scale*zoom))), Image.Resampling.LANCZOS); photo=ImageTk.PhotoImage(img); self._photos.append(photo)
            a,b=xy(x+w/2+ox*w,y+h/2+oy*h); self.canvas.create_image(a,b,image=photo,anchor="center")
        except Exception: pass

    def start_drag(self, event):
        c=self.cfg
        for side,path,x,y,w,h in [("front",self.front_path,c.glue+c.depth+c.width,c.bottom,c.depth,c.height),("back",self.back_path,c.glue,c.bottom,c.depth,c.height)]:
            if path:
                cx=self.origin[0]+(x+w/2+self.art[side][0]*w)*self.scale; cy=self.origin[1]+(c.total_h-(y+h/2+self.art[side][1]*h))*self.scale
                if abs(event.x-cx)<w*self.scale/2 and abs(event.y-cy)<h*self.scale/2: self.drag=(side,event.x,event.y); return
    def move_drag(self,event):
        if not self.drag:return
        side,px,py=self.drag; self.art[side][0]+=(event.x-px)/(self.scale*self.cfg.depth); self.art[side][1]-=(event.y-py)/(self.scale*self.cfg.height); self.drag=(side,event.x,event.y); self.redraw()

    def artwork_svg(self, path, x, y, w, h, side, page_h):
        if not path: return ""
        try: data=base64.b64encode(Path(path).read_bytes()).decode(); ext=Path(path).suffix.lower().replace('.','') or 'png'; z,ox,oy=self.art[side]
        except OSError: return ""
        return f'<image href="data:image/{ext};base64,{data}" x="{x+ox*w-w*z/2+w/2}" y="{page_h-(y+oy*h-h*z/2+h/2)}" width="{w*z}" height="{h*z}" preserveAspectRatio="xMidYMid meet"/>'

    def export_svg(self):
        path=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG", "*.svg")])
        if not path:return
        c=self.cfg; W,H=c.total_w+2*c.bleed,c.total_h+2*c.bleed; ox=oy=c.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
        def r(x,y,w,h,fold=False): out.append(f'<rect x="{x+ox}" y="{H-y-oy-h}" width="{w}" height="{h}" fill="none" stroke="{"#2865ad" if fold else "#111"}" stroke-width=".25" {"stroke-dasharray=\"2,1\"" if fold else ""}/>')
        for x,y,w,h,_ in self.panels(): r(x,y,w,h)
        for x,y,w,h in self.flaps(): r(x,y,w,h)
        for x,y,w,h,side in self.panels():
            if side in ("front","back"): out.append(self.artwork_svg(self.front_path if side=="front" else self.back_path,x+ox,y+oy,w,h,H))
        for x in [c.glue,c.glue+c.depth,c.glue+c.depth+c.width,c.glue+c.depth*2+c.width]: out.append(f'<path d="M{x+ox} {H-oy}V{H-c.total_h-oy}" stroke="#2865ad" stroke-width=".2" stroke-dasharray="2,1"/>')
        for y in [c.bottom,c.bottom+c.height]: out.append(f'<path d="M{ox} {H-y-oy}H{W-ox}" stroke="#2865ad" stroke-width=".2" stroke-dasharray="2,1"/>')
        out.append('</svg>'); Path(path).write_text('\n'.join(out),encoding="utf-8"); messagebox.showinfo("Exported",path)

    def export_pdf(self, pagesize, name, sheet):
        if pdf_canvas is None: messagebox.showerror("Dependency missing","Run pip install -r requirements.txt"); return
        try: cols, rows, gap = (int(self.sheet_cols.get()), int(self.sheet_rows.get()), float(self.sheet_gap.get())) if sheet else (1,1,0)
        except ValueError: messagebox.showerror("Invalid sheet layout","Columns and rows must be whole numbers; gap must be numeric."); return
        if cols < 1 or rows < 1 or gap < 0: messagebox.showerror("Invalid sheet layout","Use at least one row and column and a non-negative gap."); return
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF", "*.pdf")]);
        if not path:return
        c=self.cfg; pw,ph=pagesize; margin=12*mm; requested_w=cols*c.total_w+(cols-1)*gap+2*c.bleed; requested_h=rows*c.total_h+(rows-1)*gap+2*c.bleed
        scale=min((pw-2*margin)/(requested_w*mm),(ph-2*margin)/(requested_h*mm)); pdf=pdf_canvas(path,pagesize=pagesize); x0=margin+(pw-2*margin-requested_w*mm*scale)/2; y0=ph-margin-requested_h*mm*scale
        def draw_one(px,py):
            def rr(x,y,w,h): pdf.rect(px+(x+c.bleed)*mm*scale, py+(y+c.bleed)*mm*scale,w*mm*scale,h*mm*scale,stroke=1,fill=0)
            for x,y,w,h,_ in self.panels(): rr(x,y,w,h)
            for x,y,w,h in self.flaps(): rr(x,y,w,h)
            pdf.setDash(3,2); pdf.setStrokeColorRGB(.16,.4,.68)
            for x in [c.glue,c.glue+c.depth,c.glue+c.depth+c.width,c.glue+c.depth*2+c.width]: pdf.line(px+(x+c.bleed)*mm*scale,py,px+(x+c.bleed)*mm*scale,py+(c.total_h+2*c.bleed)*mm*scale)
            for y in [c.bottom,c.bottom+c.height]: pdf.line(px,py+(y+c.bleed)*mm*scale,px+(c.total_w+2*c.bleed)*mm*scale,py+(y+c.bleed)*mm*scale)
            pdf.setDash()
        for row in range(rows):
            for col in range(cols): draw_one(x0+col*(c.total_w+gap)*mm*scale,y0+(rows-1-row)*(c.total_h+gap)*mm*scale)
        pdf.save(); messagebox.showinfo("Exported",f"{name} sheet: {cols*rows} boxes\n{path}")

if __name__ == "__main__": App().mainloop()
