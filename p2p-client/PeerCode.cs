using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace CampusLink.Client {
    public sealed class PeerCode {
        public string Url,Token,DeviceId,Key;
        public static string Random(int bytes) {var data=new byte[bytes];using(var rng=RandomNumberGenerator.Create())rng.GetBytes(data);return BitConverter.ToString(data).Replace("-","").ToLowerInvariant();}
        public static PeerCode Parse(string text) {
            text=Regex.Replace(text??"",@"\s","");
            if(text.Length>3000 || !Regex.IsMatch(text,@"^CL4\.[A-Za-z0-9_-]+$"))throw new ArgumentException("Paste a CL4 server or computer connection code.");
            string raw=text.Substring(4).Replace('-','+').Replace('_','/');raw=raw.PadRight((raw.Length+3)/4*4,'=');
            Dictionary<string,object> value;
            try{value=Json.Decode(Encoding.UTF8.GetString(Convert.FromBase64String(raw)));}catch{throw new ArgumentException("Invalid connection code.");}
            if(value==null)throw new ArgumentException("Invalid connection code.");
            var result=new PeerCode{Url=Json.Text(value,"u"),Token=Json.Text(value,"t"),DeviceId=Json.Text(value,"d"),Key=Json.Text(value,"k")};
            Uri uri;
            if(!Uri.TryCreate(result.Url,UriKind.Absolute,out uri)||result.Url.Length>512||uri.UserInfo!=""||uri.Query!=""||uri.Fragment!=""||uri.AbsolutePath!="/"||(uri.Scheme!="https" && !(uri.Scheme=="http" && (uri.Host=="127.0.0.1"||uri.Host=="localhost"||uri.Host=="[::1]"))))throw new ArgumentException("Invalid server address.");
            if(!Regex.IsMatch(result.Token,@"^[a-f0-9]{64}$") || ((result.DeviceId!=""||result.Key!="")&&(!Regex.IsMatch(result.DeviceId,@"^\d{10}$")||!Regex.IsMatch(result.Key,@"^[a-f0-9]{32}$"))))throw new ArgumentException("Invalid server or computer credentials.");
            return result;
        }
        public string Encode() {var value=new Dictionary<string,object>{{"u",Url},{"t",Token}};if(DeviceId!=null&&DeviceId!=""){value["d"]=DeviceId;value["k"]=Key;}return "CL4."+Convert.ToBase64String(Encoding.UTF8.GetBytes(Json.Encode(value))).TrimEnd('=').Replace('+','-').Replace('/','_');}
        public Uri WebSocketUri {get{var uri=new UriBuilder(Url);uri.Scheme=uri.Scheme=="https"?"wss":"ws";uri.Path="/peer";return uri.Uri;}}
    }
    static class PeerSettings {
        static string Folder {get{var path=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CampusLink","P2P");Directory.CreateDirectory(path);return path;}}
        public static string Load(string name) {try{return Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(Path.Combine(Folder,name)),null,DataProtectionScope.CurrentUser));}catch{return "";}}
        public static void Save(string name,string value) {File.WriteAllBytes(Path.Combine(Folder,name),ProtectedData.Protect(Encoding.UTF8.GetBytes(value),null,DataProtectionScope.CurrentUser));}
        public static string Identity(string server) {string name;using(var sha=SHA256.Create())name=BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(server))).Replace("-","")+".identity";string value=Load(name);if(!Regex.IsMatch(value,@"^[a-f0-9]{64}$")){value=PeerCode.Random(32);Save(name,value);}return value;}
    }
}
