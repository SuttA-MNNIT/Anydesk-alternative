import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { createRelay } from '../server/index.mjs';
import { createChannel } from '../web/protocol.js';

const token = 'a'.repeat(64), secret = '0123456789abcdef0123456789abcdef';
function next(ws) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('Timed out waiting for message')); }, 4000);
    const message = (data, binary) => { cleanup(); resolve(binary ? data : JSON.parse(data.toString())); };
    const close = () => { cleanup(); reject(new Error('Socket closed before message')); };
    function cleanup() { clearTimeout(timer); ws.off('message', message); ws.off('close', close); }
    ws.on('message', message); ws.on('close', close);
  });
}
async function fixture(t) {
  const relay = createRelay({ enrollmentToken: token }, { info() {} });
  relay.server.listen(0, '127.0.0.1'); await once(relay.server, 'listening');
  t.after(() => relay.close());
  const port = relay.server.address().port;
  return { relay, url: `ws://127.0.0.1:${port}/ws`, http: `http://127.0.0.1:${port}` };
}
async function open(url, options = {}) {
  const ws = new WebSocket(url, options); await once(ws, 'open'); return ws;
}
async function register(url, id = '1234567890') {
  const host = await open(url); const reply = next(host);
  host.send(JSON.stringify({ type: 'register-host', token, deviceId: id }));
  assert.equal((await reply).type, 'registered'); return host;
}
async function pair(url, host) {
  const viewer = await open(url); const hp = next(host), vp = next(viewer);
  viewer.send(JSON.stringify({ type: 'connect', deviceId: '1234567890' }));
  const [h, v] = await Promise.all([hp, vp]);
  assert.equal(h.sessionId, v.sessionId); return { viewer, sessionId: v.sessionId };
}
test('viewer and health endpoint are served with security headers; no file traversal', async t => {
  const f = await fixture(t);
  const page = await fetch(f.http);
  assert.equal(page.status, 200); assert.match(await page.text(), /CampusLink/);
  assert.match(page.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  assert.equal(page.headers.get('referrer-policy'), 'no-referrer');
  assert.equal((await fetch(f.http + '/config/relay.json')).status, 404);
  assert.equal((await fetch(f.http + '/%2e%2e/package.json')).status, 404);
  assert.deepEqual(await (await fetch(f.http + '/healthz')).json(), { status: 'ok', protocol: 1 });
});
test('host enrollment rejects invalid token and prevents duplicate device registration', async t => {
  const f = await fixture(t);
  const bad = await open(f.url); const rejected = once(bad, 'close');
  bad.send(JSON.stringify({ type: 'register-host', token: 'bad', deviceId: '1234567890' }));
  assert.equal((await rejected)[0], 1008);
  await register(f.url);
  const duplicate = await open(f.url); const duplicateClosed = once(duplicate, 'close');
  duplicate.send(JSON.stringify({ type: 'register-host', token, deviceId: '1234567890' }));
  assert.equal((await duplicateClosed)[0], 1008);
  assert.equal(f.relay.hosts.size, 1);
});
test('cross-origin browser socket and unexpected paths are rejected', async t => {
  const f = await fixture(t);
  for (const [url, options] of [[f.url, { origin: 'https://evil.example' }], [f.url + '/bad', {}]]) {
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(url, options);
      ws.on('unexpected-response', (_, response) => { assert.equal(response.statusCode, 403); response.resume(); ws.terminate(); resolve(); });
      ws.on('error', () => {}); ws.on('open', () => { ws.close(); reject(new Error('Unexpected origin accepted')); });
    });
  }
});
test('binary frames and control remain encrypted through relay; session tears down cleanly', async t => {
  const f = await fixture(t); const host = await register(f.url); const { viewer, sessionId } = await pair(f.url, host);
  const hc = await createChannel(secret, sessionId, 'host'), vc = await createChannel(secret, sessionId);
  const auth = await vc.seal(1, JSON.stringify({ type: 'auth', name: 'Test Viewer', control: true }));
  assert.equal(Buffer.from(auth).includes(Buffer.from('Test Viewer')), false);
  const hp = next(host); viewer.send(auth); const authPacket = await hp;
  assert.deepEqual(Buffer.from(auth), authPacket);
  const opened = await hc.open(authPacket); assert.equal(JSON.parse(new TextDecoder().decode(opened.payload)).type, 'auth');
  host.send(JSON.stringify({ type: 'ready' }));
  const vp = next(viewer); host.send(await hc.seal(2, new Uint8Array([0xff, 0xd8, 1, 2, 0xff, 0xd9])));
  const frame = await vc.open(await vp); assert.equal(frame.type, 2); assert.equal(frame.payload[0], 0xff);
  const endedHost = next(host), endedViewer = next(viewer);
  viewer.send(JSON.stringify({ type: 'end' }));
  assert.equal((await endedHost).type, 'session-ended'); assert.equal((await endedViewer).type, 'session-ended');
  assert.equal(f.relay.sessions.size, 0); assert.equal(f.relay.hosts.size, 1);
  assert.ok(f.relay.metrics.bytesForwarded > 0);
});
test('unavailable devices give no metadata; host disconnect ends viewer session', async t => {
  const f = await fixture(t); const unavailable = await open(f.url); const failure = next(unavailable);
  unavailable.send(JSON.stringify({ type: 'connect', deviceId: '1111111111' }));
  assert.deepEqual(await failure, { type: 'error', message: 'Device unavailable or busy.' });
  const host = await register(f.url); const { viewer } = await pair(f.url, host);
  const ended = next(viewer); host.close(); assert.equal((await ended).type, 'session-ended');
});
test('malformed JSON and oversized control packets are rejected', async t => {
  const f = await fixture(t); const ws = await open(f.url); const closed = once(ws, 'close');
  ws.send('{'); assert.equal((await closed)[0], 1008);
  const host = await register(f.url); const { viewer } = await pair(f.url, host);
  const ended = next(host); viewer.send(Buffer.alloc(20_000));
  assert.equal((await ended).reason, 'Control packet too large');
});
test('channel rejects wrong key, tampering, reflected packets and replay', async () => {
  const sid = '1'.repeat(32), host = await createChannel(secret, sid, 'host'), viewer = await createChannel(secret, sid);
  const wrong = await createChannel('f'.repeat(32), sid);
  const packet = await host.seal(1, '{"type":"approved"}');
  await assert.rejects(wrong.open(packet)); await assert.rejects(host.open(packet));
  const modified = new Uint8Array(packet); modified[modified.length - 1] ^= 1;
  await assert.rejects(viewer.open(modified));
  assert.equal((await viewer.open(packet)).type, 1);
  await assert.rejects(viewer.open(packet), /Replay/);
});

test('enrolled host can explicitly enable full-size native reverse video after approval', async t => {
  const f = await fixture(t); const host = await register(f.url); const { viewer } = await pair(f.url, host);
  host.send(JSON.stringify({ type: 'ready' }));
  const enabled = next(host); host.send(JSON.stringify({ type: 'allow-reverse' }));
  assert.equal((await enabled).type, 'reverse-enabled');
  const largeFrame = Buffer.alloc(64 * 1024, 7);
  const received = next(host); viewer.send(largeFrame);
  assert.deepEqual(await received, largeFrame);
});
