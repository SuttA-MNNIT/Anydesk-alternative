using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace CampusLink.Client {
    public sealed class ScreenSurface : Control {
        public Image FrameImage;
        public Rectangle PictureBounds { get; private set; }
        public ScreenSurface() { DoubleBuffered=true; BackColor=Color.FromArgb(8,12,10); TabStop=true; SetStyle(ControlStyles.Selectable,true); }
        protected override void OnPaint(PaintEventArgs e) {
            base.OnPaint(e);
            if(FrameImage==null) return;
            double scale=Math.Min((double)Width/FrameImage.Width,(double)Height/FrameImage.Height);
            var size=new Size(Math.Max(1,(int)(FrameImage.Width*scale)),Math.Max(1,(int)(FrameImage.Height*scale)));
            PictureBounds=new Rectangle((Width-size.Width)/2,(Height-size.Height)/2,size.Width,size.Height);
            e.Graphics.InterpolationMode=InterpolationMode.NearestNeighbor; e.Graphics.DrawImage(FrameImage,PictureBounds);
        }
        protected override bool IsInputKey(Keys data) { return true; }
        public void SetFrame(Image image) { var old=FrameImage; FrameImage=image; if(old!=null) old.Dispose(); Invalidate(); }
        protected override void Dispose(bool disposing) { if(disposing && FrameImage!=null) {FrameImage.Dispose();FrameImage=null;} base.Dispose(disposing); }
    }
    public sealed class MainForm : Form {
        readonly Color background=Color.FromArgb(16,21,21),panel=Color.FromArgb(27,37,33),green=Color.FromArgb(196,242,119),muted=Color.FromArgb(145,167,154);
        readonly TextBox code=new TextBox { Multiline=true,ScrollBars=ScrollBars.Vertical,Height=95,Dock=DockStyle.Top,Font=new Font("Consolas",10) };
        readonly Label status=new Label { Dock=DockStyle.Bottom,Height=48,TextAlign=ContentAlignment.MiddleLeft };
        readonly Label stats=new Label { AutoSize=true,Padding=new Padding(10,10,6,0) };
        readonly Label remote=new Label { AutoSize=true,Padding=new Padding(4,10,10,0) };
        readonly Panel home=new Panel { Dock=DockStyle.Fill },desktop=new Panel { Dock=DockStyle.Fill,Visible=false };
        readonly ScreenSurface surface=new ScreenSurface { Dock=DockStyle.Fill };
        readonly ComboBox quality=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList,Width=210 };
        readonly CheckBox allow=new CheckBox { AutoSize=true,Text="Allow remote keyboard and mouse",Padding=new Padding(8,10,0,0) };
        Button connect,reverse,request;
        ClientSession session;
        bool refreshing,fullScreen;
        Rectangle savedBounds; FormBorderStyle savedBorder;
        int frames; long bytes; DateTime since=DateTime.UtcNow,lastMove=DateTime.MinValue;
        public MainForm() {
            Text="CampusLink Client — Connect"; Width=1050;Height=760;MinimumSize=new Size(780,640);BackColor=background;ForeColor=Color.FromArgb(237,244,237);Font=new Font("Segoe UI",10);
            status.Padding=new Padding(22,2,22,2);status.ForeColor=green;status.Text="Ready. Paste a connection code from the office server.";
            Controls.Add(home);Controls.Add(desktop);Controls.Add(status);
            var card=new Panel { Dock=DockStyle.Top,Height=375,Padding=new Padding(24),BackColor=panel };
            home.Padding=new Padding(32,25,32,10);
            var title=new Label { Text="CampusLink Client",Font=new Font("Segoe UI",25,FontStyle.Bold),Dock=DockStyle.Top,Height=55 };
            var intro=new Label { Text="Connect without carrying the server. Native Windows remote desktop.",ForeColor=muted,Dock=DockStyle.Top,Height=48 };
            var caption=new Label { Text="Connection code",Dock=DockStyle.Top,Height=32,Padding=new Padding(0,6,0,0) };
            var note=new Label { Text="The sharing computer runs CampusLink Server. Its owner must approve your session.",ForeColor=muted,Dock=DockStyle.Bottom,Height=58,Padding=new Padding(0,12,0,0) };
            var actions=new FlowLayoutPanel { Dock=DockStyle.Top,Height=62,Padding=new Padding(0,12,0,0) };
            connect=MakeButton("Connect",async delegate { await Connect(); });actions.Controls.Add(connect);
            actions.Controls.Add(MakeButton("Open invitation",delegate { OpenInvitation(); },true));
            actions.Controls.Add(MakeButton("Disconnect",delegate { Disconnect(); },true));
            card.Controls.Add(note);card.Controls.Add(actions);card.Controls.Add(code);card.Controls.Add(caption);
            home.Controls.Add(card);home.Controls.Add(intro);home.Controls.Add(title);
            var toolbar=new FlowLayoutPanel { Dock=DockStyle.Top,Height=78,Padding=new Padding(12,8,12,4),WrapContents=true };
            toolbar.Controls.Add(remote);
            reverse=MakeButton("Share my screen instead",Reverse,true);toolbar.Controls.Add(reverse);
            request=MakeButton("Request control",async delegate { if(session!=null) await session.Send(new {type="request-control"}); },true);toolbar.Controls.Add(request);
            toolbar.Controls.Add(MakeButton("Full screen",delegate { FullScreen(); },true));
            toolbar.Controls.Add(MakeButton("Disconnect",delegate { Disconnect(); },true));
            toolbar.Controls.Add(stats);
            var options=new FlowLayoutPanel { Dock=DockStyle.Bottom,Height=48,Padding=new Padding(12,8,12,0) };
            quality.Items.AddRange(new object[]{"Economy · 5 fps","Balanced · 10 fps","Sharper · 15 fps","Smooth · 30 fps target","Fast · 60 fps target"});quality.SelectedIndex=3;
            quality.SelectedIndexChanged+=async delegate { if(session!=null) {session.Profile=quality.Text;if(session.Mode=="viewing" && session.Native) await session.Send(new {type="quality",profile=quality.Text});} };
            options.Controls.Add(quality);options.Controls.Add(allow);
            allow.CheckedChanged+=async delegate { if(!refreshing && session!=null && session.Mode=="sharing") await session.SetControl(allow.Checked); };
            desktop.Controls.Add(surface);desktop.Controls.Add(toolbar);desktop.Controls.Add(options);
            surface.MouseDown+=async delegate(object sender,MouseEventArgs e) {surface.Focus();if(surface.PictureBounds.Contains(e.Location)) await Mouse(e,true);};
            surface.MouseUp+=async delegate(object sender,MouseEventArgs e) {await Mouse(e,false);};
            surface.MouseMove+=async delegate(object sender,MouseEventArgs e) {if((DateTime.UtcNow-lastMove).TotalMilliseconds>=16 && surface.PictureBounds.Contains(e.Location)) {lastMove=DateTime.UtcNow;await Pointer(e);} };
            surface.MouseWheel+=async delegate(object sender,MouseEventArgs e) {if(session!=null) await session.Input(new {type="wheel",delta=Math.Max(-1200,Math.Min(1200,e.Delta))});};
            surface.KeyDown+=async delegate(object sender,KeyEventArgs e) {e.SuppressKeyPress=true;if(e.KeyCode==Keys.F11) {FullScreen();return;} if(e.KeyCode==Keys.Escape && fullScreen) {FullScreen();return;} string key=WindowsInput.CodeFor(e.KeyCode);if(session!=null && key!=null) await session.Input(new {type="key",code=key,down=true});};
            surface.KeyUp+=async delegate(object sender,KeyEventArgs e) {e.SuppressKeyPress=true;string key=WindowsInput.CodeFor(e.KeyCode);if(session!=null && key!=null && e.KeyCode!=Keys.F11) await session.Input(new {type="key",code=key,down=false});};
            surface.LostFocus+=async delegate {if(session!=null) await session.Input(new {type="release"});};
            FormClosing+=delegate {Disconnect();};
        }
        Button MakeButton(string text,Action action,bool secondary=false) {
            var button=new Button { Text=text,AutoSize=true,Height=38,FlatStyle=FlatStyle.Flat,BackColor=secondary?panel:green,ForeColor=secondary?ForeColor:background,Padding=new Padding(9,3,9,3),Margin=new Padding(0,0,8,0) };
            button.FlatAppearance.BorderSize=0;button.Click+=delegate {action();};return button;
        }
        void Ui(Action action) {if(IsDisposed || !IsHandleCreated) return;if(InvokeRequired) BeginInvoke(action);else action();}
        public Task ShowFrame(byte[] jpeg,string streamId) {
            var completion=new TaskCompletionSource<bool>();
            if(IsDisposed || !IsHandleCreated) {completion.SetResult(false);return completion.Task;}
            BeginInvoke(new Action(delegate {
                try {
                    if(session==null || session.Mode!="viewing" || session.StreamId!=streamId) {completion.SetResult(false);return;}
                    using(var input=new MemoryStream(jpeg)) using(var image=Image.FromStream(input,true,true)) {
                        if((long)image.Width*image.Height>16777216) throw new InvalidDataException("Screen size is too large.");
                        surface.SetFrame(new Bitmap(image));
                    }
                    frames++;bytes+=jpeg.Length;double elapsed=(DateTime.UtcNow-since).TotalSeconds;
                    if(elapsed>=1) {stats.Text=string.Format("{0} × {1} · {2:0} fps · {3:0.0} Mbps",surface.FrameImage.Width,surface.FrameImage.Height,frames/elapsed,bytes*8/elapsed/1000000);frames=0;bytes=0;since=DateTime.UtcNow;}
                    completion.SetResult(true);
                } catch(Exception error) {completion.SetException(error);}
            }));
            return completion.Task;
        }
        async Task Connect() {
            if(session!=null) {status.Text="Disconnect the current session first.";return;}
            Invitation invitation;
            try {invitation=Invitation.Parse(code.Text);}catch(Exception error){status.Text=error.Message;return;}
            var peer=new ClientSession();session=peer;peer.Profile=quality.Text;code.Clear();connect.Enabled=false;status.Text="Connecting… Waiting for approval on the sharing computer.";
            peer.Frame=ShowFrame;
            peer.Changed=message=>Ui(delegate {if(session!=peer)return;status.Text=message;RefreshMode();});
            peer.Ended=message=>Ui(delegate {if(session!=peer)return;Disconnect();status.Text=message;});
            peer.ReverseOffer=control=>Ask("The other person offers to share their screen again. Stop sharing your screen and accept?","Switch direction");
            peer.ControlRequest=()=>Ask("Allow the connected person to use your keyboard and mouse for this session?","Allow control");
            await peer.Connect(invitation);
        }
        Task<bool> Ask(string message,string title) {
            var answer=new TaskCompletionSource<bool>();
            if(IsDisposed || !IsHandleCreated) {answer.SetResult(false);return answer.Task;}
            BeginInvoke(new Action(delegate {answer.TrySetResult(session!=null && MessageBox.Show(this,message,"CampusLink — "+title,MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)==DialogResult.Yes);}));
            return answer.Task;
        }
        async void Reverse() {
            var peer=session;if(peer==null || peer.Mode!="viewing" || !peer.Native)return;
            var choice=MessageBox.Show(this,"Share your primary screen instead?\n\nYes: allow keyboard and mouse control.\nNo: view only.\nCancel: keep viewing.","CampusLink — Share your screen",MessageBoxButtons.YesNoCancel,MessageBoxIcon.Question,MessageBoxDefaultButton.Button3);
            if(choice!=DialogResult.Cancel) await peer.Reverse(choice==DialogResult.Yes);
        }
        void RefreshMode() {
            if(session==null)return;
            home.Visible=false;desktop.Visible=true;
            surface.Visible=session.Mode=="viewing";
            remote.Text=session.Mode=="sharing"?"Sharing your screen":session.RemoteName+(session.Control?" · Control":" · View only");
            reverse.Enabled=session.Native && session.Mode=="viewing";request.Enabled=session.Native && session.Mode=="viewing" && !session.Control;
            refreshing=true;allow.Enabled=session.Mode=="sharing";allow.Checked=session.Mode=="sharing" && session.Control;refreshing=false;
            if(session.Mode=="viewing")surface.Focus();
        }
        async Task Pointer(MouseEventArgs e) {if(session==null)return;var r=surface.PictureBounds;if(r.Width<1||r.Height<1)return;await session.Input(new {type="move",x=Math.Max(0,Math.Min(1,(double)(e.X-r.X)/r.Width)),y=Math.Max(0,Math.Min(1,(double)(e.Y-r.Y)/r.Height))});}
        async Task Mouse(MouseEventArgs e,bool down) {if(session==null)return;int button=e.Button==MouseButtons.Left?0:e.Button==MouseButtons.Middle?1:2;var r=surface.PictureBounds;if(r.Width<1||r.Height<1)return;await session.Input(new {type="button",button=button,down=down,x=Math.Max(0,Math.Min(1,(double)(e.X-r.X)/r.Width)),y=Math.Max(0,Math.Min(1,(double)(e.Y-r.Y)/r.Height))});}
        async void OpenInvitation() {using(var dialog=new OpenFileDialog {Filter="CampusLink invitation|*.campuslink|Text file|*.txt"}) if(dialog.ShowDialog(this)==DialogResult.OK) {try {if(new FileInfo(dialog.FileName).Length>4096)throw new InvalidDataException("Invitation file is too large.");code.Text=File.ReadAllText(dialog.FileName);await Connect();}catch(Exception error){status.Text=error.Message;}}}
        void FullScreen() {if(!fullScreen){savedBounds=Bounds;savedBorder=FormBorderStyle;FormBorderStyle=FormBorderStyle.None;WindowState=FormWindowState.Normal;Bounds=Screen.FromControl(this).Bounds;}else{FormBorderStyle=savedBorder;Bounds=savedBounds;}fullScreen=!fullScreen;}
        public void Disconnect() {var peer=session;session=null;if(peer!=null)peer.Dispose();home.Visible=true;desktop.Visible=false;connect.Enabled=true;surface.SetFrame(null);status.Text="Disconnected. No server or tunnel runs in this client.";if(fullScreen)FullScreen();}
    }
}
