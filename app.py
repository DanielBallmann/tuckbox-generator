"""MTG tuckbox generator with four-panel artwork placement."""
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
    tuck: float = 25.0
    notch: float = 11.0

    @property
    def panel_w(self): return self.cards * self.thickness + 2 * self.clearance
    @property
    def panel_d(self): return self.card_w + 2 * self.clearance
    @property
    def panel_h(self): return self.card_h + 2 * self.clearance
    @property
    def bottom_flap(self): return min(self.panel_d * .62, self.panel_h * .56)
    @property
    def dust_flap(self): return min(self.panel_d * .42, self.panel_h * .38)
    @property
    def body_y(self): return self.bottom_flap
    @property
    def cut_width(self): return self.glue + 2 * self.panel_d + 2 * self.panel_w
    @property
    def cut_height(self): return self.bottom_flap + self.panel_h + self.tuck
    @property
    def page_width(self): return self.cut_width + 2 * self.bleed
    @property
    def page_height(self): return self.cut_height + 2 * self.bleed

    def panels(self):
        x, y = self.glue, self.body_y
        return {
            "back": (x, y, self.panel_d, self.panel_h),
            "side_left": (x + self.panel_d, y, self.panel_w, self.panel_h),
            "front": (x + self.panel_d + self.panel_w, y, self.panel_d, self.panel_h),
            "side_right": (x + 2 * self.panel_d + self.panel_w, y, self.panel_w, self.panel_h),
        }

    def flaps(self):
        x, y = self.glue, self.body_y
        d, w, h = self.panel_d, self.panel_w, self.panel_h
        dust, shoulder = self.dust_flap, min(6.0, d / 7)
        front, left, right, top = x + d + w, x + d, x + 2*d + w, y + h
        return [
            ([(x+shoulder,y),(x+d-shoulder,y),(x+d,y-self.bottom_flap),(x,y-self.bottom_flap)], "cut"),
            ([(front+shoulder,y),(front+d-shoulder,y),(front+d,y-self.bottom_flap),(front,y-self.bottom_flap)], "cut"),
            ([(left+3,y),(left+w-3,y),(left+w,y-dust+4),(left+w-4,y-dust),(left+4,y-dust),(left,y-dust+4)], "cut"),
            ([(right+3,y),(right+w-3,y),(right+w,y-dust+4),(right+w-4,y-dust),(right+4,y-dust),(right,y-dust+4)], "cut"),
            ([(x+3,top),(x+d-3,top),(x+d-5,top+dust),(x+5,top+dust)], "cut"),
            ([(front+4,top),(front+d-4,top),(front+d-7,top+self.tuck),
              (front+d/2+self.notch/2,top+self.tuck),(front+d/2+self.notch/2,top+self.tuck-4),
              (front+d/2-self.notch/2,top+self.tuck-4),(front+d/2-self.notch/2,top+self.tuck),
              (front+7,top+self.tuck)], "cut"),
            ([(left+3,top),(left+w-3,top),(left+w-4,top+dust),(left+4,top+dust)], "cut"),
            ([(right+3,top),(right+w-3,top),(right+w-4,top+dust),(right+4,top+dust)], "cut"),
        ]


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("MTG Tuckbox Generator")
        self.geometry("1240x820")
        self.minsize(1000, 680)
        self.dark = False
        self.box = Box()
        self.art_paths = {side: None for side in self.box.panels()}
        self.art_offsets = {side: [0.0, 0.0] for side in self.box.panels()}
        self.photos = []
        self.drag = None
        self.preview_scale = 1.0
        self.preview_origin = (15.0, 15.0)
        defaults = {"cards":22,"card_w":63,"card_h":88,"thickness":.30,"clearance":2,"bleed":3,"glue":12,"tuck":25,"notch":11}
        self.vars = {k: ttk.StringVar(value=str(v)) for k,v in defaults.items()}
        self.cols, self.rows, self.gap = ttk.StringVar(value="1"), ttk.StringVar(value="1"), ttk.StringVar(value="5")
        self.build_ui()
        self.after(100, self.redraw)

    def build_ui(self):
        root=ttk.Frame(self,padding=12); root.pack(fill=BOTH,expand=True)
        side=ttk.Frame(root,width=320); side.pack(side=LEFT,fill=Y,padx=(0,12)); side.pack_propagate(False)
        view=ttk.Frame(root); view.pack(side=RIGHT,fill=BOTH,expand=True)
        header=ttk.Frame(side); header.pack(fill=X,pady=(0,10))
        ttk.Label(header,text="MTG Tuckbox Generator",font=("Segoe UI",16,"bold"),bootstyle="primary").pack(side=LEFT)
        ttk.Button(header,text="☾",width=3,command=self.toggle_theme,bootstyle="secondary-outline").pack(side=RIGHT)
        self.size_box=ttk.Labelframe(side,text="Sizing options",padding=8,bootstyle="primary")
        labels={"cards":"Cards per pack","card_w":"Card width (mm)","card_h":"Card height (mm)","thickness":"Thickness/card (mm)","clearance":"Clearance (mm)","bleed":"Bleed (mm)","glue":"Glue tab (mm)","tuck":"Tuck flap depth (mm)","notch":"Thumb notch (mm)"}
        for key,var in self.vars.items():
            row=ttk.Frame(self.size_box);row.pack(fill=X,pady=2);ttk.Label(row,text=labels[key],width=20).pack(side=LEFT);ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(self.size_box,text="Apply dimensions",command=self.apply,bootstyle="primary").pack(fill=X,pady=(7,0))
        ttk.Button(side,text="Show sizing options",command=self.toggle_sizing,bootstyle="link").pack(anchor="w",pady=(0,5))
        art=ttk.Labelframe(side,text="Artwork — drag any panel image",padding=8,bootstyle="secondary");art.pack(fill=X,pady=6)
        for label,key in (("Load back artwork","back"),("Load left side artwork","side_left"),("Load front artwork","front"),("Load right side artwork","side_right")):
            ttk.Button(art,text=label,command=lambda k=key:self.load_art(k),bootstyle="secondary").pack(fill=X,pady=2)
        ttk.Button(art,text="Reset artwork positions",command=self.reset_art,bootstyle="link").pack(fill=X,pady=2)
        self.art_label=ttk.Label(art,text="No artwork loaded",wraplength=290);self.art_label.pack(anchor="w",pady=4)
        ttk.Label(art,text="Press and drag directly over an image. Each panel has independent artwork.",wraplength=290).pack(anchor="w")
        sheet=ttk.Labelframe(side,text="Print sheet",padding=8,bootstyle="secondary");sheet.pack(fill=X,pady=6)
        for label,var in (("Columns",self.cols),("Rows",self.rows),("Gap (mm)",self.gap)):
            row=ttk.Frame(sheet);row.pack(fill=X,pady=2);ttk.Label(row,text=label,width=20).pack(side=LEFT);ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(sheet,text="Save PDF sheet — A4",command=lambda:self.save_pdf(A4),bootstyle="success").pack(fill=X,pady=2)
        ttk.Button(sheet,text="Save PDF sheet — Letter",command=lambda:self.save_pdf(letter),bootstyle="success").pack(fill=X,pady=2)
        ttk.Button(sheet,text="Save SVG dieline",command=self.save_svg,bootstyle="info").pack(fill=X,pady=(6,2))
        self.info=ttk.Label(side,justify="left",wraplength=300);self.info.pack(anchor="w",pady=12)
        ttk.Label(view,text="Preview  •  red=cut  •  white/dark=score  •  artwork on all panels",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,7))
        self.canvas=tk.Canvas(view,bg="#edf0f2",highlightthickness=1);self.canvas.pack(fill=BOTH,expand=True)
        self.canvas.bind("<Configure>",lambda _e:self.redraw())
        self.canvas.bind("<ButtonPress-1>",self.start_drag);self.canvas.bind("<B1-Motion>",self.move_drag);self.canvas.bind("<ButtonRelease-1>",self.end_drag)

    def toggle_sizing(self):
        if self.size_box.winfo_ismapped(): self.size_box.pack_forget()
        else: self.size_box.pack(fill=X,before=self.size_box.master.winfo_children()[1],pady=(0,8))

    def toggle_theme(self):
        self.dark=not self.dark;self.style.theme_use("darkly" if self.dark else "flatly");self.canvas.config(bg="#1f2329" if self.dark else "#edf0f2");self.redraw()

    def apply(self):
        try:
            values={k:float(v.get()) for k,v in self.vars.items()};values["cards"]=int(values["cards"])
            if values["cards"]<1 or values["bleed"]<0 or any(values[k]<=0 for k in values if k!="bleed"):raise ValueError
            self.box=Box(**values)
            for side in self.box.panels(): self.art_paths.setdefault(side,None);self.art_offsets.setdefault(side,[0.,0.])
            self.redraw()
        except (ValueError,TypeError):messagebox.showerror("Invalid dimensions","Enter positive numeric dimensions and at least one card.")

    def load_art(self,side):
        path=filedialog.askopenfilename(title=f"Choose {side} artwork",filetypes=[("Images","*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        if not path:return
        if Image is None:messagebox.showerror("Missing dependency","Install Pillow with: pip install -r requirements.txt");return
        try:
            with Image.open(path) as im:im.verify()
        except Exception as exc:messagebox.showerror("Invalid image",str(exc));return
        self.art_paths[side]=path;self.art_offsets[side]=[0.,0.];self.update_art_label();self.redraw()

    def update_art_label(self):
        names=[f"{side}: {Path(path).name}" for side,path in self.art_paths.items() if path]
        self.art_label.config(text="\n".join(names) if names else "No artwork loaded")

    def reset_art(self):
        self.art_offsets={side:[0.,0.] for side in self.art_paths};self.redraw()

    def page_xy(self,x,y):
        return (self.preview_origin[0]+(x+self.box.bleed)*self.preview_scale,self.preview_origin[1]+(self.box.page_height-y-self.box.bleed)*self.preview_scale)

    def artwork_rect(self,side):
        x,y,w,h=self.box.panels()[side];ox,oy=self.art_offsets[side];return x+ox,y+oy,w,h

    def redraw(self):
        if not hasattr(self,"canvas"):return
        b=self.box;self.canvas.delete("all");self.photos.clear();self.preview_scale=min(max(self.canvas.winfo_width()-30,100)/b.page_width,max(self.canvas.winfo_height()-30,100)/b.page_height);self.preview_origin=(15.,15.)
        cut="#dc3545" if not self.dark else "#ff6675";score="#ffffff" if not self.dark else "#adb5bd";panel="#fff" if not self.dark else "#30343b";side="#f0f2f4" if not self.dark else "#272b31"
        def poly(points,fill):self.canvas.create_polygon([n for p in points for n in self.page_xy(*p)],fill=fill,outline=cut,width=2)
        for x,y,w,h,name in b.body_panels():poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],panel if name in ("front","back") else side)
        for points,_ in b.flaps():poly(points,side)
        for x,y,w,h,name in b.body_panels():a,bb=self.page_xy(x+w/2,y+h/2);self.canvas.create_text(a,bb,text=name.upper(),fill="#6c757d",font=("Segoe UI",10,"bold"))
        for x in (b.glue,b.glue+b.panel_d,b.glue+b.panel_d+b.panel_w,b.glue+2*b.panel_d+b.panel_w):a,bb=self.page_xy(x,0);c,d=self.page_xy(x,b.page_height);self.canvas.create_line(a,bb,c,d,fill=score,dash=(7,4),width=2)
        for y in (b.body_y,b.body_y+b.panel_h):a,bb=self.page_xy(0,y);c,d=self.page_xy(b.page_width,y);self.canvas.create_line(a,bb,c,d,fill=score,dash=(7,4),width=2)
        for side_name in self.art_paths:self.draw_art(side_name)
        for x,y in ((0,0),(b.cut_width,0),(0,b.cut_height),(b.cut_width,b.cut_height)):a,bb=self.page_xy(x,y);self.canvas.create_line(a-5,bb,a+5,bb,fill=cut);self.canvas.create_line(a,bb-5,a,bb+5,fill=cut)
        self.info.config(text=f"Cards per pack: {b.cards}\nInside: {b.panel_w:.2f} W × {b.panel_d:.2f} D × {b.panel_h:.2f} H mm\nArtwork panels: {sum(bool(p) for p in self.art_paths.values())}/4\nDrag any artwork image directly\nPrint at 100%; test-fold first.")

    def draw_art(self,side):
        path=self.art_paths[side]
        if not path or Image is None:return
        try:
            x,y,w,h=self.artwork_rect(side)
            with Image.open(path) as source:image=ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"),(max(2,round(w*self.preview_scale)),max(2,round(h*self.preview_scale))),method=Image.Resampling.LANCZOS)
            photo=ImageTk.PhotoImage(image);self.photos.append(photo);a,bb=self.page_xy(x+w/2,y+h/2);self.canvas.create_image(a,bb,image=photo,anchor="center",tags=("artwork",f"art:{side}"))
        except Exception as exc:self.info.config(text=f"Artwork preview failed: {exc}")

    def start_drag(self,event):
        # Coordinate hit-testing is stable even when canvas items overlap or are redrawn.
        for side in reversed(tuple(self.art_paths)):
            if not self.art_paths[side]:continue
            x,y,w,h=self.artwork_rect(side);cx,cy=self.page_xy(x+w/2,y+h/2)
            if abs(event.x-cx)<=w*self.preview_scale/2 and abs(event.y-cy)<=h*self.preview_scale/2:
                self.drag=(side,event.x,event.y);self.canvas.configure(cursor="fleur");return
        self.drag=None

    def move_drag(self,event):
        if not self.drag:return
        side,px,py=self.drag;self.art_offsets[side][0]+=(event.x-px)/self.preview_scale;self.art_offsets[side][1]-=(event.y-py)/self.preview_scale;self.drag=(side,event.x,event.y);self.redraw()

    def end_drag(self,_event):self.drag=None;self.canvas.configure(cursor="")

    def svg_art(self,side):
        path=self.art_paths[side]
        if not path:return ""
        x,y,w,h=self.artwork_rect(side);o=self.box.bleed;H=self.box.page_height;data=base64.b64encode(Path(path).read_bytes()).decode("ascii");mime=mimetypes.guess_type(path)[0] or "image/png";clip=f"clip-{side}"
        return f'<clipPath id="{clip}"><rect x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}"/></clipPath><image href="data:{mime};base64,{data}" x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip})"/>'

    def save_svg(self):
        path=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG files","*.svg")])
        if not path:return
        try:
            b,W,H,o=self.box,self.box.page_width,self.box.page_height,self.box.bleed;out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
            def polygon(points,stroke="#dc3545",dash=""):
                p=" ".join(f"{x+o},{H-y-o}" for x,y in points);out.append(f'<polygon points="{p}" fill="none" stroke="{stroke}" stroke-width=".25"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>' )
            for x,y,w,h,_ in b.body_panels():polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
            for points,_ in b.flaps():polygon(points)
            out.extend(self.svg_art(side) for side in self.art_paths)
            for x in (b.glue,b.glue+b.panel_d,b.glue+b.panel_d+b.panel_w,b.glue+2*b.panel_d+b.panel_w):out.append(f'<path d="M{x+o} {H-o}V{H-b.page_height+o}" fill="none" stroke="#ffffff" stroke-width=".2" stroke-dasharray="2,1"/>')
            for y in (b.body_y,b.body_y+b.panel_h):out.append(f'<path d="M{o} {H-y-o}H{W-o}" fill="none" stroke="#ffffff" stroke-width=".2" stroke-dasharray="2,1"/>')
            Path(path).write_text("\n".join(out+["</svg>"]),encoding="utf-8");messagebox.showinfo("Saved",f"SVG saved to:\n{path}")
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
            b=self.box;pw,ph=pagesize;margin=12*mm;sw=cols*b.page_width+(cols-1)*gap;sh=rows*b.page_height+(rows-1)*gap;scale=min((pw-2*margin)/(sw*mm),(ph-2*margin)/(sh*mm));left=margin+(pw-2*margin-sw*mm*scale)/2;bottom=margin+(ph-2*margin-sh*mm*scale)/2;pdf=Canvas(path,pagesize=pagesize)
            def draw_one(px,py):
                def P(x,y):return px+(x+b.bleed)*mm*scale,py+(y+b.bleed)*mm*scale
                def shape(points):
                    q=pdf.beginPath();q.moveTo(*P(*points[0]));
                    for point in points[1:]:q.lineTo(*P(*point))
                    q.close();pdf.setStrokeColorRGB(.86,.1,.18);pdf.setDash();pdf.drawPath(q,stroke=1,fill=0)
                for x,y,w,h,_ in b.body_panels():shape([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
                for points,_ in b.flaps():shape(points)
                if ImageReader:
                    for side in self.art_paths:
                        if self.art_paths[side]:
                            x,y,w,h=self.artwork_rect(side);pdf.drawImage(ImageReader(self.art_paths[side]),*P(x,y),width=w*mm*scale,height=h*mm*scale,preserveAspectRatio=False,mask="auto")
                pdf.setStrokeColorRGB(1,1,1);pdf.setDash(3,2)
                for x in (b.glue,b.glue+b.panel_d,b.glue+b.panel_d+b.panel_w,b.glue+2*b.panel_d+b.panel_w):pdf.line(*P(x,0),*P(x,b.page_height))
                for y in (b.body_y,b.body_y+b.panel_h):pdf.line(*P(0,y),*P(b.page_width,y))
                pdf.setDash()
            for row in range(rows):
                for col in range(cols):draw_one(left+col*(b.page_width+gap)*mm*scale,bottom+(rows-1-row)*(b.page_height+gap)*mm*scale)
            pdf.save();messagebox.showinfo("Saved",f"PDF saved to:\n{path}")
        except Exception as exc:messagebox.showerror("PDF export failed",str(exc))


if __name__=="__main__":App().mainloop()
