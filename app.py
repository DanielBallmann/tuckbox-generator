"""Printable straight-tuck MTG box generator."""
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
    thickness: float = .30
    clearance: float = 2.0
    bleed: float = 3.0
    glue: float = 12.0
    tuck_lip: float = 19.05
    notch: float = 11.0

    @property
    def width(self): return max(1.0, self.cards * self.thickness + 2 * self.clearance)
    @property
    def depth(self): return self.card_w + 2 * self.clearance
    @property
    def height(self): return self.card_h + 2 * self.clearance
    @property
    def body_y(self): return self.depth + self.tuck_lip
    @property
    def sheet_w(self): return self.glue + 2 * self.width + 2 * self.depth + 2 * self.bleed
    @property
    def sheet_h(self): return self.body_y + self.height + self.depth + self.tuck_lip + 2 * self.bleed

    def panels(self):
        """The assembly order is glue -> back -> left side -> front -> right side.

        The glue tab is glued behind the right side, leaving the named back and
        front on their actual opposite faces.  The top flap belongs to back and
        the bottom flap belongs to front; this is important for artwork order.
        """
        x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        return {
            "back": (x, y, w, h),
            "side_left": (x + w, y, d, h),
            "front": (x + w + d, y, w, h),
            "side_right": (x + 2*w + d, y, d, h),
            "top": (x, y + h, w, d),       # attached to back
            "bottom": (x + w + d, y - d, w, d),  # attached to front
        }

    def body(self):
        return [(x, y, w, h, name) for name, (x, y, w, h) in self.panels().items()
                if name in {"back", "side_left", "front", "side_right"}]

    def cut_segments(self):
        """Only outside cut edges.  Hinge edges are deliberately not cut."""
        p = self.panels(); x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        dust = min(d * .42, h * .38); left, right = p["side_left"][0], p["side_right"][0]
        n = max(2.0, min(self.notch, w - 4.0)); c = min(4.0, self.glue / 2)
        segments = [
            # outside of glue tab (its right edge is the body hinge)
            ((0, y+c), (c, y)), ((c, y), (x, y)),
            ((0, y+c), (0, y+h-c)), ((0, y+h-c), (c, y+h)), ((c, y+h), (x, y+h)),
            # top flap, starting after its hinge at y+h
            ((x, y+h+d), (x, y+h+d+self.tuck_lip)),
            ((x, y+h+d+self.tuck_lip), (x+7, y+h+d+self.tuck_lip)),
            ((x+7, y+h+d+self.tuck_lip), (x+w/2-n/2, y+h+d+self.tuck_lip)),
            ((x+w/2-n/2, y+h+d+self.tuck_lip), (x+w/2-n/2, y+h+d+self.tuck_lip-4)),
            ((x+w/2-n/2, y+h+d+self.tuck_lip-4), (x+w/2+n/2, y+h+d+self.tuck_lip-4)),
            ((x+w/2+n/2, y+h+d+self.tuck_lip-4), (x+w/2+n/2, y+h+d+self.tuck_lip)),
            ((x+w/2+n/2, y+h+d+self.tuck_lip), (x+w-7, y+h+d+self.tuck_lip)),
            ((x+w-7, y+h+d+self.tuck_lip), (x+w, y+h+d)),
            ((x+w, y+h+d), (x+w, y+h)),
            # bottom flap, attached to front at y
            ((x+w+d, y-d), (x+w+d, y-d-self.tuck_lip)),
            ((x+w+d, y-d-self.tuck_lip), (x+2*w+d, y-d-self.tuck_lip)),
            ((x+2*w+d, y-d-self.tuck_lip), (x+2*w+d, y-d)),
            # bottom and top dust-flap outside edges
            ((left, y-dust+4), (left+4, y-dust)), ((left+4, y-dust), (left+d-4, y-dust)), ((left+d-4, y-dust), (left+d, y-dust+4)),
            ((right, y-dust+4), (right+4, y-dust)), ((right+4, y-dust), (right+d-4, y-dust)), ((right+d-4, y-dust), (right+d, y-dust+4)),
            ((left+4, y+h+dust), (left+d-4, y+h+dust)), ((left+d-4, y+h+dust), (left+d-2, y+h)),
            ((right+4, y+h+dust), (right+d-4, y+h+dust)), ((right+d-4, y+h+dust), (right+d-2, y+h)),
        ]
        return segments

    def fold_segments(self):
        p = self.panels(); x, y, w, d, h = self.glue, self.body_y, self.width, self.depth, self.height
        return [
            ((x,y),(x,y+h)), ((x+w,y),(x+w,y+h)), ((x+w+d,y),(x+w+d,y+h)), ((x+2*w+d,y),(x+2*w+d,y+h)),
            ((x,y+h),(x+w,y+h)), ((x,y+h+d),(x+w,y+h+d)),
            ((x+w+d,y),(x+2*w+d,y)), ((x+w+d,y-d),(x+2*w+d,y-d)),
            ((x+w,y),(x+w+d,y)), ((x+2*w+d,y),(x+2*w+2*d,y)),
            ((x+w,y+h),(x+w+d,y+h)), ((x+2*w+d,y+h),(x+2*w+2*d,y+h)),
        ]


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("MTG Tuckbox Generator"); self.geometry("1180x780")
        self.box=Box(); self.art={f:None for f in self.box.panels()}; self.photos=[]; self.scale=1; self.origin=(15,15)
        self.vars={k:ttk.StringVar(value=str(v)) for k,v in {"cards":22,"card_w":63,"card_h":88,"thickness":.30,"clearance":2,"bleed":3,"glue":12,"tuck_lip":19.05,"notch":11}.items()}
        self.build_ui(); self.after(100,self.redraw)

    def build_ui(self):
        root=ttk.Frame(self,padding=12); root.pack(fill=BOTH,expand=True); side=ttk.Frame(root,width=300); side.pack(side=LEFT,fill=Y,padx=(0,12)); side.pack_propagate(False); view=ttk.Frame(root); view.pack(side=RIGHT,fill=BOTH,expand=True)
        ttk.Label(side,text="MTG Tuckbox Generator",font=("Segoe UI",16,"bold")).pack(anchor="w",pady=(0,10)); box=ttk.Labelframe(side,text="Box dimensions (mm)",padding=8); box.pack(fill=X)
        labels={"cards":"Cards","card_w":"Card width","card_h":"Card height","thickness":"Thickness/card","clearance":"Clearance","bleed":"Bleed","glue":"Glue tab","tuck_lip":"Tuck lip","notch":"Thumb notch"}
        for k,v in self.vars.items():
            row=ttk.Frame(box); row.pack(fill=X,pady=2); ttk.Label(row,text=labels[k],width=17).pack(side=LEFT); ttk.Entry(row,textvariable=v,width=9).pack(side=RIGHT)
        ttk.Button(box,text="Apply dimensions",command=self.apply,bootstyle="primary").pack(fill=X,pady=(7,0)); art=ttk.Labelframe(side,text="Artwork (actual faces)",padding=8); art.pack(fill=X,pady=8)
        for label,face in (("Back","back"),("Left side","side_left"),("Front","front"),("Right side","side_right"),("Top flap","top"),("Bottom flap","bottom")):
            ttk.Button(art,text=f"Choose {label}",command=lambda f=face:self.choose_art(f)).pack(fill=X,pady=2)
        self.art_label=ttk.Label(art,text="No artwork loaded",wraplength=270); self.art_label.pack(anchor="w",pady=4)
        ttk.Button(side,text="Save SVG dieline",command=self.save_svg,bootstyle="info").pack(fill=X,pady=2); ttk.Button(side,text="Save PDF (A4)",command=lambda:self.save_pdf(A4),bootstyle="success").pack(fill=X,pady=2); ttk.Button(side,text="Save PDF (Letter)",command=lambda:self.save_pdf(letter),bootstyle="success").pack(fill=X,pady=2)
        self.info=ttk.Label(side,justify="left",wraplength=285); self.info.pack(anchor="w",pady=12); ttk.Label(view,text="Preview • red=cut • grey dashed=fold",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,7)); self.canvas=tk.Canvas(view,bg="#edf0f2",highlightthickness=1); self.canvas.pack(fill=BOTH,expand=True); self.canvas.bind("<Configure>",lambda _:self.redraw())

    def apply(self):
        try:
            values={k:float(v.get()) for k,v in self.vars.items()}; values["cards"]=int(values["cards"])
            if values["cards"]<1 or values["bleed"]<0 or any(v<=0 for k,v in values.items() if k!="bleed"): raise ValueError
            old=self.art; self.box=Box(**values); self.art={f:old.get(f) for f in self.box.panels()}; self.update_art_label(); self.redraw()
        except (ValueError,TypeError): messagebox.showerror("Invalid dimensions","Enter positive dimensions and at least one card.")

    def choose_art(self,face):
        path=filedialog.askopenfilename(filetypes=[("Images","*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff")])
        if not path or Image is None:return
        try:
            with Image.open(path) as im: im.verify()
            self.art[face]=str(Path(path).resolve()); self.update_art_label(); self.redraw()
        except Exception as exc: messagebox.showerror("Invalid artwork",str(exc))

    def update_art_label(self): self.art_label.config(text="\n".join(f"{f}: {Path(p).name}" for f,p in self.art.items() if p) or "No artwork loaded")
    def page_xy(self,x,y): return self.origin[0]+(x+self.box.bleed)*self.scale,self.origin[1]+(self.box.sheet_h-y-self.box.bleed)*self.scale

    def redraw(self):
        if not hasattr(self,"canvas"):return
        b=self.box; self.canvas.delete("all"); self.photos.clear(); self.scale=min(max(self.canvas.winfo_width()-30,100)/b.sheet_w,max(self.canvas.winfo_height()-30,100)/b.sheet_h); self.origin=(15,15)
        def poly(points,fill): self.canvas.create_polygon([q for p in points for q in self.page_xy(*p)],fill=fill,outline="")
        for x,y,w,h,name in b.body(): poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],"#fff" if name in {"front","back"} else "#f0f2f4")
        for face in ("top","bottom"):
            x,y,w,h=b.panels()[face]; poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],"#f0f2f4")
        for face,path in self.art.items(): self.draw_art(face,path)
        for a,z in b.cut_segments(): self.canvas.create_line(*self.page_xy(*a),*self.page_xy(*z),fill="#dc3545",width=2)
        for a,z in b.fold_segments(): self.canvas.create_line(*self.page_xy(*a),*self.page_xy(*z),fill="#6c757d",dash=(7,4),width=2)
        self.info.config(text=f"Assembly: glue → back → left side → front → right side\nInternal: {b.width:.1f} W × {b.depth:.1f} D × {b.height:.1f} H mm\nSheet: {b.sheet_w:.1f} × {b.sheet_h:.1f} mm\nArtwork: {sum(bool(p) for p in self.art.values())}/6")

    def draw_art(self,face,path):
        if not path or Image is None:return
        try:
            x,y,w,h=self.box.panels()[face]
            with Image.open(path) as src: image=ImageOps.fit(ImageOps.exif_transpose(src).convert("RGB"),(max(2,round(w*self.scale)),max(2,round(h*self.scale))))
            photo=ImageTk.PhotoImage(image); self.photos.append(photo); self.canvas.create_image(*self.page_xy(x+w/2,y+h/2),image=photo,anchor="center")
        except Exception as exc:self.info.config(text=f"Artwork preview failed: {exc}")

    def save_svg(self):
        path=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG files","*.svg")]);
        if not path:return
        b=self.box; W,H=b.sheet_w,b.sheet_h; o=b.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
        for face,p in self.art.items():
            if p:
                x,y,w,h=b.panels()[face]; data=base64.b64encode(Path(p).read_bytes()).decode(); mime=mimetypes.guess_type(p)[0] or "image/jpeg"; out.append(f'<image href="data:{mime};base64,{data}" x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')
        for a,z in b.cut_segments(): out.append(f'<path d="M{a[0]+o} {H-a[1]-o}L{z[0]+o} {H-z[1]-o}" fill="none" stroke="#dc3545" stroke-width=".25"/>')
        for a,z in b.fold_segments(): out.append(f'<path d="M{a[0]+o} {H-a[1]-o}L{z[0]+o} {H-z[1]-o}" fill="none" stroke="#777" stroke-dasharray="2,1"/>')
        Path(path).write_text("\n".join(out+["</svg>"]),encoding="utf-8"); messagebox.showinfo("Saved",f"SVG saved to:\n{path}")

    def save_pdf(self,pagesize):
        if Canvas is None: messagebox.showerror("Missing dependency","Install dependencies with: pip install -r requirements.txt"); return
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF files","*.pdf")]);
        if not path:return
        try:
            b=self.box; pw,ph=pagesize; margin=12*mm; scale=min((pw-2*margin)/(b.sheet_w*mm),(ph-2*margin)/(b.sheet_h*mm)); px=margin+(pw-2*margin-b.sheet_w*mm*scale)/2; py=margin+(ph-2*margin-b.sheet_h*mm*scale)/2; pdf=Canvas(path,pagesize=pagesize)
            def P(x,y): return px+(x+b.bleed)*mm*scale,py+(y+b.bleed)*mm*scale
            for face,p in self.art.items():
                if p:
                    x,y,w,h=b.panels()[face]; pdf.drawImage(ImageReader(p),*P(x,y),width=w*mm*scale,height=h*mm*scale,preserveAspectRatio=False,mask="auto")
            pdf.setStrokeColorRGB(.86,.1,.18); pdf.setDash()
            for a,z in b.cut_segments(): pdf.line(*P(*a),*P(*z))
            pdf.setStrokeColorRGB(.45,.45,.45); pdf.setDash(3,2)
            for a,z in b.fold_segments(): pdf.line(*P(*a),*P(*z))
            pdf.save(); messagebox.showinfo("Saved",f"PDF saved to:\n{path}")
        except Exception as exc: messagebox.showerror("PDF export failed",str(exc))


if __name__ == "__main__": App().mainloop()
