using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace CampusLink.Client {
    // Matches host/protocol.py. Uses Windows CNG; no bundled crypto library.
    public sealed class CryptoChannel : IDisposable {
        readonly CngGcm sender, receiver;
        readonly byte[] sendSuffix, receiveSuffix;
        ulong sequence;
        ulong received;
        bool hasReceived;
        public CryptoChannel(string secret, string sessionId) {
            byte[] material;
            using (var derive = new Rfc2898DeriveBytes(secret.ToLowerInvariant(), Encoding.UTF8.GetBytes("CampusLink/1/" + sessionId), 150000, HashAlgorithmName.SHA256)) material = derive.GetBytes(64);
            sender = new CngGcm(material.Take(32).ToArray());
            receiver = new CngGcm(material.Skip(32).ToArray());
            Array.Clear(material, 0, material.Length);
            sendSuffix = Encoding.UTF8.GetBytes(sessionId + "viewer");
            receiveSuffix = Encoding.UTF8.GetBytes(sessionId + "host");
        }
        public byte[] Seal(byte kind, byte[] payload) {
            var header = new byte[9]; header[0] = 1;
            ulong current = sequence++;
            for (int i = 8; i > 0; i--) { header[i] = (byte)current; current >>= 8; }
            var nonce = new byte[12]; using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(nonce);
            byte[] plain = new byte[payload.Length + 1]; plain[0] = kind; Buffer.BlockCopy(payload, 0, plain, 1, payload.Length);
            return header.Concat(nonce).Concat(sender.Transform(plain, nonce, header.Concat(sendSuffix).ToArray(), false)).ToArray();
        }
        public byte[] Open(byte[] packet) {
            if (packet.Length < 38 || packet[0] != 1) throw new CryptographicException("Invalid encrypted packet.");
            ulong n = 0; for (int i = 1; i < 9; i++) n = (n << 8) | packet[i];
            if (hasReceived && n <= received) throw new CryptographicException("Replayed packet rejected.");
            var data = receiver.Transform(packet.Skip(21).ToArray(), packet.Skip(9).Take(12).ToArray(), packet.Take(9).Concat(receiveSuffix).ToArray(), true);
            received = n; hasReceived = true; return data;
        }
        public void Dispose() { sender.Dispose(); receiver.Dispose(); }
    }

    sealed class CngGcm : IDisposable {
        IntPtr algorithm, key;
        [StructLayout(LayoutKind.Sequential)]
        struct AuthInfo {
            public int cbSize, version;
            public IntPtr nonce; public int nonceLength;
            public IntPtr aad; public int aadLength;
            public IntPtr tag; public int tagLength;
            public IntPtr mac; public int macLength;
            public int cbAAD; public long cbData; public int flags;
        }
        [DllImport("bcrypt.dll", CharSet=CharSet.Unicode)] static extern int BCryptOpenAlgorithmProvider(out IntPtr algorithm, string id, string implementation, int flags);
        [DllImport("bcrypt.dll", CharSet=CharSet.Unicode)] static extern int BCryptSetProperty(IntPtr handle, string name, byte[] value, int length, int flags);
        [DllImport("bcrypt.dll")] static extern int BCryptGenerateSymmetricKey(IntPtr algorithm, out IntPtr key, IntPtr buffer, int size, byte[] secret, int secretLength, int flags);
        [DllImport("bcrypt.dll")] static extern int BCryptEncrypt(IntPtr key, byte[] input, int inputLength, ref AuthInfo info, IntPtr iv, int ivLength, byte[] output, int outputLength, out int result, int flags);
        [DllImport("bcrypt.dll")] static extern int BCryptDecrypt(IntPtr key, byte[] input, int inputLength, ref AuthInfo info, IntPtr iv, int ivLength, byte[] output, int outputLength, out int result, int flags);
        [DllImport("bcrypt.dll")] static extern int BCryptDestroyKey(IntPtr key);
        [DllImport("bcrypt.dll")] static extern int BCryptCloseAlgorithmProvider(IntPtr algorithm, int flags);
        static void Check(int status) { if (status != 0) throw new CryptographicException("Windows authenticated encryption failed (0x" + status.ToString("X8") + ")."); }
        public CngGcm(byte[] material) {
            try {
                Check(BCryptOpenAlgorithmProvider(out algorithm, "AES", null, 0));
                byte[] mode = Encoding.Unicode.GetBytes("ChainingModeGCM\0");
                Check(BCryptSetProperty(algorithm, "ChainingMode", mode, mode.Length, 0));
                Check(BCryptGenerateSymmetricKey(algorithm, out key, IntPtr.Zero, 0, material, material.Length, 0));
            } catch { Dispose(); throw; }
            finally { Array.Clear(material, 0, material.Length); }
        }
        public byte[] Transform(byte[] input, byte[] nonce, byte[] aad, bool decrypt) {
            if (decrypt && input.Length < 16) throw new CryptographicException("Invalid GCM tag.");
            byte[] tag = decrypt ? input.Skip(input.Length-16).ToArray() : new byte[16];
            byte[] content = decrypt ? input.Take(input.Length-16).ToArray() : input;
            var output = new byte[content.Length];
            var n = GCHandle.Alloc(nonce, GCHandleType.Pinned);
            var a = GCHandle.Alloc(aad, GCHandleType.Pinned);
            var t = GCHandle.Alloc(tag, GCHandleType.Pinned);
            try {
                var info = new AuthInfo { cbSize=Marshal.SizeOf(typeof(AuthInfo)), version=1, nonce=n.AddrOfPinnedObject(), nonceLength=nonce.Length,
                    aad=a.AddrOfPinnedObject(), aadLength=aad.Length, tag=t.AddrOfPinnedObject(), tagLength=16 };
                int length;
                int status = decrypt ? BCryptDecrypt(key, content, content.Length, ref info, IntPtr.Zero, 0, output, output.Length, out length, 0)
                    : BCryptEncrypt(key, content, content.Length, ref info, IntPtr.Zero, 0, output, output.Length, out length, 0);
                Check(status);
                return decrypt ? output : output.Concat(tag).ToArray();
            } finally { n.Free(); a.Free(); t.Free(); }
        }
        public void Dispose() { if (key != IntPtr.Zero) { BCryptDestroyKey(key); key=IntPtr.Zero; } if (algorithm != IntPtr.Zero) { BCryptCloseAlgorithmProvider(algorithm,0); algorithm=IntPtr.Zero; } }
    }
}
