import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox

# APC40 MK2 COLOR-ONLY LED MAPPER
# No MIDI IN is used. LEDs are refreshed continuously so pressing a hardware
# button cannot leave its LED off. This deliberately keeps the program simple.

winmm = ctypes.WinDLL('winmm')
UINT=wintypes.UINT; DWORD=wintypes.DWORD
HMIDIOUT=wintypes.HANDLE

class OUTCAP(ctypes.Structure):
    _fields_=[('wMid',wintypes.WORD),('wPid',wintypes.WORD),('vDriverVersion',DWORD),
              ('szPname',wintypes.WCHAR*32),('wTechnology',wintypes.WORD),
              ('wVoices',wintypes.WORD),('wNotes',wintypes.WORD),
              ('wChannelMask',wintypes.WORD),('dwSupport',DWORD)]

winmm.midiOutGetNumDevs.restype=UINT
winmm.midiOutGetDevCapsW.argtypes=[UINT,ctypes.POINTER(OUTCAP),UINT]
winmm.midiOutOpen.argtypes=[ctypes.POINTER(HMIDIOUT),UINT,ctypes.c_size_t,ctypes.c_size_t,DWORD]
winmm.midiOutOpen.restype=UINT
winmm.midiOutShortMsg.argtypes=[HMIDIOUT,DWORD]
winmm.midiOutShortMsg.restype=UINT
winmm.midiOutReset.argtypes=[HMIDIOUT]
winmm.midiOutClose.argtypes=[HMIDIOUT]

# Main RGB controls: 40 Clip Launch pads + 5 Scene Launch buttons.
# APC40 MK2 protocol uses MIDI channel 1 (zero-based channel 0) for these LEDs.
CONTROLS=[]
for i in range(40):
    CONTROLS.append((f'Clip {i+1}', i))
for i in range(5):
    CONTROLS.append((f'Scene {i+1}', 0x52+i))

# APC40 MK2 color palette (protocol velocity values 0..127).
# Indexed palette values are kept from the official controller palette family.
PALETTE = [
'#000000','#1E1E1E','#7F7F7F','#FFFFFF','#FF4C4C','#FF0000','#590000','#190000',
'#FFBD6C','#FF5400','#591D00','#271B00','#FFFF4C','#FFFF00','#595900','#191900',
'#88FF4C','#54FF00','#1D5900','#142B00','#4CFF4C','#00FF00','#005900','#001900',
'#4CFF5E','#00FF19','#00590D','#001902','#4CFF88','#00FF55','#00591D','#001F12',
'#4CFFB7','#00FF99','#005935','#001912','#4CC3FF','#00A9FF','#004152','#001019',
'#4C88FF','#0055FF','#001D59','#000819','#4C4CFF','#0000FF','#000059','#000019',
'#874CFF','#5400FF','#190064','#0F0030','#FF4CFF','#FF00FF','#590059','#190019',
'#FF4C87','#FF0054','#59001D','#220013','#FF1500','#993500','#795100','#436400',
'#033900','#005735','#00547F','#0000FF','#00454F','#2500CC','#7F7F7F','#202020',
'#FF0000','#BDFF2D','#AFED06','#64FF09','#108B00','#00FF87','#00A9FF','#002AFF',
'#3F00FF','#7A00FF','#B21A7D','#402100','#FF4A00','#88E106','#72FF15','#00FF00',
'#3BFF26','#59FF71','#38FFCC','#5B8AFF','#3151C6','#877FE9','#D31DFF','#FF005D',
'#FF7F00','#B9B000','#90FF00','#835D07','#392B00','#144C10','#0D5038','#15152A',
'#16205A','#693C1C','#A8000A','#DE513D','#D86A1C','#FFE126','#9EE12F','#67B50F',
'#1E1E30','#DCFF6B','#80FFBD','#9A99FF','#8E66FF','#404040','#757575','#E0FFFF',
'#A00000','#350000','#1AD000','#074200','#B9B000','#3F3100','#B35F00','#4B1502'
]

def rgb(h):
    h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))

def nearest_palette(h):
    r,g,b=rgb(h)
    best=(10**12,0)
    for i,c in enumerate(PALETTE):
        cr,cg,cb=rgb(c); d=(r-cr)**2+(g-cg)**2+(b-cb)**2
        if d<best[0]: best=(d,i)
    return best[1]

class MidiOut:
    def __init__(self): self.h=None; self.devices=[]; self.refresh()
    def refresh(self):
        self.devices=[]
        for i in range(int(winmm.midiOutGetNumDevs())):
            c=OUTCAP()
            if winmm.midiOutGetDevCapsW(i,ctypes.byref(c),ctypes.sizeof(c))==0:
                self.devices.append((i,c.szPname))
    def open(self,index):
        self.close(); h=HMIDIOUT(); r=winmm.midiOutOpen(ctypes.byref(h),int(index),0,0,0)
        if r: raise RuntimeError(f'midiOutOpen error {r}')
        self.h=h
    def send(self,note,velocity):
        if self.h:
            # Note On, channel 1 (MIDI channel number 1; zero-based channel 0)
            msg=0x90 | ((int(note)&127)<<8) | ((int(velocity)&127)<<16)
            winmm.midiOutShortMsg(self.h,msg)
    def close(self):
        if self.h:
            try: winmm.midiOutReset(self.h)
            except Exception: pass
            try: winmm.midiOutClose(self.h)
            except Exception: pass
            self.h=None

class App:
    BG='#121212'; PANEL='#1B1B1B'; PANEL2='#202020'; FG='#F2F2F2'; MUTED='#A8A8A8'; ACCENT='#5B9BFF'
    def __init__(self,root):
        self.root=root; root.title('APC40 MK2 • LED Color Mapper'); root.geometry('1120x760'); root.minsize(900,620); root.configure(bg=self.BG)
        self.m=MidiOut(); self.colors=['#00FF00']*len(CONTROLS); self.connected=False; self.running=True
        self.buttons=[]; self.swatches=[]
        self.setup_style(); self.build(); self.refresh_devices(); self.loop(); root.protocol('WM_DELETE_WINDOW',self.close)
    def setup_style(self):
        s=ttk.Style(); s.theme_use('clam');
        s.configure('.',background=self.BG,foreground=self.FG); s.configure('TFrame',background=self.BG); s.configure('Panel.TFrame',background=self.PANEL)
        s.configure('TLabel',background=self.BG,foreground=self.FG); s.configure('Muted.TLabel',background=self.BG,foreground=self.MUTED)
        s.configure('TButton',background='#2A2A2A',foreground=self.FG,borderwidth=0,padding=(10,7)); s.map('TButton',background=[('active','#3A3A3A')])
        s.configure('TCombobox',fieldbackground='#252525',background='#252525',foreground=self.FG,arrowcolor=self.FG)
    def build(self):
        head=tk.Frame(self.root,bg=self.BG); head.pack(fill='x',padx=18,pady=(16,8))
        tk.Label(head,text='APC40 MK2',bg=self.BG,fg=self.FG,font=('Segoe UI',20,'bold')).pack(side='left')
        tk.Label(head,text='  LED COLOR MAPPER',bg=self.BG,fg=self.MUTED,font=('Segoe UI',11)).pack(side='left',pady=(7,0))
        top=tk.Frame(self.root,bg=self.PANEL); top.pack(fill='x',padx=18,pady=8)
        tk.Label(top,text='MIDI OUT',bg=self.PANEL,fg=self.FG,font=('Segoe UI',10,'bold')).pack(side='left',padx=(14,6),pady=12)
        self.combo=ttk.Combobox(top,state='readonly',width=42); self.combo.pack(side='left',pady=10)
        tk.Button(top,text='REFRESH',command=self.refresh_devices,bg='#2A2A2A',fg=self.FG,activebackground='#3A3A3A',activeforeground=self.FG,bd=0,padx=12,pady=7).pack(side='left',padx=7)
        tk.Button(top,text='CONNECT',command=self.connect,bg=self.ACCENT,fg='white',activebackground='#4A89EA',activeforeground='white',bd=0,padx=14,pady=7).pack(side='left',padx=2)
        self.status=tk.Label(top,text='● Disconnected',bg=self.PANEL,fg='#FF6B6B',font=('Segoe UI',10)); self.status.pack(side='right',padx=14)
        hint=tk.Frame(self.root,bg=self.BG); hint.pack(fill='x',padx=18,pady=(4,8))
        tk.Label(hint,text='Selecciona un botón y asigna su color. El programa mantiene el LED encendido continuamente.',bg=self.BG,fg=self.MUTED,font=('Segoe UI',9)).pack(side='left')
        tk.Button(hint,text='ALL GREEN',command=lambda:self.set_all('#00FF00'),bg='#242424',fg=self.FG,bd=0,padx=10,pady=5).pack(side='right',padx=4)
        tk.Button(hint,text='ALL OFF',command=lambda:self.set_all('#000000'),bg='#242424',fg=self.FG,bd=0,padx=10,pady=5).pack(side='right',padx=4)
        outer=tk.Frame(self.root,bg=self.BG); outer.pack(fill='both',expand=True,padx=18,pady=(0,18))
        canvas=tk.Canvas(outer,bg=self.BG,highlightthickness=0); scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview); canvas.configure(yscrollcommand=scroll.set); canvas.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
        grid=tk.Frame(canvas,bg=self.BG); win=canvas.create_window((0,0),window=grid,anchor='nw')
        grid.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all'))); canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        for i,(name,note) in enumerate(CONTROLS):
            card=tk.Frame(grid,bg=self.PANEL,highlightthickness=1,highlightbackground='#2B2B2B'); card.grid(row=i//5,column=i%5,sticky='nsew',padx=5,pady=5)
            tk.Label(card,text=name,bg=self.PANEL,fg=self.FG,font=('Segoe UI',10,'bold')).pack(padx=12,pady=(12,3))
            tk.Label(card,text=f'MIDI note {note}',bg=self.PANEL,fg=self.MUTED,font=('Segoe UI',8)).pack()
            b=tk.Button(card,text='COLOR',command=lambda x=i:self.pick(x),bg=self.colors[i],fg=self.text_color(self.colors[i]),activebackground=self.colors[i],activeforeground=self.text_color(self.colors[i]),bd=0,font=('Segoe UI',9,'bold'),width=13,height=2)
            b.pack(padx=12,pady=(8,6)); self.buttons.append(b)
            sw=tk.Label(card,text=self.colors[i],bg=self.colors[i],fg=self.text_color(self.colors[i]),font=('Consolas',8),width=13,padx=2,pady=2); sw.pack(padx=12,pady=(0,12)); self.swatches.append(sw)
        for c in range(5): grid.columnconfigure(c,weight=1)
    def text_color(self,h):
        r,g,b=rgb(h); return '#000000' if (r*299+g*587+b*114)>150000 else '#FFFFFF'
    def refresh_devices(self):
        self.m.refresh(); vals=[f'{i}: {n}' for i,n in self.m.devices]; self.combo['values']=vals
        if vals: self.combo.current(0)
        self.status.config(text='● Disconnected',fg='#FF6B6B')
    def connect(self):
        if not self.m.devices: messagebox.showerror('APC40 MK2','No se ha encontrado ningún dispositivo MIDI OUT.'); return
        idx=self.combo.current()
        if idx<0: idx=0
        try:
            self.m.open(self.m.devices[idx][0]); self.connected=True; self.status.config(text='● Connected',fg='#52E38B')
            self.push_all()
        except Exception as e:
            self.connected=False; messagebox.showerror('MIDI OUT',str(e))
    def pick(self,i):
        color=colorchooser.askcolor(color=self.colors[i],title=f'Color — {CONTROLS[i][0]}')[1]
        if color:
            self.colors[i]=color.upper(); self.update_button(i); self.send(i)
    def update_button(self,i):
        c=self.colors[i]; self.buttons[i].configure(bg=c,activebackground=c,fg=self.text_color(c),activeforeground=self.text_color(c)); self.swatches[i].configure(text=c,bg=c,fg=self.text_color(c))
    def set_all(self,c):
        self.colors=[c]*len(CONTROLS)
        for i in range(len(CONTROLS)): self.update_button(i)
        self.push_all()
    def send(self,i):
        if self.connected:
            # Palette velocity selects a fixed RGB color; no blink mode is sent.
            self.m.send(CONTROLS[i][1],nearest_palette(self.colors[i]))
    def push_all(self):
        for i in range(len(CONTROLS)): self.send(i)
    def loop(self):
        if self.running and self.connected: self.push_all()
        self.root.after(120,self.loop)
    def close(self):
        self.running=False; self.m.close(); self.root.destroy()

if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
