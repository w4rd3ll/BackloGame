import assert from 'node:assert/strict';
import test from 'node:test';
import worker,{profileName} from '../deploy/cloudflare-steam/worker.mjs';
const key='a'.repeat(32);
const env={STEAM_API_KEY:key,LIBRARY_RATE_LIMIT:{limit:async()=>({success:true})}};
const ctx={waitUntil:()=>{}};
const req=(profile='76561198055848505')=>new Request('https://example.workers.dev/v1/steam/library?profile='+encodeURIComponent(profile));

test('rejects arbitrary hosts and malformed profiles',()=>{
  assert.equal(profileName('https://steamcommunity.com/id/test/'),'test');
  for(const value of ['https://evil.example/id/test','https://steamcommunity.com@evil.example/id/test','http://steamcommunity.com/id/test','test?key=bad'])assert.throws(()=>profileName(value));
});
test('requires key and rate limiter',async()=>{
  assert.equal((await worker.fetch(req(),{},ctx)).status,503);
  assert.equal((await worker.fetch(req(),{STEAM_API_KEY:key},ctx)).status,503);
});
test('only known read routes accepted',async()=>{
  assert.equal((await worker.fetch(new Request('https://example.workers.dev/other'),env,ctx)).status,404);
  assert.equal((await worker.fetch(new Request(req().url,{method:'POST'}),env,ctx)).status,405);
  assert.equal((await worker.fetch(new Request(req().url+'&url=https://evil.example'),env,ctx)).status,400);
});
test('rate limit refuses upstream fetch',async()=>{
  assert.equal((await worker.fetch(req(),{...env,LIBRARY_RATE_LIMIT:{limit:async()=>({success:false})}},ctx)).status,429);
});
test('public library uses fixed Steam host and never returns key',async()=>{
  const original=globalThis.fetch;
  const calls=[];
  globalThis.fetch=async url=>{calls.push(url);return Response.json({response:{game_count:1,games:[{appid:400,name:'Portal',notes:'private'}]}});};
  try {
    const response=await worker.fetch(req(),env,ctx);
    assert.equal(response.status,200);
    const text=await response.text();
    assert.deepEqual(JSON.parse(text),{games:[{title:'Portal',source_id:'steam:400'}]});
    assert.equal(new URL(calls[0]).hostname,'api.steampowered.com');
    assert.equal(text.includes(key),false);
    assert.equal(text.includes('private'),false);
  }finally{globalThis.fetch=original;}
});
test('upstream failures do not leak URL or key',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async()=>{throw Error('https://api.steampowered.com/?key='+key);};
  try {
    const response=await worker.fetch(req(),env,ctx);
    assert.equal(response.status,502);
    assert.equal((await response.text()).includes(key),false);
  }finally{globalThis.fetch=original;}
});
