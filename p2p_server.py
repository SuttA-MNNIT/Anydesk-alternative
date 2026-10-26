"""Single-window broker launcher; contains no screen capture or input controller."""
import base64,json,queue,re,secrets,threading,tkinter as tk,sys,time
from pathlib import Path
from tkinter import ttk,messagebox
from desktop.runtime import ManagedRuntime,settings_dir

def server_token():
    path=settings_dir()/'p2p-server.json'
    if path.exists():
        value=json.loads(path.read_text(encoding='utf-8')).get('token','')
        if not re.fullmatch(r'[a-f0-9]{64}',value):raise RuntimeError('Invalid server settings. Restore the saved server settings before continuing.')
        return value
    token=secrets.token_hex(32)
    path.write_text(json.dumps({'token':token}),encoding='utf-8')
    return token

class ServerApp:
    def __init__(self):
        self.root=tk.Tk();self.root.title('p2p_Remote_Desktop — Server');self.root.geometry('810x510');self.root.minsize(700,460)
        self.events=queue.Queue();self.runtime=None;self.code='';self.closed=False;self.restarting=False
        self.status=tk.StringVar(value='Starting the server and outside connection…')
        frame=ttk.Frame(self.root,padding=28);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='CampusLink P2P Server',font=('Segoe UI',22,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Keep this app running on the office PC. Clients can connect to each other.',font=('Segoe UI',11),wraplength=710).pack(anchor='w',pady=(10,18))
        ttk.Label(frame,textvariable=self.status,wraplength=710).pack(anchor='w',pady=(0,12))
        self.box=tk.Text(frame,height=6,wrap='char',font=('Consolas',10));self.box.pack(fill='x');self.box.configure(state='disabled')
        buttons=ttk.Frame(frame);buttons.pack(anchor='w',pady=16)
        self.copy=ttk.Button(buttons,text='Copy server code',command=self.copy_code,state='disabled');self.copy.pack(side='left',padx=(0,12))
        self.restart_button=ttk.Button(buttons,text='Restart server',command=self.restart,state='disabled');self.restart_button.pack(side='left',padx=(0,12))
        ttk.Button(buttons,text='Stop and exit',command=self.close).pack(side='left')
        ttk.Label(frame,text='On each client, paste this code once and choose Join server. Then share the computer code shown by that client. Every incoming screen session requires local approval.\n\nThe temporary outside address changes after a server restart. Clients will need the new server code until a permanent address is configured.',wraplength=710).pack(anchor='w')
        self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(80,self.poll);self.root.after(200,self.start)
    def start(self):
        if self.closed:return
        try:
            self.runtime=ManagedRuntime(self.events,settings_dir()/'p2p-devices.json',server_token())
            threading.Thread(target=self.runtime.start,daemon=True).start()
        except Exception as error:
            self.status.set(str(error));self.restarting=False;self.restart_button.configure(state='normal')
    def copy_code(self):
        if self.code:self.root.clipboard_clear();self.root.clipboard_append(self.code);self.status.set('Server code copied. Send it privately to your client users.')
    def restart(self):
        if self.restarting:return
        self.restarting=True;self.restart_button.configure(state='disabled')
        self.copy.configure(state='disabled');self.code='';self.status.set('Restarting…')
        previous=self.runtime;self.runtime=None
        def stop():
            if previous:previous.stop()
            self.events.put(('restart-ready',None))
        threading.Thread(target=stop,daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='restart-ready':self.start()
                elif kind=='runtime-ready' and data is self.runtime:
                    self.restarting=False;self.restart_button.configure(state='normal')
                    self.code='CL4.'+base64.urlsafe_b64encode(json.dumps({'u':data.url,'t':data.token},separators=(',',':')).encode()).decode().rstrip('=')
                    self.box.configure(state='normal');self.box.delete('1.0','end');self.box.insert('1.0',self.code);self.box.configure(state='disabled');self.copy.configure(state='normal');self.status.set('Online. Direct P2P first; encrypted relay fallback is available.')
                elif kind in ('runtime-status','runtime-error') and data[0] is self.runtime:
                    self.status.set(data[1])
                    if kind=='runtime-error':
                        self.copy.configure(state='disabled');self.restarting=False;self.restart_button.configure(state='normal')
        except queue.Empty:pass
        if not self.closed:self.root.after(80,self.poll)
    def close(self):
        self.closed=True
        if self.runtime:self.runtime.stop()
        self.root.destroy()
    def run(self):self.root.mainloop()

def check_installation(destination):
    events=queue.Queue();runtime=ManagedRuntime(events);error=None
    worker=threading.Thread(target=runtime.start,kwargs={'tunnel':False},daemon=True);worker.start()
    try:
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            try:kind,data=events.get(timeout=.2)
            except queue.Empty:continue
            if kind=='runtime-error':raise RuntimeError(data[1])
            if kind=='runtime-ready':break
        else:raise RuntimeError('Bundled server startup timed out.')
        children=list(runtime.children)
        runtime.stop();worker.join(timeout=5)
        Path(destination).write_text(json.dumps({'status':'ok','version':'0.4.0','bundledRuntimeStarted':True,'ownedHelpersStopped':all(child.poll() is not None for child in children),'screenCaptureIncluded':False}),encoding='utf-8')
    finally:runtime.stop()

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--check-installation':check_installation(sys.argv[2])
    else:ServerApp().run()
