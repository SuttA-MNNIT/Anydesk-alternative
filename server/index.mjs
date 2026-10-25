import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { timingSafeEqual, randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { WebSocketServer, WebSocket } from 'ws';

const root = fileURLToPath(new URL('../', import.meta.url));
const staticFiles = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/style.css', ['style.css', 'text/css; charset=utf-8']],
  ['/protocol.js', ['protocol.js', 'text/javascript; charset=utf-8']]
]);
const equals = (a, b) => typeof a === 'string' && typeof b === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));

export function createRelay(config, logger = console) {
  if (typeof config.enrollmentToken !== 'string' || config.enrollmentToken.length < 32) throw new Error('Run npm run setup first: enrollment token is missing or too short.');
  const hosts = new Map();
  const sessions = new Map();
  const limits = new Map();
  const counts = new Map();
  const metrics = { paired: 0, bytesForwarded: 0, started: Date.now() };
  function budget(ip, cost = 1) {
    const now = Date.now();
    let entry = limits.get(ip);
    if (!entry || now > entry.until) { entry = { count: 0, until: now + 60_000 }; limits.set(ip, entry); }
    entry.count += cost;
    return entry.count <= 30;
  }
  function send(ws, value) { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(value)); }
  function end(pair, reason = 'Session ended') {
    if (!pair || !sessions.delete(pair.sessionId)) return;
    clearTimeout(pair.timer);
    if (pair.host.pair === pair) pair.host.pair = null;
    if (pair.viewer.pair === pair) pair.viewer.pair = null;
    send(pair.host, { type: 'session-ended', reason });
    send(pair.viewer, { type: 'session-ended', reason });
    pair.viewer.close(1000, reason.slice(0, 100));
  }
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    const url = new URL(req.url, 'http://localhost');
    if (req.method !== 'GET') { res.writeHead(405); res.end(); return; }
    if (url.pathname === '/healthz') {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ status: 'ok', protocol: 1 })); return;
    }
    // No public device directory, session list, IP addresses, tokens or metrics.
    const file = staticFiles.get(url.pathname);
    if (!file) { res.writeHead(404); res.end('Not found'); return; }
    try { res.setHeader('Content-Type', file[1]); res.end(await readFile(path.join(root, 'web', file[0]))); }
    catch { res.writeHead(500); res.end('Unable to load viewer'); }
  });
  const wss = new WebSocketServer({ noServer: true, maxPayload: 3 * 1024 * 1024, perMessageDeflate: false });
  server.on('upgrade', (req, socket, head) => {
    // Deliberately ignore forwarded IP headers: an arbitrary client must not bypass rate limits.
    const ip = req.socket.remoteAddress || 'unknown';
    const origin = req.headers.origin;
    let validOrigin = !origin; // Native host has no Origin; browser viewer must be same-origin.
    if (origin) {
      try {
        const u = new URL(origin);
        validOrigin = (['http:', 'https:'].includes(u.protocol) && u.host === req.headers.host) || (config.allowedOrigins || []).includes(origin);
      } catch { validOrigin = false; }
    }
    if (req.url !== '/ws' || !validOrigin || !budget(ip) || (counts.get(ip) || 0) >= 100 || wss.clients.size >= 512) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return;
    }
    wss.handleUpgrade(req, socket, head, ws => { ws.ip = ip; wss.emit('connection', ws); });
  });
  wss.on('connection', ws => {
    ws.alive = true;
    counts.set(ws.ip, (counts.get(ws.ip) || 0) + 1);
    const registrationTimer = setTimeout(() => { if (!ws.role) ws.close(1008, 'Register within 10 seconds'); }, 10_000);
    registrationTimer.unref();
    ws.on('pong', () => { ws.alive = true; });
    ws.on('error', () => {});
    ws.on('message', (data, binary) => {
      if (binary) {
        const pair = ws.pair;
        if (!pair) { ws.close(1008, 'No session'); return; }
        if (ws.role === 'viewer' && !pair.reverseAllowed && data.length > 16_384) { end(pair, 'Control packet too large'); return; }
        const now = Date.now();
        if (!ws.rate || now > ws.rate.until) ws.rate = { count: 0, until: now + 1000 };
        if (++ws.rate.count > 300) { end(pair, 'Message rate exceeded'); return; }
        const peer = ws === pair.host ? pair.viewer : pair.host;
        if (peer.readyState !== WebSocket.OPEN || peer.bufferedAmount > 4 * 1024 * 1024) { end(pair, 'Connection too slow'); return; }
        peer.send(data, { binary: true });
        metrics.bytesForwarded += data.length;
        return;
      }
      if (data.length > 4096) { ws.close(1008, 'Message too large'); return; }
      let msg;
      try { msg = JSON.parse(data.toString()); } catch { ws.close(1008, 'Invalid message'); return; }
      if (!msg || typeof msg !== 'object') { ws.close(1008, 'Invalid message'); return; }
      if (msg.type === 'register-host' && !ws.role) {
        if (!equals(msg.token, config.enrollmentToken) || !/^\d{10}$/.test(msg.deviceId || '')) { ws.close(1008, 'Host registration rejected'); return; }
        if (hosts.has(msg.deviceId)) { ws.close(1008, 'Device ID is already in use'); return; }
        ws.role = 'host'; ws.deviceId = msg.deviceId; hosts.set(msg.deviceId, ws);
        clearTimeout(registrationTimer);
        send(ws, { type: 'registered', deviceId: msg.deviceId });
      } else if (msg.type === 'connect' && !ws.role) {
        if (!/^\d{10}$/.test(msg.deviceId || '') || !budget(ws.ip, 2)) { ws.close(1008, 'Connection rejected'); return; }
        const host = hosts.get(msg.deviceId);
        if (!host || host.pair) { send(ws, { type: 'error', message: 'Device unavailable or busy.' }); ws.close(1000); return; }
        ws.role = 'viewer'; clearTimeout(registrationTimer);
        const sessionId = randomBytes(16).toString('hex');
        const pair = { host, viewer: ws, sessionId, approved: false };
        pair.timer = setTimeout(() => end(pair, 'Approval timed out'), 60_000); pair.timer.unref();
        host.pair = pair; ws.pair = pair; sessions.set(sessionId, pair);
        send(host, { type: 'session', sessionId });
        send(ws, { type: 'session', sessionId });
      } else if (msg.type === 'ready' && ws.role === 'host' && ws.pair && !ws.pair.approved) {
        ws.pair.approved = true; clearTimeout(ws.pair.timer); metrics.paired++;
        logger.info('Attended session approved.');
      } else if (msg.type === 'allow-reverse' && ws.role === 'host' && ws.pair?.approved) {
        // Only the enrolled host can permit full-sized video from the other side.
        ws.pair.reverseAllowed = true;
        send(ws, { type: 'reverse-enabled' });
      } else if (msg.type === 'end' && ws.pair) {
        end(ws.pair, 'Disconnected by participant');
      } else { ws.close(1008, 'Unexpected message'); }
    });
    ws.on('close', () => {
      clearTimeout(registrationTimer);
      counts.set(ws.ip, Math.max(0, (counts.get(ws.ip) || 1) - 1));
      if (!counts.get(ws.ip)) counts.delete(ws.ip);
      if (ws.role === 'host' && hosts.get(ws.deviceId) === ws) hosts.delete(ws.deviceId);
      end(ws.pair, 'Peer disconnected');
    });
  });
  const heartbeat = setInterval(() => {
    for (const [ip, entry] of limits) if (Date.now() > entry.until) limits.delete(ip);
    for (const ws of wss.clients) { if (!ws.alive) ws.terminate(); else { ws.alive = false; ws.ping(); } }
  }, 25_000);
  heartbeat.unref();
  async function close() {
    clearInterval(heartbeat);
    for (const pair of [...sessions.values()]) end(pair, 'Relay stopped');
    for (const ws of wss.clients) ws.terminate();
    await new Promise(resolve => wss.close(resolve));
    if (server.listening) await new Promise(resolve => server.close(resolve));
  }
  return { server, close, metrics, hosts, sessions };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const config = JSON.parse(await readFile(process.env.CAMPUSLINK_RELAY_CONFIG || path.join(root, 'config/relay.json'), 'utf8'));
    const relay = createRelay(config);
    relay.server.listen(config.port ?? 8787, config.listenHost || '127.0.0.1', () => console.log(`CampusLink relay: http://${config.listenHost || '127.0.0.1'}:${relay.server.address().port}`));
    relay.server.on('error', err => { console.error(err.message); process.exitCode = 1; });
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => { await relay.close(); process.exit(0); });
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
