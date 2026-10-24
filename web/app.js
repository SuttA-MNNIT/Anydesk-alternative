import { createChannel } from './protocol.js';
const $ = id => document.getElementById(id);
const decoder = new TextDecoder();
let socket, channel, controlling = false, approved = false, active = false, sendChain = Promise.resolve(), receiveChain = Promise.resolve();
let frameCount = 0, frameBytes = 0, lastStats = performance.now(), connectionEpoch = 0, secret = '', requestedName = '';
let moveAt = 0;
const pressed = new Set();
const canvas = $('screen'), context = canvas.getContext('2d', { alpha: false });
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
function reset(reason = 'Disconnected. The host must approve a new connection.') {
  connectionEpoch++;
  active = false; approved = false; controlling = false; channel = null; secret = ''; pressed.clear();
  if (socket && socket.readyState < 2) socket.close();
  socket = null;
  $('lobby').classList.remove('hidden'); $('desktop').classList.add('hidden'); document.body.classList.remove('connected');
  $('connect').disabled = false; $('cancel').classList.add('hidden');
  context.clearRect(0, 0, canvas.width, canvas.height); $('screen-wait').classList.remove('hidden');
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  message(reason);
}
function sendJson(value) {
  const epoch = connectionEpoch;
  sendChain = sendChain.then(async () => {
    if (!channel || !socket || socket.readyState !== WebSocket.OPEN || epoch !== connectionEpoch) return;
    if (socket.bufferedAmount > 256 * 1024) throw new Error('Input connection is too slow.');
    const packet = await channel.seal(1, JSON.stringify(value));
    if (epoch === connectionEpoch && socket?.readyState === WebSocket.OPEN) socket.send(packet);
  }).catch(err => { if (epoch === connectionEpoch) reset(err.message); });
}
async function receive(event, epoch) {
  if (epoch !== connectionEpoch) return;
  if (typeof event.data === 'string') {
    const msg = JSON.parse(event.data);
    if (msg.type === 'session') {
      const created = await createChannel(secret, msg.sessionId);
      if (epoch !== connectionEpoch) return;
      channel = created;
      secret = '';
      sendJson({ type: 'auth', name: requestedName, control: $('request-control').checked });
      message('Access key sent through the encrypted channel. Waiting for host approval…');
    } else if (msg.type === 'error' || msg.type === 'session-ended') reset(msg.message || msg.reason);
    return;
  }
  if (!channel) throw new Error('Unexpected session packet.');
  const packet = await channel.open(event.data);
  if (epoch !== connectionEpoch) return;
  if (packet.type === 1) {
    const msg = JSON.parse(decoder.decode(packet.payload));
    if (msg.type === 'approved') {
      approved = true; controlling = msg.control === true;
      $('mode').textContent = controlling ? 'Remote control' : 'View only';
      $('remote-name').textContent = msg.name || 'Windows desktop';
      $('lobby').classList.add('hidden'); $('desktop').classList.remove('hidden'); document.body.classList.add('connected');
      canvas.focus(); frameCount = 0; frameBytes = 0; lastStats = performance.now();
    } else if (msg.type === 'error' || msg.type === 'denied') reset(msg.message || 'Connection declined by the host.');
    else if (msg.type === 'control') {
      controlling = msg.enabled === true; $('mode').textContent = controlling ? 'Remote control' : 'View only';
      if (!controlling) pressed.clear();
    }
  } else if (packet.type === 2 && approved) {
    const bitmap = await createImageBitmap(new Blob([packet.payload], { type: 'image/jpeg' }));
    if (epoch !== connectionEpoch) { bitmap.close(); return; }
    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) { canvas.width = bitmap.width; canvas.height = bitmap.height; }
    context.drawImage(bitmap, 0, 0); bitmap.close(); $('screen-wait').classList.add('hidden');
    frameCount++; frameBytes += event.data.byteLength;
    const now = performance.now();
    if (now - lastStats > 1000) {
      const seconds = (now - lastStats) / 1000;
      $('stats').textContent = `${canvas.width} × ${canvas.height} · ${(frameCount / seconds).toFixed(0)} fps · ${(frameBytes * 8 / seconds / 1e6).toFixed(1)} Mbps`;
      frameCount = 0; frameBytes = 0; lastStats = now;
    }
    sendJson({ type: 'ack' });
  }
}
$('connect-form').addEventListener('submit', event => {
  event.preventDefault();
  const id = $('device').value.replace(/\D/g, '');
  const access = $('secret').value.replace(/[\s-]/g, '').toLowerCase();
  if (!/^\d{10}$/.test(id)) { message('Enter the 10-digit device ID.', true); return; }
  if (!/^[a-f0-9]{32}$/.test(access)) { message('Paste the 32-character access key from the host.', true); return; }
  if (!globalThis.isSecureContext || !crypto.subtle) { message('Open the viewer over HTTPS (or localhost) to enable encryption.', true); return; }
  reset('Connecting to the office relay…');
  active = true; secret = access; requestedName = $('name').value.trim().slice(0, 60) || 'Guest';
  $('secret').value = ''; $('connect').disabled = true; $('cancel').classList.remove('hidden');
  sendChain = Promise.resolve(); receiveChain = Promise.resolve();
  const epoch = connectionEpoch;
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
  socket = ws; ws.binaryType = 'arraybuffer';
  ws.onopen = () => { if (epoch === connectionEpoch) ws.send(JSON.stringify({ type: 'connect', deviceId: id })); };
  ws.onmessage = event => {
    receiveChain = receiveChain.then(() => receive(event, epoch)).catch(() => { if (epoch === connectionEpoch) reset('Session authentication failed. Check the access key and reconnect.'); });
  };
  ws.onerror = () => { if (epoch === connectionEpoch) reset('Cannot reach the relay. Check the server and tunnel.'); };
  ws.onclose = event => { if (epoch === connectionEpoch && active) reset(event.reason || 'Connection closed. Check the device ID and access key.'); };
});
$('cancel').onclick = () => reset('Connection cancelled.');
$('disconnect').onclick = () => reset();
$('fullscreen').onclick = () => { if (document.fullscreenElement) document.exitFullscreen(); else $('desktop').requestFullscreen().catch(() => {}); };
function point(event) {
  const rect = canvas.getBoundingClientRect();
  return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
}
canvas.addEventListener('contextmenu', event => event.preventDefault());
canvas.addEventListener('pointermove', event => {
  if (!controlling || !approved || performance.now() - moveAt < 33) return;
  moveAt = performance.now(); sendJson({ type: 'move', ...point(event) });
});
canvas.addEventListener('pointerdown', event => {
  canvas.focus(); if (!controlling || !approved || event.button > 2) return;
  event.preventDefault(); canvas.setPointerCapture(event.pointerId);
  sendJson({ type: 'button', down: true, button: event.button, ...point(event) });
});
canvas.addEventListener('pointerup', event => {
  if (!controlling || !approved || event.button > 2) return;
  event.preventDefault(); sendJson({ type: 'button', down: false, button: event.button, ...point(event) });
});
canvas.addEventListener('pointercancel', () => { if (controlling) sendJson({ type: 'release' }); });
canvas.addEventListener('wheel', event => {
  if (!controlling || !approved) return;
  event.preventDefault(); sendJson({ type: 'wheel', delta: Math.sign(event.deltaY) * -120 });
}, { passive: false });
for (const type of ['keydown', 'keyup']) canvas.addEventListener(type, event => {
  if (!controlling || !approved || event.code === 'Escape') return;
  event.preventDefault();
  const down = type === 'keydown';
  if (down) pressed.add(event.code); else pressed.delete(event.code);
  sendJson({ type: 'key', down, code: event.code });
});
function release() { if (approved && controlling) sendJson({ type: 'release' }); pressed.clear(); }
window.addEventListener('blur', release);
canvas.addEventListener('blur', release);
document.addEventListener('visibilitychange', () => { if (document.hidden) release(); });
window.addEventListener('beforeunload', () => { socket?.close(); });
fetch('/healthz').then(r => { if (!r.ok) throw new Error(); $('relay-status').innerHTML = '<i></i> Office relay online'; }).catch(() => { $('relay-status').textContent = 'Relay unavailable'; $('relay-status').classList.add('offline'); });
if (!globalThis.isSecureContext) message('Use HTTPS for outside access. Plain HTTP only works on localhost.', true);
