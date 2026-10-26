using System;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using System.IO;

[assembly:AssemblyTitle("p2p_Remote_Desktop")]
[assembly:AssemblyProduct("CampusLink P2P")]
[assembly:AssemblyVersion("0.4.0.0")]
[assembly:AssemblyFileVersion("0.4.0.0")]
[assembly:System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8",FrameworkDisplayName=".NET Framework 4.8")]

namespace CampusLink.Client {
    static class P2PProgram {
        [DllImport("user32.dll")]static extern bool SetProcessDpiAwarenessContext(IntPtr context);
        [STAThread]static void Main(string[] args) {
            EmbeddedLibraries.Install();
            try{Run(args);}catch(Exception error){MessageBox.Show(error.Message,"CampusLink P2P");}
        }
        [MethodImpl(MethodImplOptions.NoInlining)]static void Run(string[] args) {
            try{SetProcessDpiAwarenessContext(new IntPtr(-4));}catch(EntryPointNotFoundException){}
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            if(args.Length==1&&args[0]=="--licenses"){EmbeddedLibraries.Notices();return;}
            if(args.Length==2&&args[0]=="--check-installation"){
                using(var form=new MainForm(new BrokerNetwork())){var handle=form.Handle;File.WriteAllText(args[1],Json.Encode(new{status="ok",version="0.4.0",nativeHandleCreated=handle!=IntPtr.Zero,bytes=new FileInfo(Assembly.GetExecutingAssembly().Location).Length,externalLibrariesRequired=false,bundledServer=false,inputSize=WindowsInput.Size}));}return;
            }
            using(var network=new BrokerNetwork())using(var form=new MainForm(network)) {
                var menu=new MenuStrip();var help=new ToolStripMenuItem("About / licenses");help.Click+=delegate{EmbeddedLibraries.Notices();};menu.Items.Add(help);form.Controls.Add(menu);
                form.Shown+=async delegate{string saved=network.SavedProfile;if(saved!=""){try{await network.Join(saved);}catch{}}};
                Application.Run(form);
            }
        }
    }
}
