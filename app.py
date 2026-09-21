"""Printable tuckbox dieline generator for standard MTG-sized cards."""
from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from xml.sax.saxutils import escape

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


@dataclass
class BoxConfig:
    cards: int = 60
    card_w: float = 63.0
    card_h: float = 88.0
    thickness: float = 0.30
    clearance: float = 2.0
    bleed: float = 3.0
    glue_tab: float = 12.0
    tuck_depth: float = 25.0

    @property
    def inner_w(self): return self.cards * self.thickness + self.clearance * 2
    @property
    def inner_d(self): return self.card_w + self.clearance * 2
    @property
    def inner_h(self): return self.card_h + self.clearance * 2
    @property
    def dieline_w(self): return self.glue_tab + self.inner_d * 2 + self.inner_w * 2
    @property
    def dieline_h(self): return self.tuck_depth + self.inner_h + self.inner_h * .72


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Tuckbox Generator")
        self.geometry("1250x820")
        self.minsize(1000, 700)
        self.cfg = BoxConfig()
        self.front_path = self.back_path = None
        self._photos = []
        self._make_ui()
        self.redraw()

    def _make_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill="both", expand=True)
        controls = ttk.Frame(root, width=285); controls.pack(side="left", fill="y", padx=(0, 12)); controls.pack_propagate(False)
        preview = ttk.Frame(root); preview.pack(side="right", fill="both", expand=True)
        ttk.Label(controls, text="Tuckbox settings", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 8))
        self.vars = {k: tk.StringVar(value=str(v)) for k, v in {
            "cards": 60, "card_w": 63, "card_h": 88, "thickness": .30,
            "clearance": 2, "bleed": 3, "glue_tab": 12, "tuck_depth": 25}.items()}
        labels = {"cards":"Cards", "card_w":"Card width (mm)", "card_h":"Card height (mm)", "thickness":"Card thickness (mm)", "clearance":"Clearance (mm)", "bleed":"Bleed (mm)", "glue_tab":"Glue tab (mm)", "tuck_depth":"Top tuck flap (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(controls); row.pack(fill="x", pady=3)
            ttk.Label(row, text=labels[key], width=20).pack(side="left")
            ttk.Entry(row, textvariable=var, width=9).pack(side="right")
        ttk.Button(controls, text="Apply and redraw", command=self.apply).pack(fill="x", pady=(8, 12))
        ttk.Separator(controls).pack(fill="x", pady=4)
        ttk.Label(controls, text="Artwork", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=8)
        ttk.Button(controls, text="Choose front artwork", command=lambda: self.choose("front")).pack(fill="x", pady=3)
        ttk.Button(controls, text="Choose back artwork", command=lambda: self.choose("back")).pack(fill="x", pady=3)
        self.art_label = ttk.Label(controls, text="No artwork selected", wraplength=260); self.art_label.pack(anchor="w", pady=5)
        ttk.Separator(controls).pack(fill="x", pady=8)
        ttk.Label(controls, text="Export", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)
        ttk.Button(controls, text="Export SVG dieline", command=self.export_svg).pack(fill="x", pady=3)
        ttk.Button(controls, text="Export PDF (A4)", command=lambda: self.export_pdf(A4)).pack(fill="x", pady=3)
        ttk.Button(controls, text="Export PDF (Letter)", command=lambda: self.export_pdf(letter)).pack(fill="x", pady=3)
        self.info = ttk.Label(controls, text="", justify="left", wraplength=270); self.info.pack(anchor="w", pady=18)
        ttk.Label(preview, text="Dieline preview — solid = cut, dashed = fold", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 8))
        self.canvas = tk.Canvas(preview, background="#eef0f2", highlightthickness=1); self.canvas.pack(fill="both", expand=True)

    def apply(self):
        try:
            values = {k: float(v.get()) for k, v in self.vars.items()}
            values["cards"] = int(values["cards"])
            if values["cards"] < 1 or any(values[k] <= 0 for k in ("card_w", "card_h", "thickness", "clearance", "glue_tab", "tuck_depth")) or values["bleed"] < 0:
                raise ValueError
            self.cfg = BoxConfig(**values)
        except (ValueError, TypeError):
            messagebox.showerror("Invalid settings", "Enter positive numeric dimensions and at least one card."); return
        self.redraw()

    def choose(self, side):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")])
        if path:
            setattr(self, side + "_path", path)
            self.art_label.config(text=f"Front: {os.path.basename(self.front_path) if self.front_path else 'none'}\nBack: {os.path.basename(self.back_path) if self.back_path else 'none'}")
            self.redraw()

    def geometry(self):
        c = self.cfg; x = c.glue_tab; y = c.tuck_depth
        # panel order: glue, back, side, front, side; each tuple x,y,w,h
        panels = [(0, y, c.glue_tab, c.inner_h), (x, y, c.inner_d, c.inner_h), (x+c.inner_d, y, c.inner_w, c.inner_h), (x+c.inner_d+c.inner_w, y, c.inner_d, c.inner_h), (x+c.inner_d*2+c.inner_w, y, c.inner_w, c.inner_h)]
        return panels

    def redraw(self):
        self.canvas.delete("all"); self._photos.clear(); c = self.cfg
        scale = min((self.canvas.winfo_width()-30)/max(c.dieline_w, 1), (self.canvas.winfo_height()-30)/max(c.dieline_h, 1), 5.2)
        scale = max(scale, 1.4); ox, oy = 15, 15
        def p(x, y): return ox+x*scale, oy+(c.dieline_h-y)*scale
        def rect(x,y,w,h, fill="white", outline="#222", dash=()):
            x1,y1=p(x,y); x2,y2=p(x+w,y+h); self.canvas.create_rectangle(x1,y2,x2,y1, fill=fill, outline=outline, width=2, dash=dash)
        # body panels
        panels = self.geometry()
        for i,(x,y,w,h) in enumerate(panels): rect(x,y,w,h, "#fff" if i in (1,3) else "#f3f5f7")
        # bottom flaps: full flaps on front/back, dust flaps on sides
        for x,y,w,h in [(c.glue_tab,y-c.inner_h*.72,c.inner_d,c.inner_h*.72), (c.glue_tab+c.inner_d+c.inner_w,y-c.inner_h*.72,c.inner_d,c.inner_h*.72), (c.glue_tab+c.inner_d,y-c.inner_h*.52,c.inner_w,c.inner_h*.52), (c.glue_tab+c.inner_d*2+c.inner_w,y-c.inner_h*.52,c.inner_w,c.inner_h*.52)]: rect(x,y,w,h,"#f8f8f8")
        # top flaps: back locking tuck, front dust flap, side dust flaps
        for x,y,w,h in [(c.glue_tab,y+c.inner_h,c.inner_d,c.tuck_depth), (c.glue_tab+c.inner_d+c.inner_w,y+c.inner_h,c.inner_d,c.inner_h*.52), (c.glue_tab+c.inner_d,y+c.inner_h,c.inner_w,c.inner_h*.34), (c.glue_tab+c.inner_d*2+c.inner_w,y+c.inner_h,c.inner_w,c.inner_h*.34)]: rect(x,y,w,h,"#f8f8f8")
        # labels and fold lines
        for i,(x,y,w,h) in enumerate(panels):
            if i == 0: continue
            tx,ty=p(x+w/2,y+h/2); self.canvas.create_text(tx,ty,text={1:"BACK",2:"SIDE",3:"FRONT",4:"SIDE"}[i], fill="#555", font=("Segoe UI", 10, "bold"))
        for x in [c.glue_tab, c.glue_tab+c.inner_d, c.glue_tab+c.inner_d+c.inner_w, c.glue_tab+c.inner_d*2+c.inner_w, c.glue_tab+c.inner_d*2+c.inner_w*2]:
            x1,y1=p(x,0); x2,y2=p(x,c.dieline_h); self.canvas.create_line(x1,y1,x2,y2, fill="#5577aa", dash=(5,4))
        for y in [c.tuck_depth, c.tuck_depth+c.inner_h]:
            x1,y1=p(0,y); x2,y2=p(c.dieline_w,y); self.canvas.create_line(x1,y1,x2,y2, fill="#5577aa", dash=(5,4))
        self.info.config(text=f"Internal: {c.inner_w:.2f} W × {c.inner_d:.2f} D × {c.inner_h:.2f} H mm\nDieline: {c.dieline_w:.2f} × {c.dieline_h:.2f} mm\nBleed: {c.bleed:.2f} mm\nPrint at 100%; verify with a test cut.")

    def _svg(self):
        c=self.cfg; w,h=c.dieline_w+2*c.bleed,c.dieline_h+2*c.bleed; ox=oy=c.bleed
        out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">', '<rect width="100%" height="100%" fill="white"/>']
        def r(x,y,ww,hh,kind="cut"):
            style='fill:#fff;stroke:#111;stroke-width:.25' if kind=='cut' else 'fill:none;stroke:#36c;stroke-width:.2;stroke-dasharray="2,1"'
            out.append(f'<rect x="{x+ox}" y="{h-(y+oy+hh)}" width="{ww}" height="{hh}" style="{style}"/>')
        for x,y,ww,hh in self.geometry(): r(x,y,ww,hh)
        for x,y,ww,hh in [(c.glue_tab,y-c.inner_h*.72,c.inner_d,c.inner_h*.72),(c.glue_tab+c.inner_d+c.inner_w,y-c.inner_h*.72,c.inner_d,c.inner_h*.72),(c.glue_tab+c.inner_d,y-c.inner_h*.52,c.inner_w,c.inner_h*.52),(c.glue_tab+c.inner_d*2+c.inner_w,y-c.inner_h*.52,c.inner_w,c.inner_h*.52),(c.glue_tab,y+c.inner_h,c.inner_d,c.tuck_depth),(c.glue_tab+c.inner_d+c.inner_w,y+c.inner_h,c.inner_d,c.inner_h*.52),(c.glue_tab+c.inner_d,y+c.inner_h,c.inner_w,c.inner_h*.34),(c.glue_tab+c.inner_d*2+c.inner_w,y+c.inner_h,c.inner_w,c.inner_h*.34)]: r(x,y,ww,hh)
        for x in [c.glue_tab,c.glue_tab+c.inner_d,c.glue_tab+c.inner_d+c.inner_w,c.glue_tab+c.inner_d*2+c.inner_w,c.glue_tab+c.inner_d*2+c.inner_w*2]: out.append(f'<path d="M{x+ox} {h-oy}V{h-(c.dieline_h+oy)}" style="fill:none;stroke:#36c;stroke-width:.2;stroke-dasharray:2,1"/>')
        for y in [c.tuck_depth,c.tuck_depth+c.inner_h]: out.append(f'<path d="M{ox} {h-(y+oy)}H{w-ox}" style="fill:none;stroke:#36c;stroke-width:.2;stroke-dasharray:2,1"/>')
        out.append('</svg>'); return '\n'.join(out)

    def export_svg(self):
        path=filedialog.asksaveasfilename(defaultextension='.svg',filetypes=[('SVG','*.svg')])
        if path:
            Path(path).write_text(self._svg(), encoding='utf-8'); messagebox.showinfo('Exported', path)

    def export_pdf(self, pagesize):
        if pdf_canvas is None: messagebox.showerror('Dependency missing','Run pip install -r requirements.txt'); return
        path=filedialog.asksaveasfilename(defaultextension='.pdf',filetypes=[('PDF','*.pdf')])
        if not path:return
        c=self.cfg; pdf=pdf_canvas(path,pagesize=pagesize); pw,ph=pagesize; margin=12*mm
        scale=min((pw-2*margin)/(c.dieline_w+2*c.bleed)/mm,(ph-2*margin)/(c.dieline_h+2*c.bleed)/mm)
        x0,y0=margin,ph-margin-(c.dieline_h+2*c.bleed)*mm*scale
        def rr(x,y,w,h): pdf.rect(x0+(x+c.bleed)*mm*scale,y0+(y+c.bleed)*mm*scale,w*mm*scale,h*mm*scale,stroke=1,fill=0)
        for x,y,w,h in self.geometry():rr(x,y,w,h)
        for x,y,w,h in [(c.glue_tab,y-c.inner_h*.72,c.inner_d,c.inner_h*.72),(c.glue_tab+c.inner_d+c.inner_w,y-c.inner_h*.72,c.inner_d,c.inner_h*.72),(c.glue_tab+c.inner_d,y-c.inner_h*.52,c.inner_w,c.inner_h*.52),(c.glue_tab+c.inner_d*2+c.inner_w,y-c.inner_h*.52,c.inner_w,c.inner_h*.52),(c.glue_tab,y+c.inner_h,c.inner_d,c.tuck_depth),(c.glue_tab+c.inner_d+c.inner_w,y+c.inner_h,c.inner_d,c.inner_h*.52),(c.glue_tab+c.inner_d,y+c.inner_h,c.inner_w,c.inner_h*.34),(c.glue_tab+c.inner_d*2+c.inner_w,y+c.inner_h,c.inner_w,c.inner_h*.34)]:rr(x,y,w,h)
        pdf.setDash(3,2); pdf.setStrokeColorRGB(.2,.4,.8)
        for x in [c.glue_tab,c.glue_tab+c.inner_d,c.glue_tab+c.inner_d+c.inner_w,c.glue_tab+c.inner_d*2+c.inner_w,c.glue_tab+c.inner_d*2+c.inner_w*2]:pdf.line(x0+(x+c.bleed)*mm*scale,y0,x0+(x+c.bleed)*mm*scale,y0+(c.dieline_h+2*c.bleed)*mm*scale)
        pdf.save(); messagebox.showinfo('Exported', path)

if __name__ == '__main__':
    App().mainloop()
