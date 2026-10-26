using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace CampusLink.Client {
    public interface IInput { void Apply(Dictionary<string,object> message); void Release(); }
    public sealed class WindowsInput : IInput {
        [StructLayout(LayoutKind.Sequential)] struct MouseInput { public int x,y; public uint data,flags,time; public UIntPtr extra; }
        [StructLayout(LayoutKind.Sequential)] struct KeyInput { public ushort key,scan; public uint flags,time; public UIntPtr extra; }
        [StructLayout(LayoutKind.Explicit)] struct Union { [FieldOffset(0)] public MouseInput mouse; [FieldOffset(0)] public KeyInput keyboard; }
        [StructLayout(LayoutKind.Sequential)] struct Input { public uint type; public Union value; }
        [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint count, Input[] input, int size);
        [DllImport("user32.dll")] static extern bool SetCursorPos(int x,int y);
        readonly HashSet<string> keys=new HashSet<string>(); readonly HashSet<int> buttons=new HashSet<int>(); readonly object gate=new object();
        static readonly Dictionary<string,int> named=new Dictionary<string,int> {
            {"Backspace",8},{"Tab",9},{"Enter",13},{"Escape",27},{"Space",32},{"PageUp",33},{"PageDown",34},{"End",35},{"Home",36},
            {"ArrowLeft",37},{"ArrowUp",38},{"ArrowRight",39},{"ArrowDown",40},{"Insert",45},{"Delete",46},
            {"ShiftLeft",160},{"ShiftRight",161},{"ControlLeft",162},{"ControlRight",163},{"AltLeft",164},{"AltRight",165},{"MetaLeft",91},{"MetaRight",92},
            {"CapsLock",20},{"NumLock",144},{"ScrollLock",145},{"Semicolon",186},{"Equal",187},{"Comma",188},{"Minus",189},{"Period",190},
            {"Slash",191},{"Backquote",192},{"BracketLeft",219},{"Backslash",220},{"BracketRight",221},{"Quote",222},
            {"NumpadMultiply",106},{"NumpadAdd",107},{"NumpadSubtract",109},{"NumpadDecimal",110},{"NumpadDivide",111},{"NumpadEnter",13}
        };
        static readonly HashSet<string> extended=new HashSet<string>(new[]{"ControlRight","AltRight","MetaLeft","MetaRight","ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End","PageUp","PageDown","Insert","Delete","NumpadDivide","NumpadEnter","NumLock"});
        public static int Size { get { return Marshal.SizeOf(typeof(Input)); } }
        public static int VirtualKey(string code) {
            int value;
            if (named.TryGetValue(code,out value)) return value;
            if (code.Length==4 && code.StartsWith("Key") && code[3]>='A' && code[3]<='Z') return code[3];
            if (code.Length==6 && code.StartsWith("Digit") && char.IsDigit(code[5])) return code[5];
            if (code.StartsWith("F") && int.TryParse(code.Substring(1),out value) && value>=1 && value<=12) return 111+value;
            if (code.Length==7 && code.StartsWith("Numpad") && char.IsDigit(code[6])) return 96+code[6]-'0';
            return 0;
        }
        public static string CodeFor(Keys key) {
            int value=(int)key;
            if (value>=65 && value<=90) return "Key"+(char)value;
            if (value>=48 && value<=57) return "Digit"+(char)value;
            if (value>=112 && value<=123) return "F"+(value-111);
            if (value>=96 && value<=105) return "Numpad"+(value-96);
            if (value==16) return "ShiftLeft"; if (value==17) return "ControlLeft"; if (value==18) return "AltLeft";
            foreach (var entry in named) if (entry.Value==value) return entry.Key;
            return null;
        }
        static void Send(Input input) { if (SendInput(1,new[]{input},Size)!=1) throw new InvalidOperationException("Windows blocked remote input into this window."); }
        void Key(string code,bool down) {
            int vk=VirtualKey(code); if (vk==0) return;
            Send(new Input { type=1,value=new Union { keyboard=new KeyInput { key=(ushort)vk, flags=(uint)((down?0:2)|(extended.Contains(code)?1:0)) } } });
            if (down) keys.Add(code); else keys.Remove(code);
        }
        void Button(int button,bool down) {
            uint[] press={2,32,8}, release={4,64,16}; if (button<0 || button>2) throw new ArgumentException("Invalid mouse button.");
            Send(new Input { type=0,value=new Union { mouse=new MouseInput { flags=down?press[button]:release[button] } } });
            if (down) buttons.Add(button); else buttons.Remove(button);
        }
        static double Number(Dictionary<string,object> m,string field) {
            object item; if (!m.TryGetValue(field,out item) || !(item is double || item is int || item is decimal || item is long)) throw new ArgumentException("Invalid pointer event.");
            double value=Convert.ToDouble(item); if (double.IsNaN(value)||double.IsInfinity(value)||value<0||value>1) throw new ArgumentException("Invalid pointer event."); return value;
        }
        static void Move(Dictionary<string,object> m) { var size=Screen.PrimaryScreen.Bounds; if (!SetCursorPos((int)Math.Round(Number(m,"x")*(size.Width-1)),(int)Math.Round(Number(m,"y")*(size.Height-1)))) throw new InvalidOperationException("Windows blocked pointer input."); }
        public void Apply(Dictionary<string,object> m) {
            lock(gate) {
                string type=Json.Text(m,"type");
                if (type=="move") Move(m);
                else if (type=="button") { if (!(m["down"] is bool) || !(m["button"] is int)) throw new ArgumentException("Invalid mouse event."); Move(m); Button((int)m["button"],(bool)m["down"]); }
                else if (type=="key") { if (!(m["down"] is bool)) throw new ArgumentException("Invalid key event."); Key(Json.Text(m,"code"),(bool)m["down"]); }
                else if (type=="wheel") { if (!(m["delta"] is int) || Math.Abs((int)m["delta"])>1200) throw new ArgumentException("Invalid scroll event."); Send(new Input {value=new Union { mouse=new MouseInput { flags=2048,data=unchecked((uint)(int)m["delta"]) } } }); }
                else if (type=="release") Release();
            }
        }
        public void Release() { lock(gate) { foreach(string code in keys.ToArray()) try { Key(code,false); } catch {} foreach(int button in buttons.ToArray()) try { Button(button,false); } catch {} keys.Clear(); buttons.Clear(); } }
    }

    static class Capture {
        static readonly ImageCodecInfo jpeg=ImageCodecInfo.GetImageEncoders().First(c=>c.MimeType=="image/jpeg");
        public static byte[] Jpeg(int width,long quality) {
            var screen=Screen.PrimaryScreen.Bounds;
            using(var full=new Bitmap(screen.Width,screen.Height,PixelFormat.Format24bppRgb)) {
                using(var graphics=Graphics.FromImage(full)) graphics.CopyFromScreen(screen.Location,Point.Empty,screen.Size);
                double scale=Math.Min(1.0,(double)width/full.Width);
                using(var image=new Bitmap(Math.Max(1,(int)(full.Width*scale)),Math.Max(1,(int)(full.Height*scale)),PixelFormat.Format24bppRgb)) {
                    using(var graphics=Graphics.FromImage(image)) {
                        graphics.InterpolationMode=InterpolationMode.NearestNeighbor; graphics.DrawImage(full,new Rectangle(0,0,image.Width,image.Height));
                        Point cursor=Cursor.Position; int x=(int)(cursor.X*scale),y=(int)(cursor.Y*scale);
                        Point[] shape={new Point(x,y),new Point(x+3,y+17),new Point(x+8,y+11),new Point(x+15,y+10)};
                        graphics.FillPolygon(Brushes.White,shape); graphics.DrawPolygon(Pens.Black,shape);
                    }
                    using(var parameters=new EncoderParameters(1)) using(var output=new MemoryStream()) {
                        parameters.Param[0]=new EncoderParameter(System.Drawing.Imaging.Encoder.Quality,quality); image.Save(output,jpeg,parameters); return output.ToArray();
                    }
                }
            }
        }
    }
}
