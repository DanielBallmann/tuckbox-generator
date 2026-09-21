"""MTG tuckbox generator with working artwork preview and exports."""
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
    card_w: float = 63
    card_h: float = 88
    thickness: float = .30
    clearance: float = 2
    bleed: float = 3
    glue: float = 12
    tuck: float = 25

    @property
    def w(self): return self.cards * self.thickness + 2 * self.clearance
    @property
    def d(self): return self.card_w + 2 * self.clearance
    @property
    def h(self): return self.card_h + 2 * self.clearance
    @property
    def bottom_depth(self): return min(self.d * .62, self.h * .56)
    @property
    def dust_depth(self): return min(self.d * .42, self.h * .38)
    @property
    def y(self): return self.bottom_depth
    @property
    def cut_w(self): return self.glue + 2 * self.d + 2 * self.w
    @property
    def cut_h(self): return self.bottom_depth + self.h + self.tuck
    @property
    def page_w(self): return self.cut_w + 2 * self.bleed
    @property
    def page_h(self): return self.cut_h + 2 * self.bleed

    def panels(self):
        x, y = self.glue, self.y
        return [(x, y, self.d, self.h, "back"),
                (x+self.d, y, self.w, self.h, "side"),
                (x+self.d+self.w, y, self.d, self.h, "front"),
                (x+2*self.d+self.w, y, self.w, self.h, "side")]

    def flaps(self):
        c, x, y = self, self.glue, self.y
        main, dust, shoulder = c.bottom_depth, c.dust_depth, min(6, c.d/7)
        fx, sx, rx = x+c.d+c.w, x+c.d, x+2*c.d+c.w
        return [
            ([(x+shoulder,y),(x+c.d-shoulder,y),(x+c.d,y-main),(x,y-main)], "bottom"),
            ([(fx+shoulder,y),(fx+c.d-shoulder,y),(fx+c.d,y-main),(fx,y-main)], "bottom"),
            ([(sx+3,y),(sx+c.w-3,y),(sx+c.w,y-dust+4),(sx+c.w-4,y-dust),(sx+4,y-dust),(sx,y-dust+4)], "dust"),
            ([(rx+3,y),(rx+c.w-3,y),(rx+c.w,y-dust+4),(rx+c.w-4,y-dust),(rx+4,y-dust),(rx,y-dust+4)], "dust"),
            ([(x+3,y+c.h),(x+c.d-3,y+c.h),(x+c.d-5,y+c.h+dust),(x+5,y+c.h+dust)], "dust"),
            ([(fx+4,y+c.h),(fx+c.d-4,y+c.h),(fx+c.d-7,y+c.h+c.tuck),(fx+c.d/2+5,y+c.h+c.tuck),(fx+c.d/2,y+c.h+c.tuck+4),(fx+c.d/2-5,y+c.h+c.tuck),(fx+7,y+c.h+c.tuck)], "tuck"),
            ([(sx+3,y+c.h),(sx+c.w-3,y+c.h),(sx+c.w-4,y+c.h+dust),(sx+4,y+c.h+dust)], "dust"),
            ([(rx+3,y+c.h),(rx+c.w-3,y+c.h),(rx+c.w-4,y+c.h+dust),(rx+4,y+c.h+dust)], "dust"),
        ]


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("MTG Tuckbox Generator"); self.geometry("1240x820"); self.minsize(1000, 680)
        self.box = Box(); self.front = None; self.back = None
        self.art_offset = {"front": [0., 0.], "back": [0., 0.]}
        self.photos = []; self.drag = None; self.preview_scale = 1.; self.origin = (0, 0)
        self.vars = {k: ttk.StringVar(value=str(v)) for k, v in {"cards":60,"card_w":63,"card_h":88,"thickness":.30,"clearance":2,"bleed":3,"glue":12,"tuck":25}.items()}
        self.cols = ttk.StringVar(value="1"); self.rows = ttk.StringVar(value="1"); self.gap = ttk.StringVar(value="5")
        self.build_ui(); self.after(100, self.redraw)

    def build_ui(self):
        root=ttk.Frame(self,padding=12); root.pack(fill=BOTH,expand=True)
        left=ttk.Frame(root,width=310); left.pack(side=LEFT,fill=Y,padx=(0,12)); left.pack_propagate(False)
        right=ttk.Frame(root); right.pack(side=RIGHT,fill=BOTH,expand=True)
        ttk.Label(left,text="MTG Tuckbox Generator",font=("Segoe UI",16,"bold"),bootstyle="primary").pack(anchor="w",pady=(0,10))
        labels={"cards":"Cards","card_w":"Card width (mm)","card_h":"Card height (mm)","thickness":"Thickness/card (mm)","clearance":"Clearance (mm)","bleed":"Bleed (mm)","glue":"Glue tab (mm)","tuck":"Tuck flap depth (mm)"}
        for key,var in self.vars.items():
            row=ttk.Frame(left); row.pack(fill=X,pady=2); ttk.Label(row,text=labels[key],width=20).pack(side=LEFT); ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(left,text="Apply dimensions",command=self.apply,bootstyle="primary").pack(fill=X,pady=(8,10))
        ttk.Separator(left).pack(fill=X,pady=5); ttk.Label(left,text="Artwork",font=("Segoe UI",11,"bold")).pack(anchor="w",pady=5)
        ttk.Button(left,text="Load front artwork",command=lambda:self.load_art("front"),bootstyle="secondary").pack(fill=X,pady=2)
        ttk.Button(left,text="Load back artwork",command=lambda:self.load_art("back"),bootstyle="secondary").pack(fill=X,pady=2)
        ttk.Button(left,text="Reset artwork positions",command=self.reset_art,bootstyle="link").pack(fill=X,pady=2)
        self.art_label=ttk.Label(left,text="No artwork loaded",wraplength=290); self.art_label.pack(anchor="w",pady=5)
        ttk.Separator(left).pack(fill=X,pady=6); ttk.Label(left,text="Print sheet",font=("Segoe UI",11,"bold")).pack(anchor="w",pady=5)
        for label,var in (("Columns",self.cols),("Rows",self.rows),("Gap (mm)",self.gap)):
            row=ttk.Frame(left); row.pack(fill=X,pady=2); ttk.Label(row,text=label,width=20).pack(side=LEFT); ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(left,text="Save PDF sheet — A4",command=lambda:self.save_pdf(A4),bootstyle="success").pack(fill=X,pady=2)
        ttk.Button(left,text="Save PDF sheet — Letter",command=lambda:self.save_pdf(letter),bootstyle="success").pack(fill=X,pady=2)
        ttk.Button(left,text="Save SVG dieline",command=self.save_svg,bootstyle="info").pack(fill=X,pady=(8,2))
        self.info=ttk.Label(left,justify="left",wraplength=295); self.info.pack(anchor="w",pady=14)
        ttk.Label(right,text="Preview  •  black=cut  •  blue dashed=fold  •  red=trim",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,7))
        self.canvas=tk.Canvas(right,bg="#edf0f2",highlightthickness=1); self.canvas.pack(fill=BOTH,expand=True)
        self.canvas.bind("<Configure>",lambda _e:self.redraw()); self.canvas.bind("<ButtonPress-1>",self.start_drag); self.canvas.bind("<B1-Motion>",self.move_drag); self.canvas.bind("<ButtonRelease-1>",lambda _e:setattr(self,"drag",None))

    def apply(self):
        try:
            d={k:float(v.get()) for k,v in self.vars.items()}; d["cards"]=int(d["cards"])
            if d["cards"]<1 or d["bleed"]<0 or any(d[k]<=0 for k in d if k!="bleed"): raise ValueError
            self.box=Box(**d); self.redraw()
        except (ValueError,TypeError): messagebox.showerror("Invalid dimensions","Enter positive numeric dimensions and at least one card.")

    def load_art(self, side):
        path=filedialog.askopenfilename(title=f"Choose {side} artwork",filetypes=[("Images","*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        if not path:return
        if Image is None:
            messagebox.showerror("Missing dependency","Pillow is required for artwork. Run: pip install -r requirements.txt"); return
        try:
            with Image.open(path) as image: image.verify()
        except Exception as exc:
            messagebox.showerror("Invalid image",f"Could not open the selected image:\n{exc}"); return
        setattr(self,side,path)
        self.art_offset[side]=[0.,0.]
        self.art_label.config(text=f"Front: {Path(self.front).name if self.front else 'none'}\nBack: {Path(self.back).name if self.back else 'none'}")
        self.redraw()

    def reset_art(self): self.art_offset={"front":[0.,0.],"back":[0.,0.]}; self.redraw()

    def _coords(self,x,y): return self.origin[0]+x*self.preview_scale,self.origin[1]+(self.box.page_h-y)*self.preview_scale
    def _panel_rect(self,x,y,w,h): return [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]

    def redraw(self):
        if not hasattr(self,"canvas"):return
        self.canvas.delete("all"); self.photos.clear(); b=self.box
        self.preview_scale=min(max(self.canvas.winfo_width()-30,100)/b.page_w,max(self.canvas.winfo_height()-30,100)/b.page_h); self.origin=(15,15)
        def polygon(points,fill,outline="#111"):
            self.canvas.create_polygon([n for point in points for n in self._coords(point[0],point[1])],fill=fill,outline=outline,width=2)
        for x,y,w,h,name in b.panels(): polygon(self._panel_rect(x+b.bleed,y+b.bleed,w,h),"#fff" if name in ("front","back") else "#f4f5f6")
        for points,_kind in b.flaps(): polygon([(x+b.bleed,y+b.bleed) for x,y in points],"#f8f8f8")
        for x,y,w,h,name in b.panels():
            a,bb=self._coords(x+b.bleed+w/2,y+b.bleed+h/2); self.canvas.create_text(a,bb,text=name.upper(),fill="#555",font=("Segoe UI",10,"bold"))
        for x in (b.glue,b.glue+b.d,b.glue+b.d+b.w,b.glue+2*b.d+b.w):
            a,bb=self._coords(x+b.bleed,0); c,d=self._coords(x+b.bleed,b.page_h); self.canvas.create_line(a,bb,c,d,fill="#2865ad",dash=(6,4))
        for y in (b.y,b.y+b.h):
            a,bb=self._coords(b.bleed,y+b.bleed); c,d=self._coords(b.page_w-b.bleed,y+b.bleed); self.canvas.create_line(a,bb,c,d,fill="#2865ad",dash=(6,4))
        self.draw_art("front",self.front,b.glue+b.d+b.w,b.y,b.d,b.h); self.draw_art("back",self.back,b.glue,b.y,b.d,b.h)
        for x,y in ((0,0),(b.cut_w,0),(0,b.cut_h),(b.cut_w,b.cut_h)):
            a,bb=self._coords(x+b.bleed,y+b.bleed); self.canvas.create_oval(a-3,bb-3,a+3,bb+3,outline="#c33")
        self.info.config(text=f"Inside: {b.w:.2f} W × {b.d:.2f} D × {b.h:.2f} H mm\nDieline: {b.cut_w:.2f} × {b.cut_h:.2f} mm\nArtwork: loaded images are embedded in SVG and PDF\nPrint at 100%; test-fold first.")

    def draw_art(self,side,path,x,y,w,h):
        if not path or Image is None:return
        try:
            with Image.open(path) as source:
                image=ImageOps.exif_transpose(source).convert("RGB")
            zoom=1.0; image.thumbnail((max(20,int(w*self.preview_scale*zoom)),max(20,int(h*self.preview_scale*zoom))),Image.Resampling.LANCZOS)
            photo=ImageTk.PhotoImage(image); self.photos.append(photo); ox,oy=self.art_offset[side]
            a,bb=self._coords(x+b.bleed+w/2+ox*w,y+b.bleed+h/2+oy*h); self.canvas.create_image(a,bb,image=photo,anchor="center")
        except Exception as exc: self.info.config(text=f"Artwork preview failed: {exc}")

    def start_drag(self,event):
        b=self.box
        for side,path,x,y,w,h in (("front",self.front,b.glue+b.d+b.w,b.y,b.d,b.h),("back",self.back,b.glue,b.y,b.d,b.h)):
            if path:
                ox,oy=self.art_offset[side]; cx=self.origin[0]+(x+b.bleed+w/2+ox*w)*self.preview_scale; cy=self.origin[1]+(b.page_h-(y+b.bleed+h/2+oy*h))*self.preview_scale
                if abs(event.x-cx)<w*self.preview_scale/2 and abs(event.y-cy)<h*self.preview_scale/2:self.drag=(side,event.x,event.y); return
    def move_drag(self,event):
        if not self.drag:return
        side,px,py=self.drag; self.art_offset[side][0]+=(event.x-px)/(self.preview_scale*self.box.d); self.art_offset[side][1]-=(event.y-py)/(self.preview_scale*self.box.h); self.drag=(side,event.x,event.y); self.redraw()

    def _svg_image(self,path,x,y,w,h,side,H):
        if not path:return ""
        data=base64.b64encode(Path(path).read_bytes()).decode("ascii"); mime=mimetypes.guess_type(path)[0] or "image/png"; ox,oy=self.art_offset[side]
        return f'<image href="data:{mime};base64,{data}" x="{x+ox*w}" y="{H-(y+h+oy*h)}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>'

    def save_svg(self):
        path=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG files","*.svg")])
        if not path:return
        try:
            b=self.box; W,H=b.page_w,b.page_h; o=b.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
            def poly(points,stroke="#111",dash=""):
                pts=" ".join(f"{x+o},{H-(y+o)}" for x,y in points); out.append(f'<polygon points="{pts}" fill="none" stroke="{stroke}" stroke-width=".25" {f"stroke-dasharray=\"{dash}\"" if dash else ""}/>')
            for x,y,w,h,_ in b.panels():poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
            for points,_ in b.flaps():poly(points)
            for x,y,w,h,name in b.panels():
                if name in ("front","back"):out.append(self._svg_image(self.front if name=="front" else self.back,x+o,y+o,w,h,name,H))
            for x in (b.glue,b.glue+b.d,b.glue+b.d+b.w,b.glue+2*b.d+b.w): out.append(f'<path d="M{x+o} {H-o}V{H-b.page_h+o}" fill="none" stroke="#2865ad" stroke-width=".2" stroke-dasharray="2,1"/>')
            for y in (b.y,b.y+b.h):out.append(f'<path d="M{o} {H-y-o}H{W-o}" fill="none" stroke="#2865ad" stroke-width=".2" stroke-dasharray="2,1"/>')
            out.append("</svg>"); Path(path).write_text("\n".join(out),encoding="utf-8"); messagebox.showinfo("Saved",f"SVG saved to:\n{path}")
        except Exception as exc:messagebox.showerror("SVG export failed",str(exc))

    def save_pdf(self,pagesize):
        if Canvas is None:messagebox.showerror("Missing dependency","Install reportlab with: pip install -r requirements.txt");return
        try:
            cols,rows,gap=int(self.cols.get()),int(self.rows.get()),float(self.gap.get())
            if cols<1 or rows<1 or gap<0:raise ValueError
        except ValueError:messagebox.showerror("Invalid sheet","Columns/rows must be positive integers and gap non-negative.");return
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF files","*.pdf")])
        if not path:return
        try:
            b=self.box; pw,ph=pagesize; margin=12*mm; sw=cols*b.page_w+(cols-1)*gap; sh=rows*b.page_h+(rows-1)*gap; scale=min((pw-2*margin)/(sw*mm),(ph-2*margin)/(sh*mm)); ox=margin+(pw-2*margin-sw*mm*scale)/2; oy=margin+(ph-2*margin-sh*mm*scale)/2; pdf=Canvas(path,pagesize=pagesize)
            def draw_one(px,py):
                def P(x,y):return px+(x+b.bleed)*mm*scale,py+(y+b.bleed)*mm*scale
                def polygon(points):
                    q=pdf.beginPath();q.moveTo(*P(*points[0]));
                    for point in points[1:]:q.lineTo(*P(*point))
                    q.close();pdf.setStrokeColorRGB(.08,.08,.08);pdf.setDash();pdf.drawPath(q,stroke=1,fill=0)
                for x,y,w,h,_ in b.panels():polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
                for points,_ in b.flaps():polygon(points)
                for side,path,x,y,w,h in (("back",self.back,b.glue,b.y,b.d,b.h),("front",self.front,b.glue+b.d+b.w,b.y,b.d,b.h)):
                    if path:
                        try:
                            ox_img,oy_img=self.art_offset[side]; pdf.drawImage(ImageReader(path),P(x+ox_img*w,y+oy_img*h)[0],P(x+ox_img*w,y+oy_img*h+h)[1],width=w*mm*scale,height=h*mm*scale,preserveAspectRatio=True,anchor='sw',mask='auto')
                        except Exception: pass
                pdf.setStrokeColorRGB(.16,.4,.68);pdf.setDash(3,2)
                for x in (b.glue,b.glue+b.d,b.glue+b.d+b.w,b.glue+2*b.d+b.w):pdf.line(*P(x,0),*P(x,b.page_h))
                for y in (b.y,b.y+b.h):pdf.line(*P(0,y),*P(b.page_w,y))
                pdf.setDash()
            for row in range(rows):
                for col in range(cols):draw_one(ox+col*(b.page_w+gap)*mm*scale,oy+(rows-1-row)*(b.page_h+gap)*mm*scale)
            pdf.save();messagebox.showinfo("Saved",f"PDF saved to:\n{path}")
        except Exception as exc:messagebox.showerror("PDF export failed",str(exc))


if __name__=="__main__": App().mainloop()
