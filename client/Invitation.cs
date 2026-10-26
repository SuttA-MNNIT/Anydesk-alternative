using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace CampusLink.Client {
    static class Json {
        static readonly JavaScriptSerializer serializer = new JavaScriptSerializer { MaxJsonLength=16384 };
        public static string Encode(object value) { lock(serializer) return serializer.Serialize(value); }
        public static Dictionary<string,object> Decode(string text) { lock(serializer) return serializer.Deserialize<Dictionary<string,object>>(text); }
        public static string Text(Dictionary<string,object> value, string key, string fallback="") { object item; return value.TryGetValue(key,out item) && item is string ? (string)item : fallback; }
        public static bool Flag(Dictionary<string,object> value, string key) { object item; return value.TryGetValue(key,out item) && item is bool && (bool)item; }
        public static bool Feature(Dictionary<string,object> value, string name) { object items; if (!value.TryGetValue("features",out items)) return false; var list=items as System.Collections.IEnumerable; if(list==null || items is string)return false; foreach(object item in list)if(item is string && (string)item==name)return true;return false; }
    }
    public sealed class Invitation {
        public string Url, DeviceId, Key;
        public static Invitation Parse(string code) {
            code=Regex.Replace(code??"",@"\s","");
            if (code.Length>2048 || !Regex.IsMatch(code,@"^CL3\.[A-Za-z0-9_-]+$")) throw new ArgumentException("Paste a CampusLink connection code beginning with CL3.");
            string raw=code.Substring(4).Replace('-','+').Replace('_','/'); raw=raw.PadRight((raw.Length+3)/4*4,'=');
            Dictionary<string,object> data;
            try { data=Json.Decode(Encoding.UTF8.GetString(Convert.FromBase64String(raw))); }
            catch { throw new ArgumentException("The connection code is incomplete or invalid."); }
            object version;
            if (data==null || data.Count!=4 || !data.TryGetValue("v",out version) || !(version is int) || (int)version!=3) throw new ArgumentException("Unsupported connection code.");
            var result=new Invitation { Url=Json.Text(data,"u"), DeviceId=Json.Text(data,"d"), Key=Json.Text(data,"k") };
            Uri uri;
            if (result.Url.Length>512 || !Uri.TryCreate(result.Url,UriKind.Absolute,out uri) || (uri.Scheme!="https" && uri.Scheme!="http") || uri.UserInfo!="" || uri.Query!="" || uri.Fragment!="" || uri.AbsolutePath!="/"
                || (uri.Scheme=="http" && uri.Host!="localhost" && uri.Host!="127.0.0.1" && uri.Host!="[::1]")) throw new ArgumentException("The invitation contains an unsafe connection address.");
            if (!Regex.IsMatch(result.DeviceId,@"^\d{10}$") || !Regex.IsMatch(result.Key,@"^[a-f0-9]{32}$")) throw new ArgumentException("Invalid device ID or access key.");
            return result;
        }
        public Uri WebSocketUri { get { var uri=new UriBuilder(Url); uri.Scheme=uri.Scheme=="https"?"wss":"ws"; uri.Path="/ws"; return uri.Uri; } }
    }
}
