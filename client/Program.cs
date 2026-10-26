using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace CampusLink.Client {
    static class Program {
        [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
        [STAThread] static void Main(string[] args) {
            try {SetProcessDpiAwarenessContext(new IntPtr(-4));}catch(EntryPointNotFoundException){}
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            if(args.Length==2 && args[0]=="--check-installation") {
                using(var form=new MainForm()) {var handle=form.Handle;File.WriteAllText(args[1],Json.Encode(new {status="ok",nativeViewer=true,bundledServer=false,bundledPython=false,bundledNode=false,inputSize=WindowsInput.Size,framework=Environment.Version.ToString(),nativeHandleCreated=handle!=IntPtr.Zero}));}
                return;
            }
            using(var key=Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full")) {
                if(key==null || Convert.ToInt32(key.GetValue("Release",0))<528040) {MessageBox.Show("CampusLink Client requires .NET Framework 4.8 or later. It is included with Windows 11; older Windows PCs may need a Microsoft .NET Framework update.","CampusLink Client");return;}
            }
            Application.Run(new MainForm());
        }
    }
}
