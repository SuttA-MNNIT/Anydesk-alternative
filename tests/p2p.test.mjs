import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { randomBytes } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WebSocket } from 'ws';
import { createRelay } from '../server/index.mjs';

const token='f'.repeat(64);
function next(ws){return new Promise((resolve,reject)=>{const timeout=setTimeout(()=>{clean();reject(Error('Timed out'));},3000);const message=(data,binary)=>{clean();resolve(binary?data:JSON.parse(data));};const close=()=>{clean();reject(Error('Socket closed'));};function clean(){clearTimeout(timeout);ws.off('message',message);ws.off('close',close);}ws.on('message',message);ws.on('close',close);});}
async function fixture(t,state){const relay=createRelay({enrollmentToken:token,peerState:state},{info(){}});relay.server.listen(0,'127.0.0.1');await once(relay.server,'listening');t.after(()=>relay.close());return {relay,url:`ws://127.0.0.1:${relay.server.address().port}/peer`};}
async function open(url){const ws=new WebSocket(url);await once(ws,'open');return ws;}
async function register(url,identity=randomBytes(32).toString('hex')){const ws=await open(url),reply=next(ws);ws.send(JSON.stringify({type:'join',token,identity}));const msg=await reply;assert.equal(msg.type,'registered');return {ws,id:msg.deviceId,identity};}
async function pair(a,b){const x=next(a.ws),y=next(b.ws);b.ws.send(JSON.stringify({type:'connect',deviceId:a.id}));const [host,viewer]=await Promise.all([x,y]);assert.equal(host.sessionId,viewer.sessionId);assert.equal(host.role,'host');assert.equal(viewer.role,'viewer');return host.sessionId;}

test('peer registration requires membership and unique authenticated identity',async t=>{
  const f=await fixture(t),bad=await open(f.url),closed=once(bad,'close');bad.send(JSON.stringify({type:'join',token:'bad',identity:'1'.repeat(64)}));assert.equal((await closed)[0],1008);
  const a=await register(f.url),b=await register(f.url);assert.notEqual(a.id,b.id);assert.match(a.id,/^\d{10}$/);
  const duplicate=await open(f.url),rejected=once(duplicate,'close');duplicate.send(JSON.stringify({type:'join',token,identity:a.identity}));assert.equal((await rejected)[0],1008);assert.equal(f.relay.broker.devices.size,2);
});
test('one broker carries multiple isolated pairs, encrypted relay and scoped signals',async t=>{
  const f=await fixture(t),a=await register(f.url),b=await register(f.url),c=await register(f.url),d=await register(f.url);
  const first=await pair(a,b),second=await pair(c,d);assert.notEqual(first,second);assert.equal(f.relay.broker.pairs.size,2);
  const signal=next(a.ws);b.ws.send(JSON.stringify({type:'signal',sessionId:first,payload:'opaque-encrypted-SDP'}));assert.equal((await signal).payload,'opaque-encrypted-SDP');
  const encrypted=Buffer.concat([Buffer.from(first,'hex'),randomBytes(128000)]),received=next(b.ws);a.ws.send(encrypted);assert.deepEqual(await received,encrypted);assert.equal(f.relay.broker.metrics.bytesForwarded,encrypted.length);
  const endedA=next(a.ws),endedB=next(b.ws);a.ws.send(JSON.stringify({type:'end',sessionId:first}));assert.equal((await endedA).type,'ended');assert.equal((await endedB).type,'ended');assert.equal(f.relay.broker.pairs.size,1);assert.equal(f.relay.broker.devices.size,4);
  a.ws.send(encrypted); // A late frame from the ended pair must not unregister A.
  // A stale end from an earlier session must not destroy a subsequent pair.
  b.ws.send(JSON.stringify({type:'end',sessionId:first}));await pair(b,a);assert.equal(f.relay.broker.pairs.size,2);
});
test('relay rejects packets for another session and clears only that pair',async t=>{
  const f=await fixture(t),a=await register(f.url),b=await register(f.url),c=await register(f.url),d=await register(f.url);
  await pair(a,b);const second=await pair(c,d),closed=once(a.ws,'close'),ended=next(b.ws);
  a.ws.send(Buffer.concat([Buffer.from(second,'hex'),randomBytes(128)]));assert.equal((await closed)[0],1008);assert.equal((await ended).type,'ended');assert.equal(f.relay.broker.pairs.size,1);
});
test('server-issued IDs persist across broker restarts without storing bearer credentials',async t=>{
  const directory=await mkdtemp(join(tmpdir(),'CampusLink-P2P-test-'));t.after(()=>rm(directory,{recursive:true,force:true}));
  const state=join(directory,'devices.json'),f=await fixture(t,state),a=await register(f.url),id=a.id;
  a.ws.close();await once(a.ws,'close');const g=await fixture(t,state),again=await register(g.url,a.identity);assert.equal(again.id,id);
  const {readFile}=await import('node:fs/promises');assert.equal((await readFile(state,'utf8')).includes(a.identity),false);
});
