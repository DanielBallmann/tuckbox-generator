"""MTG tuckbox generator with a styled ttkbootstrap UI and shaped closure flaps."""
from __future__ import annotations

import base64
import mimetypes
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X, Y

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
    def cut_w(self): return self.glue + self.d + self.w + self.d + self.w
    @property
    def cut_h(self): return self.bottom_depth + self.h + self.tuck
    @property
    def page_w(self): return self.cut_w + 2 * self.bleed
    @property
    def page_h(self): return self.cut_h + 2 * self.bleed

    def panels(self):
        x, y = self.glue, self.y
        return [(x,y,self.d,self.h,'back'), (x+self.d,y,self.w,self.h,'side'),
                (x+self.d+self.w,y,self.d,self.h,'front'),
                (x+2*self.d+self.w,y,self.w,self.h,'side')]

    def flaps(self):
        """Return shaped flap polygons as (points, kind).

        Main flaps have tapered shoulders; dust flaps are inset and chamfered;
        the front top flap has a locking nose rather than a plain rectangle.
        """
        c, x, y = self, self.glue, self.y
        def poly(points, kind): return (points, kind)
        # bottom back/front: broad overlapping flaps with clipped shoulders
        main = c.bottom_depth; shoulder = min(6.0, c.d / 7)
        bottom_back = [(x+shoulder,y), (x+c.d-shoulder,y), (x+c.d,y-main), (x,y-main)]
        fx = x+c.d+c.w
        bottom_front = [(fx+shoulder,y), (fx+c.d-shoulder,y), (fx+c.d,y-main), (fx,y-main)]
        # side dust flaps: shorter, chamfered so they do not collide when folded
        dust = c.dust_depth; inset = min(3.0, c.w/3)
        sx = x+c.d; rx = x+2*c.d+c.w
        side_bottom = [(sx+inset,y), (sx+c.w-inset,y), (sx+c.w,y-dust+4), (sx+c.w-4,y-dust), (sx+4,y-dust), (sx,y-dust+4)]
        side_bottom_r = [(rx+inset,y), (rx+c.w-inset,y), (rx+c.w,y-dust+4), (rx+c.w-4,y-dust), (rx+4,y-dust), (rx,y-dust+4)]
        # top back is a dust flap; top front is the tuck flap with a locking nose
        top_back = [(x+3,y+c.h), (x+c.d-3,y+c.h), (x+c.d-5,y+c.h+c.dust_depth), (x+5,y+c.h+c.dust_depth)]
        top_front = [(fx+4,y+c.h), (fx+c.d-4,y+c.h), (fx+c.d-7,y+c.h+c.tuck), (fx+c.d/2+5,y+c.h+c.tuck), (fx+c.d/2,y+c.h+c.tuck+4), (fx+c.d/2-5,y+c.h+c.tuck), (fx+7,y+c.h+c.tuck)]
        top_side = [(sx+inset,y+c.h), (sx+c.w-inset,y+c.h), (sx+c.w-4,y+c.h+c.dust_depth), (sx+4,y+c.h+c.dust_depth)]
        top_side_r = [(rx+inset,y+c.h), (rx+c.w-inset,y+c.h), (rx+c.w-4,y+c.h+c.dust_depth), (rx+4,y+c.h+c.dust_depth)]
        return [poly(bottom_back,'bottom'), poly(bottom_front,'bottom'), poly(side_bottom,'dust'), poly(side_bottom_r,'dust'), poly(top_back,'dust'), poly(top_front,'tuck'), poly(top_side,'dust'), poly(top_side_r,'dust')]


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename='flatly')
        self.title('MTG Tuckbox Generator'); self.geometry('1240x820'); self.minsize(1000,680)
        self.box = Box(); self.front = self.back = None; self.photos=[]; self.drag=None
        self.art_offset={'front':[0.,0.], 'back':[0.,0.]}; self.scale=1.; self.origin=(0,0)
        self.vars={k:ttk.StringVar(value=str(v)) for k,v in {'cards':60,'card_w':63,'card_h':88,'thickness':.30,'clearance':2,'bleed':3,'glue':12,'tuck':25}.items()}
        self.cols=ttk.StringVar(value='1'); self.rows=ttk.StringVar(value='1'); self.gap=ttk.StringVar(value='5')
        self.ui(); self.after(100,self.redraw)

    def ui(self):
        root=ttk.Frame(self,padding=12); root.pack(fill=BOTH,expand=True)
        left=ttk.Frame(root,width=310); left.pack(side=LEFT,fill=Y,padx=(0,12)); left.pack_propagate(False)
        right=ttk.Frame(root); right.pack(side=RIGHT,fill=BOTH,expand=True)
        ttk.Label(left,text='MTG Tuckbox Generator',font=('Segoe UI',16,'bold'),bootstyle='primary').pack(anchor='w',pady=(0,10))
        labels={'cards':'Cards','card_w':'Card width (mm)','card_h':'Card height (mm)','thickness':'Thickness/card (mm)','clearance':'Clearance (mm)','bleed':'Bleed (mm)','glue':'Glue tab (mm)','tuck':'Tuck flap depth (mm)'}
        for key,var in self.vars.items():
            row=ttk.Frame(left); row.pack(fill=X,pady=2); ttk.Label(row,text=labels[key],width=20).pack(side=LEFT); ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(left,text='Apply dimensions',command=self.apply,bootstyle='primary').pack(fill=X,pady=(8,10))
        ttk.Separator(left).pack(fill=X,pady=5); ttk.Label(left,text='Artwork',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=5)
        ttk.Button(left,text='Load front artwork',command=lambda:self.load_art('front'),bootstyle='secondary').pack(fill=X,pady=2)
        ttk.Button(left,text='Load back artwork',command=lambda:self.load_art('back'),bootstyle='secondary').pack(fill=X,pady=2)
        ttk.Button(left,text='Reset artwork positions',command=self.reset_art,bootstyle='link').pack(fill=X,pady=2)
        self.art_label=ttk.Label(left,text='No artwork loaded',wraplength=290); self.art_label.pack(anchor='w',pady=5)
        ttk.Separator(left).pack(fill=X,pady=6); ttk.Label(left,text='Print sheet',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=5)
        for label,var in [('Columns',self.cols),('Rows',self.rows),('Gap (mm)',self.gap)]:
            row=ttk.Frame(left); row.pack(fill=X,pady=2); ttk.Label(row,text=label,width=20).pack(side=LEFT); ttk.Entry(row,textvariable=var,width=10).pack(side=RIGHT)
        ttk.Button(left,text='Save PDF sheet — A4',command=lambda:self.save_pdf(A4),bootstyle='success').pack(fill=X,pady=2)
        ttk.Button(left,text='Save PDF sheet — Letter',command=lambda:self.save_pdf(letter),bootstyle='success').pack(fill=X,pady=2)
        ttk.Button(left,text='Save SVG dieline',command=self.save_svg,bootstyle='info').pack(fill=X,pady=(8,2))
        self.info=ttk.Label(left,justify='left',wraplength=295); self.info.pack(anchor='w',pady=14)
        ttk.Label(right,text='Preview  •  black=cut  •  blue dashed=fold  •  red=trim',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,7))
        self.canvas=tk.Canvas(right,bg='#edf0f2',highlightthickness=1); self.canvas.pack(fill=BOTH,expand=True)
        self.canvas.bind('<Configure>',lambda e:self.redraw()); self.canvas.bind('<ButtonPress-1>',self.start_drag); self.canvas.bind('<B1-Motion>',self.move_drag); self.canvas.bind('<ButtonRelease-1>',lambda e:setattr(self,'drag',None))

    def apply(self):
        try:
            d={k:float(v.get()) for k,v in self.vars.items()}; d['cards']=int(d['cards'])
            if d['cards']<1 or d['bleed']<0 or any(d[k]<=0 for k in d if k!='bleed'): raise ValueError
            self.box=Box(**d); self.redraw()
        except (TypeError,ValueError): messagebox.showerror('Invalid dimensions','Enter positive numeric dimensions and at least one card.')

    def load_art(self,side):
        p=filedialog.askopenfilename(filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp *.gif')])
        if p: setattr(self,side,p); self.art_label.config(text=f"Front: {Path(self.front).name if self.front else 'none'}\nBack: {Path(self.back).name if self.back else 'none'}"); self.redraw()
    def reset_art(self): self.art_offset={'front':[0.,0.],'back':[0.,0.]}; self.redraw()

    def redraw(self):
        if not hasattr(self,'canvas'): return
        self.canvas.delete('all'); self.photos.clear(); b=self.box
        self.scale=min(max(self.canvas.winfo_width()-30,100)/b.page_w,max(self.canvas.winfo_height()-30,100)/b.page_h); self.origin=(15,15)
        def xy(x,y): return self.origin[0]+x*self.scale,self.origin[1]+(b.page_h-y)*self.scale
        def polygon(points,fill,outline='#111'):
            self.canvas.create_polygon([v for p in points for v in xy(p[0]+b.bleed,p[1]+b.bleed)],fill=fill,outline=outline,width=2)
        for x,y,w,h,n in b.panels(): polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],'#fff' if n in ('front','back') else '#f4f5f6')
        for points,kind in b.flaps(): polygon(points,'#f8f8f8')
        for x,y,w,h,n in b.panels():
            a,bb=xy(x+b.bleed+w/2,y+b.bleed+h/2); self.canvas.create_text(a,bb,text=n.upper(),fill='#555',font=('Segoe UI',10,'bold'))
        for x in (b.glue,b.glue+b.d,b.glue+b.d+b.w,b.glue+2*b.d+b.w):
            a,bb=xy(x+b.bleed,0); c,d=xy(x+b.bleed,b.page_h); self.canvas.create_line(a,bb,c,d,fill='#2865ad',dash=(6,4))
        for y in (b.y,b.y+b.h):
            a,bb=xy(b.bleed,y+b.bleed); c,d=xy(b.page_w-b.bleed,y+b.bleed); self.canvas.create_line(a,bb,c,d,fill='#2865ad',dash=(6,4))
        self.draw_art('front',self.front,b.glue+b.d+b.w,b.y,b.d,b.h,xy); self.draw_art('back',self.back,b.glue,b.y,b.d,b.h,xy)
        for x,y in ((0,0),(b.cut_w,0),(0,b.cut_h),(b.cut_w,b.cut_h)):
            a,bb=xy(x+b.bleed,y+b.bleed); self.canvas.create_oval(a-3,bb-3,a+3,bb+3,outline='#c33')
        self.info.config(text=f'Inside: {b.w:.2f} W × {b.d:.2f} D × {b.h:.2f} H mm\nDieline: {b.cut_w:.2f} × {b.cut_h:.2f} mm\nShaped dust flaps + locking tuck nose\nPrint at 100%; test-fold first.')

    def draw_art(self,side,path,x,y,w,h,xy):
        if not path or Image is None:return
        try:
            im=ImageOps.exif_transpose(Image.open(path)).convert('RGB'); im.thumbnail((max(20,int(w*self.scale)),max(20,int(h*self.scale))),Image.Resampling.LANCZOS); photo=ImageTk.PhotoImage(im); self.photos.append(photo); ox,oy=self.art_offset[side]; a,bb=xy(x+b.bleed+w/2+ox*w,y+b.bleed+h/2+oy*h); self.canvas.create_image(a,bb,image=photo)
        except Exception as e: self.info.config(text=f'Artwork preview failed: {e}')

    def start_drag(self,e):
        b=self.box
        for side,path,x,y,w,h in [('front',self.front,b.glue+b.d+b.w,b.y,b.d,b.h),('back',self.back,b.glue,b.y,b.d,b.h)]:
            if path:
                ox,oy=self.art_offset[side]; cx=self.origin[0]+(x+b.bleed+w/2+ox*w)*self.scale; cy=self.origin[1]+(b.page_h-(y+b.bleed+h/2+oy*h))*self.scale
                if abs(e.x-cx)<w*self.scale/2 and abs(e.y-cy)<h*self.scale/2:self.drag=(side,e.x,e.y);return
    def move_drag(self,e):
        if not self.drag:return
        side,px,py=self.drag; self.art_offset[side][0]+=(e.x-px)/(self.scale*self.box.d); self.art_offset[side][1]-=(e.y-py)/(self.scale*self.box.h); self.drag=(side,e.x,e.y); self.redraw()

    def svg_image(self,path,x,y,w,h,side,H):
        if not path:return ''
        data=base64.b64encode(Path(path).read_bytes()).decode(); mime=mimetypes.guess_type(path)[0] or 'image/png'; ox,oy=self.art_offset[side]
        return f'<image href="data:{mime};base64,{data}" x="{x+ox*w}" y="{H-(y+oy*h+h)}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet"/>'
    def save_svg(self):
        p=filedialog.asksaveasfilename(defaultextension='.svg',filetypes=[('SVG files','*.svg')]);
        if not p:return
        try:
            b=self.box; W,H=b.page_w,b.page_h; o=b.bleed; out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
            def poly(points,fold=False): out.append(f'<polygon points="{" ".join(f"{x+o},{H-(y+o)}" for x,y in points)}" fill="none" stroke="{"#2865ad" if fold else "#111"}" stroke-width=".25"/>')
            for x,y,w,h,_ in b.panels():poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
            for points,_ in b.flaps():poly(points)
            for x,y,w,h,n in b.panels():
                if n in ('front','back'):out.append(self.svg_image(self.front if n=='front' else self.back,x+o,y+o,w,h,n,H))
            for x in (b.glue,b.glue+b.d,b.glue+b.d+b.w,b.glue+2*b.d+b.w):out.append(f'<path d="M{x+o} {H-o}V{H-b.page_h+o}" stroke="#2865ad" stroke-dasharray="2,1"/>')
            for y in (b.y,b.y+b.h):out.append(f'<path d="M{o} {H-y-o}H{W-o}" stroke="#2865ad" stroke-dasharray="2,1"/>')
            out.append('</svg>');Path(p).write_text('\n'.join(out),encoding='utf-8');messagebox.showinfo('Saved',p)
        except Exception as e:messagebox.showerror('SVG export failed',str(e))

    def save_pdf(self,pagesize):
        if Canvas is None:messagebox.showerror('Missing dependency','Install reportlab and try again.');return
        try: cols,rows,gap=int(self.cols.get()),int(self.rows.get()),float(self.gap.get()); assert cols>0 and rows>0 and gap>=0
        except (ValueError,AssertionError):messagebox.showerror('Invalid sheet','Columns/rows must be positive integers and gap non-negative.');return
        p=filedialog.asksaveasfilename(defaultextension='.pdf',filetypes=[('PDF files','*.pdf')]);
        if not p:return
        try:
            b=self.box; pw,ph=pagesize;margin=12*mm; sw=cols*b.page_w+(cols-1)*gap;sh=rows*b.page_h+(rows-1)*gap; scale=min((pw-2*margin)/(sw*mm),(ph-2*margin)/(sh*mm)); ox=margin+(pw-2*margin-sw*mm*scale)/2;oy=margin+(ph-2*margin-sh*mm*scale)/2; pdf=Canvas(p,pagesize=pagesize)
            def pt(x,y):return ox+(x+b.bleed)*mm*scale,oy+(y+b.bleed)*mm*scale
            def shape(points):pdf.setStrokeColorRGB(.08,.08,.08);pdf.setDash();pdf.line(0,0,0,0);pdf.beginPath()
            def draw_one(px,py):
                def P(x,y):return px+(x+b.bleed)*mm*scale,py+(y+b.bleed)*mm*scale
                def polygon(points):
                    q=pdf.beginPath();q.moveTo(*P(*points[0]));[q.lineTo(*P(*v)) for v in points[1:]];q.close();pdf.drawPath(q,stroke=1,fill=0)
                for x,y,w,h,_ in b.panels():polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])
                for points,_ in b.flaps():polygon(points)
                pdf.setStrokeColorRGB(.16,.4,.68);pdf.setDash(3,2)
                for x in (b.glue,b.glue+b.d,b.glue+b.d+b.w,b.glue+2*b.d+b.w):pdf.line(*P(x,0),*P(x,b.page_h))
                for y in (b.y,b.y+b.h):pdf.line(*P(0,y),*P(b.page_w,y))
                pdf.setDash()
            for r in range(rows):
                for col in range(cols):draw_one(ox+col*(b.page_w+gap)*mm*scale,oy+(rows-1-r)*(b.page_h+gap)*mm*scale)
            pdf.save();messagebox.showinfo('Saved',p)
        except Exception as e:messagebox.showerror('PDF export failed',str(e))

if __name__=='__main__':App().mainloop()
