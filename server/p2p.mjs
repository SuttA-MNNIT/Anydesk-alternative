import { WebSocketServer, WebSocket } from 'ws';
import { randomBytes, randomInt, createHash, timingSafeEqual } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync, existsSync } from 'node:fs';

const hash = value => createHash('sha256').update(value).digest('hex');
const equal = (a,b) => typeof a === 'string' && a.length === b.length && timingSafeEqual(Buffer.from(a),Buffer.from(b));

// The broker never receives desktop keys or plaintext SDP, frames or input.
export function attachPeerBroker(server, config) {
  const devices=new Map(), identities=new Map(), pairs=new Map(), rates=new Map();
  const metrics={registrations:0,sessions:0,bytesForwarded:0,signalingBytes:0,rejections:0};
  if(config.peerState && existsSync(config.peerState)) {
    const saved=JSON.parse(readFileSync(config.peerState,'utf8'));
    for(const [key,id] of Object.entries(saved)) {
      if(!/^[a-f0-9]{64}$/.test(key) || !/^\d{10}$/.test(id) || identities.size>=10000 || [...identities.values()].includes(id)) throw Error('Invalid peer identity store');
      identities.set(key,id);
    }
  }
  function idFor(identity) {
    const key=hash(identity);
    if(identities.has(key)) return identities.get(key);
    if(identities.size>=10000) throw Error('Device registry is full');
    let id; do { id=String(randomInt(1_000_000_000,10_000_000_000)); } while([...identities.values()].includes(id));
    identities.set(key,id);
    if(config.peerState) {
      writeFileSync(config.peerState+'.tmp',JSON.stringify(Object.fromEntries(identities)),{mode:0o600});
      renameSync(config.peerState+'.tmp',config.peerState);
    }
    return id;
  }
  const send=(ws,msg)=>{if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify(msg));};
  const other=ws=>ws===ws.pair.host?ws.pair.viewer:ws.pair.host;
  function end(pair,reason='Disconnected') {
    if(!pair || !pairs.delete(pair.id))return;
    clearTimeout(pair.timer);
    for(const ws of [pair.host,pair.viewer]) {
      ws.pair=null;ws.closedSessions??=new Set();ws.closedSessions.add(pair.id);
      if(ws.closedSessions.size>4)ws.closedSessions.delete(ws.closedSessions.values().next().value);
      send(ws,{type:'ended',sessionId:pair.id,reason});
    }
  }
  const wss=new WebSocketServer({noServer:true,maxPayload:3*1024*1024+64,perMessageDeflate:false});
  server.on('upgrade',(req,socket,head)=>{
    if(req.url!=='/peer')return;
    const ip=req.socket.remoteAddress;
    let rate=rates.get(ip);if(!rate || Date.now()>rate.until){rate={n:0,until:Date.now()+60000};rates.set(ip,rate);}
    if(req.headers.origin || ++rate.n>100 || wss.clients.size>=512) {socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');return;}
    wss.handleUpgrade(req,socket,head,ws=>wss.emit('connection',ws));
  });
  wss.on('connection',ws=>{
    ws.alive=true;
    const registration=setTimeout(()=>{if(!ws.id)ws.close(1008,'Registration required');},10000);registration.unref();
    ws.on('pong',()=>{ws.alive=true;});ws.on('error',()=>{});
    ws.on('message',(data,binary)=>{
      try {
        const now=Date.now();if(!ws.rate || now>ws.rate.until)ws.rate={n:0,bytes:0,until:now+1000};
        ws.rate.bytes+=data.length;
        if(++ws.rate.n>600 || ws.rate.bytes>64*1024*1024)throw Error('Traffic limit exceeded');
        if(binary) {
          if(!ws.id || data.length<16+38)throw Error('Invalid session packet');
          const id=data.subarray(0,16).toString('hex');
          // A queued frame can follow the end notification on a slower route.
          if(ws.closedSessions?.has(id))return;
          if(!ws.pair || id!==ws.pair.id)throw Error('Invalid session packet');
          const peer=other(ws);
          if(peer.readyState!==WebSocket.OPEN || peer.bufferedAmount>4*1024*1024) {end(ws.pair,'Relay connection too slow');return;}
          peer.send(data,{binary:true});metrics.bytesForwarded+=data.length;return;
        }
        if(data.length>65536)throw Error('Signal too large');
        const msg=JSON.parse(data.toString());
        if(msg.type==='join' && !ws.id) {
          if(!equal(msg.token,config.enrollmentToken) || !/^[a-f0-9]{64}$/.test(msg.identity||''))throw Error('Registration rejected');
          const id=idFor(msg.identity);
          if(devices.has(id))throw Error('This client identity is already online');
          ws.id=id;devices.set(id,ws);clearTimeout(registration);metrics.registrations++;
          send(ws,{type:'registered',deviceId:id});return;
        }
        if(!ws.id)throw Error('Registration required');
        if(msg.type==='connect' && !ws.pair) {
          if(!/^\d{10}$/.test(msg.deviceId||'') || msg.deviceId===ws.id)throw Error('Invalid target');
          if(ws.lastConnect && now-ws.lastConnect<2000)throw Error('Try again shortly');ws.lastConnect=now;
          const host=devices.get(msg.deviceId);
          if(!host || host.pair){send(ws,{type:'unavailable',message:'Device unavailable or busy.'});return;}
          const pair={id:randomBytes(16).toString('hex'),host,viewer:ws,approved:false};
          pair.timer=setTimeout(()=>end(pair,'Approval timed out'),60000);pair.timer.unref();
          ws.pair=pair;host.pair=pair;pairs.set(pair.id,pair);metrics.sessions++;
          send(host,{type:'session',sessionId:pair.id,role:'host'});send(ws,{type:'session',sessionId:pair.id,role:'viewer'});return;
        }
        // An already queued acknowledgement/end can arrive after a pair closes.
        if(!ws.pair || msg.sessionId!==ws.pair.id)return;
        if(msg.type==='end'){end(ws.pair);return;}
        if(msg.type==='ready' && ws===ws.pair.host){ws.pair.approved=true;clearTimeout(ws.pair.timer);return;}
        if(['signal','ack','fallback'].includes(msg.type)) {
          if(msg.type==='signal' && (typeof msg.payload!=='string' || msg.payload.length>60000))throw Error('Invalid signal');
          if(msg.type==='ack' && (!Number.isSafeInteger(msg.n)||msg.n<0))throw Error('Invalid acknowledgement');
          metrics.signalingBytes+=data.length;send(other(ws),msg);return;
        }
        throw Error('Unexpected message');
      } catch {metrics.rejections++;ws.close(1008,'Peer protocol rejected');}
    });
    ws.on('close',()=>{clearTimeout(registration);if(devices.get(ws.id)===ws)devices.delete(ws.id);end(ws.pair,'Peer disconnected');});
  });
  const heartbeat=setInterval(()=>{
    for(const [ip,r] of rates)if(Date.now()>r.until)rates.delete(ip);
    for(const ws of wss.clients){if(!ws.alive)ws.terminate();else{ws.alive=false;ws.ping();}}
  },25000);heartbeat.unref();
  async function close(){clearInterval(heartbeat);for(const pair of [...pairs.values()])end(pair,'Server stopped');for(const ws of wss.clients)ws.terminate();await new Promise(r=>wss.close(r));}
  return {devices,pairs,metrics,close};
}
