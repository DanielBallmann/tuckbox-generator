"""MTG tuckbox generator with fixed artwork panels and file-drop artwork loading."""
from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

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


@dataclass
class Box:
    cards: int = 22
    card_w: float = 63
    card_h: float = 88
    thickness: float = .30
    clearance: float = 2
    bleed: float = 3
    glue: float = 12
    tuck: float = 25
    notch: float = 11

    @property
    def panel_w(self): return self.cards * self.thickness + 2 * self.clearance
    @property
    def panel_d(self): return self.card_w + 2 * self.clearance
    @property
    def panel_h(self): return self.card_h + 2 * self.clearance
    @property
    def bottom(self): return min(self.panel_d * .62, self.panel_h * .56)
    @property
    def dust(self): return min(self.panel_d * .42, self.panel_h * .38)
    @property
    def body_y(self): return self.bottom
    @property
    def cut_w(self): return self.glue + 2 * self.panel_d + 2 * self.panel_w
    @property
    def cut_h(self): return self.bottom + self.panel_h + self.tuck
    @property
    def page_w(self): return self.cut_w + 2 * self.bleed
    @property
    def page_h(self): return self.cut_h + 2 * self.bleed

    def panels(self):
        x, y, d, w, h = self.glue, self.body_y, self.panel_d, self.panel_w, self.panel_h
        return {
            "back": (x, y, d, h),
            "side_left": (x + d, y, w, h),
            "front": (x + d + w, y, d, h),
            "side_right": (x + 2*d + w, y, w, h),
        }

    def body(self):
        return [(x, y, w, h, name) for name, (x, y, w, h) in self.panels().items()]

    def flaps(self):
        x, y, d, w, h = self.glue, self.body_y, self.panel_d, self.panel_w, self.panel_h
        front, left, right, top = x+d+w, x+d, x+2*d+w, y+h
        dust, shoulder = self.dust, min(6, d/7)
        return [
            ([(x+shoulder,y),(x+d-shoulder,y),(x+d,y-self.bottom),(x,y-self.bottom)], "cut"),
            ([(front+shoulder,y),(front+d-shoulder,y),(front+d,y-self.bottom),(front,y-self.bottom)], "cut"),
            ([(left+3,y),(left+w-3,y),(left+w,y-dust+4),(left+w-4,y-dust),(left+4,y-dust),(left,y-dust+4)], "cut"),
            ([(right+3,y),(right+w-3,y),(right+w,y-dust+4),(right+w-4,y-dust),(right+4,y-dust),(right,y-dust+4)], "cut"),
            ([(x+3,top),(x+d-3,top),(x+d-5,top+dust),(x+5,top+dust)], "cut"),
            ([(front+4,top),(front+d-4,top),(front+d-7,top+self.tuck),
              (front+d/2+self.notch/2,top+self.tuck),
              (front+d/2+self.notch/2,top+self.tuck-4),
              (front+d/2-self.notch/2,top+self.tuck-4),
              (front+d/2-self.notch/2,top+self.tuck),(front+7,top+self.tuck)], "cut"),
            ([(left+3,top),(left+w-3,top),(left+w-4,top+dust),(left+4,top+dust)], "cut"),
            ([(right+3,top),(right+w-3,top),(right+w-4,top+dust),(right+4,top+dust)], "cut"),
        ]


BaseWindow = TkinterDnD.Tk if TkinterDnD else tk.Tk


class App(BaseWindow):
    def __init__(self):
        super().__init__()
        self.style = ttk.Style(self, theme="flatly")
        self.title("MTG Tuckbox Generator")
        self.geometry("1240x820")
        self.minsize(1000, 680)
        self.dark = False
        self.box = Box()
        self.art = {name: None for name in self.box.panels()}
        self.photos = []
        self.scale = 1.0
        self.origin = (15, 15)
        self.vars = {key: ttk.StringVar(value=str(value)) for key, value in {
            "cards":22, "card_w":63, "card_h":88, "thickness":.30,
            "clearance":2, "bleed":3, "glue":12, "tuck":25, "notch":11}.items()}
        self.cols, self.rows, self.gap = (ttk.StringVar(value=v) for v in ("1", "1", "5"))
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill=BOTH, expand=True)
        side = ttk.Frame(root, width=320); side.pack(side=LEFT, fill=Y, padx=(0,12)); side.pack_propagate(False)
        view = ttk.Frame(root); view.pack(side=RIGHT, fill=BOTH, expand=True)
        head = ttk.Frame(side); head.pack(fill=X, pady=(0,10))
        ttk.Label(head, text="MTG Tuckbox Generator", font=("Segoe UI",16,"bold"), bootstyle="primary").pack(side=LEFT)
        ttk.Button(head, text="☾", width=3, command=self.toggle_theme, bootstyle="secondary-outline").pack(side=RIGHT)

        self.size = ttk.Labelframe(side, text="Sizing options", padding=8, bootstyle="primary")
        labels = {"cards":"Cards per pack","card_w":"Card width (mm)","card_h":"Card height (mm)","thickness":"Thickness/card (mm)","clearance":"Clearance (mm)","bleed":"Bleed (mm)","glue":"Glue tab (mm)","tuck":"Tuck flap depth (mm)","notch":"Thumb notch (mm)"}
        for key, var in self.vars.items():
            row = ttk.Frame(self.size); row.pack(fill=X, pady=2)
            ttk.Label(row, text=labels[key], width=20).pack(side=LEFT); ttk.Entry(row, textvariable=var, width=10).pack(side=RIGHT)
        ttk.Button(self.size, text="Apply dimensions", command=self.apply, bootstyle="primary").pack(fill=X, pady=(7,0))
        self.size_toggle = ttk.Button(side, text="Show sizing options", command=self.toggle_size, bootstyle="link"); self.size_toggle.pack(anchor="w", pady=(0,5))

        art = ttk.Labelframe(side, text="Artwork — fixed in place", padding=8, bootstyle="secondary"); art.pack(fill=X, pady=6)
        for label, panel in (("Back", "back"), ("Left side", "side_left"), ("Front", "front"), ("Right side", "side_right")):
            button = ttk.Button(art, text=f"Choose {label} artwork", command=lambda p=panel: self.choose_art(p), bootstyle="secondary")
            button.pack(fill=X, pady=2)
            self.register_drop(button, panel)
        self.art_label = ttk.Label(art, text="No artwork loaded", wraplength=290); self.art_label.pack(anchor="w", pady=4)
        ttk.Label(art, text="Drop a JPG or other supported image directly onto the matching button. Artwork is not movable.", wraplength=290).pack(anchor="w")

        sheet = ttk.Labelframe(side, text="Print sheet", padding=8, bootstyle="secondary"); sheet.pack(fill=X, pady=6)
        for label, var in (("Columns",self.cols),("Rows",self.rows),("Gap (mm)",self.gap)):
            row=ttk.Frame(sheet); row.pack(fill=X,pady=2); ttk.Label(row,text=label,width=20).pack(side=LEFT); ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(sheet,text="Save PDF sheet — A4",command=lambda:self.save_pdf(A4),bootstyle="success").pack(fill=X,pady=2)
        ttk.Button(sheet,text="Save PDF sheet — Letter",command=lambda:self.save_pdf(letter),bootstyle="success").pack(fill=X,pady=2)
        ttk.Button(sheet,text="Save SVG dieline",command=self.save_svg,bootstyle="info").pack(fill=X,pady=(6,2))
        self.info=ttk.Label(side,justify="left",wraplength=300); self.info.pack(anchor="w",pady=12)

        ttk.Label(view,text="Preview  •  red=cut  •  white/dark=score  •  artwork fixed to panels",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,7))
        self.canvas=tk.Canvas(view,bg="#edf0f2",highlightthickness=1); self.canvas.pack(fill=BOTH,expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

    def register_drop(self, widget, panel):
        if DND_FILES is None: return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda event, p=panel: self.drop_art(p, event.data))
        widget.dnd_bind("<<DragEnter>>", lambda event: widget.configure(cursor="hand2"))
        widget.dnd_bind("<<DragLeave>>", lambda event: widget.configure(cursor=""))

    @staticmethod
    def dropped_paths(data):
        # Windows supplies paths as {C:/path with spaces/file.jpg}; Unix paths
        # arrive as whitespace-separated values.
        return [a or b for a, b in re.findall(r"\{([^}]*)\}|([^\s]+)", data)]

    def drop_art(self, panel, data):
        paths = self.dropped_paths(data)
        if paths: self.set_art(panel, paths[0])

    def choose_art(self, panel):
        path = filedialog.askopenfilename(title=f"Choose {panel} artwork", filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff")])
        if path: self.set_art(panel, path)

    def set_art(self, panel, path):
        if Path(path).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
            messagebox.showerror("Unsupported artwork", "Please choose a JPG, PNG, WEBP, BMP, GIF, or TIFF image."); return
        if Image is None:
            messagebox.showerror("Missing dependency", "Install Pillow with: pip install -r requirements.txt"); return
        try:
            with Image.open(path) as image: image.verify()
        except Exception as exc:
            messagebox.showerror("Invalid image", str(exc)); return
        self.art[panel] = str(Path(path)); self.update_art_label(); self.redraw()

    def update_art_label(self):
        loaded = [f"{key}: {Path(path).name}" for key,path in self.art.items() if path]
        self.art_label.config(text="\n".join(loaded) if loaded else "No artwork loaded")

    def toggle_size(self):
        if self.size.winfo_ismapped(): self.size.pack_forget(); self.size_toggle.config(text="Show sizing options")
        else: self.size.pack(fill=X, before=self.size_toggle, pady=(0,8)); self.size_toggle.config(text="Hide sizing options")

    def toggle_theme(self):
        self.dark = not self.dark; self.style.theme_use("darkly" if self.dark else "flatly")
        self.canvas.configure(bg="#1f2329" if self.dark else "#edf0f2"); self.redraw()

    def apply(self):
        try:
            values = {k: float(v.get()) for k,v in self.vars.items()}; values["cards"] = int(values["cards"])
            if values["cards"] < 1 or values["bleed"] < 0 or any(values[k] <= 0 for k in values if k != "bleed"): raise ValueError
            old = self.art; self.box = Box(**values); self.art = {key: old.get(key) for key in self.box.panels()}; self.update_art_label(); self.redraw()
        except (ValueError, TypeError): messagebox.showerror("Invalid dimensions", "Enter positive dimensions and at least one card.")

    def page_xy(self, x, y):
        return self.origin[0]+(x+self.box.bleed)*self.scale, self.origin[1]+(self.box.page_h-y-self.box.bleed)*self.scale

    def redraw(self):
        if not hasattr(self, "canvas"): return
        b=self.box; self.canvas.delete("all"); self.photos.clear()
        self.scale=min(max(self.canvas.winfo_width()-30,100)/b.page_w,max(self.canvas.winfo_height()-30,100)/b.page_h); self.origin=(15.,15.)
        cut="#ff6675" if self.dark else "#dc3545"; score="#adb5bd" if self.dark else "#ffffff"; panel="#30343b" if self.dark else "#ffffff"; side="#272b31" if self.dark else "#f0f2f4"
        def polygon(points, fill): self.canvas.create_polygon([n for p in points for n in self.page_xy(*p)], fill=fill, outline=cut, width=2)
        for x,y,w,h,name in b.body(): polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)], panel if name in ("front","back") else side)
        for points,_ in b.flaps(): polygon(points, side)
        for x,y,w,h,name in b.body():
            a,bb=self.page_xy(x+w/2,y+h/2); self.canvas.create_text(a,bb,text=name.upper(),fill="#6c757d",font=("Segoe UI",9,"bold"))
        for x in (b.glue,b.glue+b.panel_d,b.glue+b.panel_d+b.panel_w,b.glue+2*b.panel_d+b.panel_w):
            a,bb=self.page_xy(x,0); c,d=self.page_xy(x,b.page_h); self.canvas.create_line(a,bb,c,d,fill=score,dash=(7,4),width=2)
        for y in (b.body_y,b.body_y+b.panel_h):
            a,bb=self.page_xy(0,y); c,d=self.page_xy(b.page_w,y); self.canvas.create_line(a,bb,c,d,fill=score,dash=(7,4),width=2)
        for panel_name, path in self.art.items(): self.draw_art(panel_name, path)
        for x,y in ((0,0),(b.cut_w,0),(0,b.cut_h),(b.cut_w,b.cut_h)):
            a,bb=self.page_xy(x,y); self.canvas.create_line(a-5,bb,a+5,bb,fill=cut); self.canvas.create_line(a,bb-5,a,bb+5,fill=cut)
        self.info.config(text=f"Cards per pack: {b.cards}\nArtwork panels: {sum(bool(p) for p in self.art.values())}/4\nArtwork is fixed; use the matching drop button\nPrint at 100%; test-fold first.")

    def draw_art(self, panel, path):
        if not path or Image is None: return
        try:
            x,y,w,h=self.box.panels()[panel]
            with Image.open(path) as source: image=ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"),(max(2,round(w*self.scale)),max(2,round(h*self.scale))),method=Image.Resampling.LANCZOS)
            photo=ImageTk.PhotoImage(image); self.photos.append(photo)
            cx,cy=self.page_xy(x+w/2,y+h/2); self.canvas.create_image(cx,cy,image=photo,anchor="center")
        except Exception as exc: self.info.config(text=f"Artwork preview failed: {exc}")

    def svg_art(self, panel):
        path=self.art[panel]
        if not path:return ""
        x,y,w,h=self.box.panels()[panel];o=self.box.bleed;H=self.box.page_h;data=base64.b64encode(Path(path).read_bytes()).decode("ascii");mime=mimetypes.guess_type(path)[0] or "image/jpeg";clip=f"clip-{panel}"
        return f'<clipPath id="{clip}"><rect x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}"/></clipPath><image href="data:{mime};base64,{data}" x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip})"/>'

    def save_svg(self):
        path=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG files","*.svg")])
        if not path:return
        try:
            b,W,H,o=self.box,self.box.page_w,self.box.page_h,self.box.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
            def poly(points): out.append(f'<polygon points="{" ".join(f"{x+o},{H-y-o}" for x,y in points)}" fill="none" stroke="#dc3545" stroke-width=".25"/>')
            for x,y,w,h,_ in b.body(): poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
            for points,_ in b.flaps(): poly(points)
            out.extend(self.svg_art(panel) for panel in self.art)
            for x in (b.glue,b.glue+b.panel_d,b.glue+b.panel_d+b.panel_w,b.glue+2*b.panel_d+b.panel_w): out.append(f'<path d="M{x+o} {H-o}V{H-b.page_h+o}" fill="none" stroke="#777" stroke-dasharray="2,1"/>')
            for y in (b.body_y,b.body_y+b.panel_h): out.append(f'<path d="M{o} {H-y-o}H{W-o}" fill="none" stroke="#777" stroke-dasharray="2,1"/>')
            Path(path).write_text("\n".join(out+["</svg>"]),encoding="utf-8"); messagebox.showinfo("Saved",f"SVG saved to:\n{path}")
        except Exception as exc: messagebox.showerror("SVG export failed",str(exc))

    def save_pdf(self,pagesize):
        if Canvas is None or ImageReader is None: messagebox.showerror("Missing dependency","Install reportlab with: pip install -r requirements.txt"); return
        try:
            cols,rows,gap=int(self.cols.get()),int(self.rows.get()),float(self.gap.get())
            if cols<1 or rows<1 or gap<0: raise ValueError
        except ValueError: messagebox.showerror("Invalid sheet","Columns/rows must be positive integers and gap non-negative."); return
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF files","*.pdf")])
        if not path:return
        try:
            b=self.box; pw,ph=pagesize; margin=12*mm; sw=cols*b.page_w+(cols-1)*gap; sh=rows*b.page_h+(rows-1)*gap; scale=min((pw-2*margin)/(sw*mm),(ph-2*margin)/(sh*mm)); left=margin+(pw-2*margin-sw*mm*scale)/2; bottom=margin+(ph-2*margin-sh*mm*scale)/2; pdf=Canvas(path,pagesize=pagesize)
            def draw_one(px,py):
                def P(x,y): return px+(x+b.bleed)*mm*scale,py+(y+b.bleed)*mm*scale
                def shape(points):
                    q=pdf.beginPath(); q.moveTo(*P(*points[0])); [q.lineTo(*P(*p)) for p in points[1:]]; q.close(); pdf.setStrokeColorRGB(.86,.1,.18); pdf.setDash(); pdf.drawPath(q,stroke=1,fill=0)
                for x,y,w,h,_ in b.body(): shape([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
                for points,_ in b.flaps(): shape(points)
                for panel,path_img in self.art.items():
                    if path_img:
                        x,y,w,h=b.panels()[panel]; pdf.drawImage(ImageReader(path_img),*P(x,y),width=w*mm*scale,height=h*mm*scale,preserveAspectRatio=False,mask="auto")
                pdf.setStrokeColorRGB(.45,.45,.45); pdf.setDash(3,2)
                for x in (b.glue,b.glue+b.panel_d,b.glue+b.panel_d+b.panel_w,b.glue+2*b.panel_d+b.panel_w): pdf.line(*P(x,0),*P(x,b.page_h))
                for y in (b.body_y,b.body_y+b.panel_h): pdf.line(*P(0,y),*P(b.page_w,y))
                pdf.setDash()
            for row in range(rows):
                for col in range(cols): draw_one(left+col*(b.page_w+gap)*mm*scale,bottom+(rows-1-row)*(b.page_h+gap)*mm*scale)
            pdf.save(); messagebox.showinfo("Saved",f"PDF saved to:\n{path}")
        except Exception as exc: messagebox.showerror("PDF export failed",str(exc))


if __name__ == "__main__": App().mainloop()
