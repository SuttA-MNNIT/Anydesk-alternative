using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Linq;
using System.Collections.Generic;

namespace CampusLink.Client {
    static class EmbeddedLibraries {
        static readonly Dictionary<string,Assembly> loaded=new Dictionary<string,Assembly>(StringComparer.OrdinalIgnoreCase);
        public static void Install() { AppDomain.CurrentDomain.AssemblyResolve+=Resolve; }
        static Assembly Resolve(object sender,ResolveEventArgs args) {
            string name=new AssemblyName(args.Name).Name;
            if(name.EndsWith(".resources",StringComparison.OrdinalIgnoreCase))return null;
            lock(loaded) {
            Assembly existing;if(loaded.TryGetValue(name,out existing))return existing;
            existing=AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a=>a.GetName().Name==name);
            if(existing!=null){loaded[name]=existing;return existing;}
            string replacement=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"libraries",name+".dll");
            if(File.Exists(replacement)){loaded[name]=Assembly.LoadFrom(replacement);return loaded[name];}
            using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("libraries."+name+".dll.gz")) {
                if(stream==null)return null;
                using(var gzip=new GZipStream(stream,CompressionMode.Decompress))using(var memory=new MemoryStream()){gzip.CopyTo(memory);loaded[name]=Assembly.Load(memory.ToArray());return loaded[name];}
            }
            }
        }
        public static void Notices() {
            string path=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CampusLink","P2P-LICENSES.txt");
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            using(var input=Assembly.GetExecutingAssembly().GetManifestResourceStream("THIRD-PARTY-NOTICES.txt"))using(var output=File.Create(path)){input.CopyTo(output);}
            System.Diagnostics.Process.Start(path);
        }
    }
}
