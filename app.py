"""Printable MTG tuckbox dieline.

The net follows gcoulby/netrunner-tuckbox-creator: glue tab, front, left
side, back, right side from left to right.  The back carries the two depth
panels and tuck flaps; the side panels carry dust flaps.  Red lines cut and
grey dashed lines score/fold.
"""
from __future__ import annotations
import base64, mimetypes, tkinter as tk
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
    cards:int=22; card_w:float=63; card_h:float=88; thickness:float=.30
    clearance:float=2; bleed:float=3; glue:float=12; tuck_lip:float=19.05; notch:float=11
    @property
    def width(self): return max(1,self.cards*self.thickness+2*self.clearance)
    @property
    def depth(self): return self.card_w+2*self.clearance
    @property
    def height(self): return self.card_h+2*self.clearance
    @property
    def flap(self): return self.tuck_lip
    @property
    def body_y(self): return self.flap+self.depth
    @property
    def sheet_w(self): return self.glue+2*self.width+2*self.depth+2*self.bleed
    @property
    def sheet_h(self): return self.body_y+self.height+self.depth+self.flap+2*self.bleed

    def panels(self):
        """Artwork faces in the physical order used by the reference net."""
        x,y,w,d,h=self.glue,self.body_y,self.width,self.depth,self.height
        return {
            'front':(x,y,w,h), 'side_left':(x+w,y,d,h),
            'back':(x+w+d,y,w,h), 'side_right':(x+2*w+d,y,d,h),
            # These are the actual tuck flaps, not the depth panels.
            'top':(x+w+d,y+h+d,w,self.flap),
            'bottom':(x+w+d,y-d-self.flap,w,self.flap),
        }

    def rectangles(self):
        """All material regions in the blank, including unprinted flaps."""
        p=self.panels(); x,y,w,d,h=self.glue,self.body_y,self.width,self.depth,self.height
        f=self.flap
        return [
            ('glue',(0,y,w if False else self.glue,h)),
            ('front',(x,y,w,h)), ('left',(x+w,y,d,h)), ('back',(x+w+d,y,w,h)), ('right',(x+2*w+d,y,d,h)),
            ('left_bottom',(x+w,y-d,d,d)), ('left_top',(x+w,y+h,d,f)),
            ('right_bottom',(x+2*w+d,y-d,d,d)), ('right_top',(x+2*w+d,y+h,d,f)),
            ('back_bottom_depth',(x+w+d,y-d,w,d)), ('back_top_depth',(x+w+d,y+h,w,d)),
            ('bottom_tuck',(x+w+d,y-d-f,w,f)), ('top_tuck',(x+w+d,y+h+d,w,f)),
        ]

    def body(self):
        p=self.panels()
        return [(x,y,w,h,n) for n,(x,y,w,h) in p.items() if n in {'front','side_left','back','side_right'}]

    def fold_segments(self):
        x,y,w,d,h=self.glue,self.body_y,self.width,self.depth,self.height; f=self.flap
        return [
            ((x,y),(x,y+h)), ((x+w,y),(x+w,y+h)), ((x+w+d,y),(x+w+d,y+h)), ((x+2*w+d,y),(x+2*w+d,y+h)),
            # top and bottom hinges of the four body faces
            ((x,y+h),(x+w,y+h)), ((x+w,y+h),(x+w+d,y+h)), ((x+w+d,y+h),(x+2*w+d,y+h)), ((x+2*w+d,y+h),(x+2*w+2*d,y+h)),
            ((x,y),(x+w,y)), ((x+w,y),(x+w+d,y)), ((x+w+d,y),(x+2*w+d,y)), ((x+2*w+d,y),(x+2*w+2*d,y)),
            # back's depth panels and tuck flaps
            ((x+w+d,y-d),(x+2*w+d,y-d)), ((x+w+d,y-d-f),(x+2*w+d,y-d-f)),
            ((x+w+d,y+h),(x+2*w+d,y+h)), ((x+w+d,y+h+d),(x+2*w+d,y+h+d)),
        ]

    def cut_segments(self):
        """Outside perimeter only; no cut line is drawn across a hinge."""
        x,y,w,d,h=self.glue,self.body_y,self.width,self.depth,self.height; f=self.flap
        # perimeter of connected blank, walking around each exposed outer edge
        return [
            ((0,y),(0,y+h)), ((0,y),(x,y)), ((0,y+h),(x,y+h)),
            ((x+w+d,y-d-f),(x+w+d,y-d)), ((x+w+d,y-d-f),(x+2*w+d,y-d-f)),
            ((x+2*w+d,y-d-f),(x+2*w+d,y-d)),
            ((x+w+d,y-d),(x+w+d,y-d)), # harmless zero-length avoided by renderer
            ((x+w+d,y-d),(x+w+d,y-d)),
            ((x+w+d,y-d),(x+w+d,y-d)),
            # lower dust flaps
            ((x+w,y-d),(x+w+d,y-d)), ((x+w,y-d),(x+w,y-d+4)), ((x+w,y-d+4),(x+w+4,y-d)),
            ((x+w+d,y-d),(x+2*w+d,y-d)), ((x+2*w+d,y-d),(x+2*w+d,y-d+4)),
            ((x+2*w+d,y-d+4),(x+2*w+d+4,y-d)),
            # side outer edges and upper dust flaps
            ((x+w,y),(x+w,y+h)), ((x+2*w+d,y),(x+2*w+d,y+h)),
            ((x+w,y+h),(x+w+4,y+h+f)), ((x+w+4,y+h+f),(x+w+d-4,y+h+f)), ((x+w+d-4,y+h+f),(x+w+d,y+h)),
            ((x+2*w+d,y+h),(x+2*w+d+4,y+h+f)), ((x+2*w+d+4,y+h+f),(x+2*w+2*d-4,y+h+f)), ((x+2*w+2*d-4,y+h+f),(x+2*w+2*d,y+h)),
            # upper tuck flap
            ((x+w+d,y+h+d),(x+w+d,y+h+d+f)), ((x+w+d,y+h+d+f),(x+2*w+d,y+h+d+f)), ((x+2*w+d,y+h+d+f),(x+2*w+d,y+h+d)),
            # top tuck thumb notch: cut with a shallow central notch
            ((x+w+d,y+h+d),(x+w+d+7,y+h+d+f)), ((x+2*w+d-7,y+h+d+f),(x+2*w+d,y+h+d)),
        ]

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('MTG Tuckbox Generator'); self.geometry('1180x780')
        self.box=Box(); self.art={k:None for k in self.box.panels()}; self.photos=[]; self.scale=1; self.origin=(15,15)
        self.vars={k:ttk.StringVar(value=str(v)) for k,v in {'cards':22,'card_w':63,'card_h':88,'thickness':.30,'clearance':2,'bleed':3,'glue':12,'tuck_lip':19.05,'notch':11}.items()}
        self.build_ui(); self.after(100,self.redraw)
    def build_ui(self):
        root=ttk.Frame(self,padding=12); root.pack(fill=BOTH,expand=True); side=ttk.Frame(root,width=300); side.pack(side=LEFT,fill=Y,padx=(0,12)); side.pack_propagate(False); view=ttk.Frame(root); view.pack(side=RIGHT,fill=BOTH,expand=True)
        ttk.Label(side,text='MTG Tuckbox Generator',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=(0,10)); box=ttk.Labelframe(side,text='Box dimensions (mm)',padding=8); box.pack(fill=X)
        labels={'cards':'Cards','card_w':'Card width','card_h':'Card height','thickness':'Thickness/card','clearance':'Clearance','bleed':'Bleed','glue':'Glue tab','tuck_lip':'Tuck flap','notch':'Thumb notch'}
        for k,v in self.vars.items():
            r=ttk.Frame(box); r.pack(fill=X,pady=2); ttk.Label(r,text=labels[k],width=17).pack(side=LEFT); ttk.Entry(r,textvariable=v,width=9).pack(side=RIGHT)
        ttk.Button(box,text='Apply dimensions',command=self.apply,bootstyle='primary').pack(fill=X,pady=(7,0)); art=ttk.Labelframe(side,text='Artwork (physical faces)',padding=8); art.pack(fill=X,pady=8)
        for label,face in (('Front','front'),('Left side','side_left'),('Back','back'),('Right side','side_right'),('Top tuck flap','top'),('Bottom tuck flap','bottom')): ttk.Button(art,text=f'Choose {label}',command=lambda f=face:self.choose_art(f)).pack(fill=X,pady=2)
        self.art_label=ttk.Label(art,text='No artwork loaded',wraplength=270); self.art_label.pack(anchor='w',pady=4); ttk.Button(side,text='Save SVG dieline',command=self.save_svg,bootstyle='info').pack(fill=X,pady=2); ttk.Button(side,text='Save PDF (A4)',command=lambda:self.save_pdf(A4),bootstyle='success').pack(fill=X,pady=2); ttk.Button(side,text='Save PDF (Letter)',command=lambda:self.save_pdf(letter),bootstyle='success').pack(fill=X,pady=2)
        self.info=ttk.Label(side,justify='left',wraplength=285); self.info.pack(anchor='w',pady=12); ttk.Label(view,text='Preview • red=cut • grey dashed=fold',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,7)); self.canvas=tk.Canvas(view,bg='#edf0f2',highlightthickness=1); self.canvas.pack(fill=BOTH,expand=True); self.canvas.bind('<Configure>',lambda _:self.redraw())
    def apply(self):
        try:
            v={k:float(x.get()) for k,x in self.vars.items()}; v['cards']=int(v['cards'])
            if v['cards']<1 or v['bleed']<0 or any(n<=0 for k,n in v.items() if k!='bleed'): raise ValueError
            old=self.art; self.box=Box(**v); self.art={k:old.get(k) for k in self.box.panels()}; self.update_art_label(); self.redraw()
        except (ValueError,TypeError): messagebox.showerror('Invalid dimensions','Enter positive dimensions and at least one card.')
    def choose_art(self,face):
        p=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff')])
        if not p or Image is None:return
        try:
            with Image.open(p) as im: im.verify()
            self.art[face]=str(Path(p).resolve()); self.update_art_label(); self.redraw()
        except Exception as e: messagebox.showerror('Invalid artwork',str(e))
    def update_art_label(self): self.art_label.config(text='\n'.join(f'{f}: {Path(p).name}' for f,p in self.art.items() if p) or 'No artwork loaded')
    def page_xy(self,x,y): return self.origin[0]+(x+self.box.bleed)*self.scale,self.origin[1]+(self.box.sheet_h-y-self.box.bleed)*self.scale
    def redraw(self):
        if not hasattr(self,'canvas'):return
        b=self.box; self.canvas.delete('all'); self.photos.clear(); self.scale=min(max(self.canvas.winfo_width()-30,100)/b.sheet_w,max(self.canvas.winfo_height()-30,100)/b.sheet_h); self.origin=(15,15)
        def poly(x,y,w,h,fill): self.canvas.create_rectangle(*self.page_xy(x,y),*self.page_xy(x+w,y+h),fill=fill,outline='')
        for n,x in b.rectangles(): poly(*x,'#fff' if n in ('front','back') else '#f0f2f4')
        for f,p in self.art.items(): self.draw_art(f,p)
        for a,z in b.cut_segments():
            if a!=z:self.canvas.create_line(*self.page_xy(*a),*self.page_xy(*z),fill='#dc3545',width=2)
        for a,z in b.fold_segments(): self.canvas.create_line(*self.page_xy(*a),*self.page_xy(*z),fill='#6c757d',dash=(7,4),width=2)
        self.info.config(text=f'Net: glue → front → left side → back → right side\nInternal: {b.width:.1f} W × {b.depth:.1f} D × {b.height:.1f} H mm\nSheet: {b.sheet_w:.1f} × {b.sheet_h:.1f} mm\nArtwork: {sum(bool(p) for p in self.art.values())}/6')
    def draw_art(self,f,p):
        if not p or Image is None:return
        try:
            x,y,w,h=self.box.panels()[f]
            with Image.open(p) as s: im=ImageOps.fit(ImageOps.exif_transpose(s).convert('RGB'),(max(2,round(w*self.scale)),max(2,round(h*self.scale))))
            q=ImageTk.PhotoImage(im); self.photos.append(q); self.canvas.create_image(*self.page_xy(x+w/2,y+h/2),image=q,anchor='center')
        except Exception as e:self.info.config(text=f'Artwork preview failed: {e}')
    def save_svg(self):
        p=filedialog.asksaveasfilename(defaultextension='.svg',filetypes=[('SVG files','*.svg')]);
        if not p:return
        b=self.box; W,H=b.sheet_w,b.sheet_h;o=b.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
        for f,q in self.art.items():
            if q:
                x,y,w,h=b.panels()[f]; data=base64.b64encode(Path(q).read_bytes()).decode(); out.append(f'<image href="data:{mimetypes.guess_type(q)[0] or "image/jpeg"};base64,{data}" x="{x+o}" y="{H-y-o-h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')
        for a,z in b.cut_segments():
            if a!=z:out.append(f'<path d="M{a[0]+o} {H-a[1]-o}L{z[0]+o} {H-z[1]-o}" stroke="#dc3545" stroke-width=".25" fill="none"/>')
        for a,z in b.fold_segments():out.append(f'<path d="M{a[0]+o} {H-a[1]-o}L{z[0]+o} {H-z[1]-o}" stroke="#777" stroke-dasharray="2,1" fill="none"/>')
        Path(p).write_text('\n'.join(out+['</svg>']),encoding='utf8');messagebox.showinfo('Saved',f'SVG saved to:\n{p}')
    def save_pdf(self,size):
        if Canvas is None:messagebox.showerror('Missing dependency','Install dependencies with: pip install -r requirements.txt');return
        p=filedialog.asksaveasfilename(defaultextension='.pdf',filetypes=[('PDF files','*.pdf')]);
        if not p:return
        try:
            b=self.box; pw,ph=size; margin=12*mm; scale=min((pw-2*margin)/(b.sheet_w*mm),(ph-2*margin)/(b.sheet_h*mm)); ox=margin+(pw-2*margin-b.sheet_w*mm*scale)/2; oy=margin+(ph-2*margin-b.sheet_h*mm*scale)/2; pdf=Canvas(p,pagesize=size)
            def P(x,y):return ox+(x+b.bleed)*mm*scale,oy+(y+b.bleed)*mm*scale
            for f,q in self.art.items():
                if q:
                    x,y,w,h=b.panels()[f];pdf.drawImage(ImageReader(q),*P(x,y),width=w*mm*scale,height=h*mm*scale,preserveAspectRatio=False,mask='auto')
            pdf.setStrokeColorRGB(.86,.1,.18);pdf.setDash()
            for a,z in b.cut_segments():
                if a!=z:pdf.line(*P(*a),*P(*z))
            pdf.setStrokeColorRGB(.45,.45,.45);pdf.setDash(3,2)
            for a,z in b.fold_segments():pdf.line(*P(*a),*P(*z))
            pdf.save();messagebox.showinfo('Saved',f'PDF saved to:\n{p}')
        except Exception as e:messagebox.showerror('PDF export failed',str(e))
if __name__=='__main__':App().mainloop()
