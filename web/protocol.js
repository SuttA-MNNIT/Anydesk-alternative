// Wire format: version(1), sequence uint64 big-endian(8), IV(12), AES-GCM ciphertext + tag(16).
// Header + UTF-8 session ID + direction name are authenticated as AAD.
const enc = new TextEncoder();
export async function createChannel(secret, sessionId, role = 'viewer') {
  if (!/^[a-f0-9]{32}$/i.test(secret) || !/^[a-f0-9]{32}$/.test(sessionId)) throw new Error('Invalid session credentials.');
  const base = await crypto.subtle.importKey('raw', enc.encode(secret.toLowerCase()), 'PBKDF2', false, ['deriveBits']);
  const bits = new Uint8Array(await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: enc.encode(`CampusLink/1/${sessionId}`), iterations: 150000 }, base, 512));
  const viewerKey = await crypto.subtle.importKey('raw', bits.slice(0, 32), 'AES-GCM', false, ['encrypt', 'decrypt']);
  const hostKey = await crypto.subtle.importKey('raw', bits.slice(32), 'AES-GCM', false, ['encrypt', 'decrypt']);
  bits.fill(0);
  let seq = 0n, received = -1n;
  const sendKey = role === 'viewer' ? viewerKey : hostKey;
  const receiveKey = role === 'viewer' ? hostKey : viewerKey;
  const sendDirection = role;
  const receiveDirection = role === 'viewer' ? 'host' : 'viewer';
  function aad(header, direction) {
    const suffix = enc.encode(sessionId + direction);
    const result = new Uint8Array(header.length + suffix.length); result.set(header); result.set(suffix, header.length); return result;
  }
  return {
    async seal(type, payload) {
      const data = typeof payload === 'string' ? enc.encode(payload) : new Uint8Array(payload);
      const header = new Uint8Array(9); header[0] = 1; new DataView(header.buffer).setBigUint64(1, seq++);
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const plain = new Uint8Array(1 + data.length); plain[0] = type; plain.set(data, 1);
      const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: aad(header, sendDirection) }, sendKey, plain));
      const packet = new Uint8Array(21 + cipher.length); packet.set(header); packet.set(iv, 9); packet.set(cipher, 21); return packet;
    },
    async open(buffer) {
      const packet = new Uint8Array(buffer);
      if (packet.length < 38 || packet[0] !== 1) throw new Error('Invalid encrypted packet.');
      const n = new DataView(packet.buffer, packet.byteOffset, packet.byteLength).getBigUint64(1);
      if (n <= received) throw new Error('Replayed packet rejected.');
      const data = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: packet.slice(9, 21), additionalData: aad(packet.slice(0, 9), receiveDirection) }, receiveKey, packet.slice(21)));
      received = n; return { type: data[0], payload: data.slice(1) };
    }
  };
}
