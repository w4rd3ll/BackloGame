import assert from 'node:assert/strict';
import test from 'node:test';
import worker from '../deploy/cloudflare-steam/worker.mjs';
import {normalizeGame} from '../deploy/cloudflare-steam/igdb.mjs';
const ctx={waitUntil:()=>{}},env={IGDB_CLIENT_ID:'fixture-client',IGDB_CLIENT_SECRET:'fixture-secret',IGDB_RATE_LIMIT:{limit:async()=>({success:true})}};
const req=path=>new Request('https://example.workers.dev/v1/igdb/'+path);
test('normalizes game series, developers, date and fixed image hosts',()=>{
  const game=normalizeGame({id:1,name:'Portal',slug:'portal',summary:'summary',first_release_date:1191974400,cover:{image_id:'co123'},artworks:[{image_id:'ar123'}],collections:[{name:'Portal'}],franchises:[{name:'Half-Life universe'}],involved_companies:[{developer:true,company:{name:'Valve'}},{developer:false,company:{name:'Publisher'}}]});
  assert.equal(game.series,'Portal');assert.equal(game.developer,'Valve');assert.equal(game.release_date,'2007-10-10');
  assert.equal(new URL(game.image).hostname,'images.igdb.com');assert.ok(game.landscape_image.includes('screenshot_big'));
  assert.equal(normalizeGame({id:2,name:'Standalone',franchises:[{name:'Universe'}]}).series,'');
  assert.equal(normalizeGame({id:3,name:'Bad image',cover:{image_id:'../../evil'}}).image,'');
});
test('rejects malformed routes and parameters without upstream requests',async()=>{
  for(const path of ['game?id=0','game?id=1;fields=*','search?q=a&q=b','search?q=a&url=evil','search?q=%0a','anything?q=a'])assert.ok((await worker.fetch(req(path),env,ctx)).status>=400);
  assert.equal((await worker.fetch(req('search?q=Portal'),{},ctx)).status,503);
  assert.equal((await worker.fetch(req('search?q=Portal'),{...env,IGDB_RATE_LIMIT:{limit:async()=>({success:false})}},ctx)).status,429);
});
test('obtains token through POST, queries only games and never returns credentials',async()=>{
  const original=globalThis.fetch,calls=[];
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return url.includes('oauth2')?Response.json({access_token:'fixture-'+'access-token',expires_in:3600}):Response.json([{id:1,name:'Portal',collections:[{name:'Portal'}]}]);};
  try{
    const result=await worker.fetch(req('search?q=Portal'),env,ctx),raw=await result.text();
    assert.equal(result.status,200);assert.equal(JSON.parse(raw).items[0].source_id,'igdb:1');
    assert.equal(calls[0].url,'https://id.twitch.tv/oauth2/token');assert.equal(calls[0].options.method,'POST');
    assert.equal(calls[1].url,'https://api.igdb.com/v4/games');assert.ok(calls[1].options.body.startsWith('search "Portal";'));
    for(const value of ['fixture-secret','fixture-client','fixture-access-token'])assert.equal(raw.includes(value),false);
  }finally{globalThis.fetch=original;}
});
test('upstream exception text never reaches the public response',async()=>{
  const original=globalThis.fetch;globalThis.fetch=async()=>{throw Error('fixture-secret fixture-access-token');};
  try{const response=await worker.fetch(req('game?id=1'),env,ctx);assert.equal(response.status,502);assert.equal((await response.text()).includes('fixture-'),false);}
  finally{globalThis.fetch=original;}
});
test('expired upstream token is renewed once and game request is retried',async()=>{
  const original=globalThis.fetch;let gameCalls=0,tokenCalls=0;
  globalThis.fetch=async(url)=>{
    if(url.includes('oauth2')){tokenCalls++;return Response.json({access_token:'renewed-fixture',expires_in:3600});}
    gameCalls++;return gameCalls===1?new Response('',{status:401}):Response.json([{id:71,name:'Portal'}]);
  };
  try{const response=await worker.fetch(req('game?id=71'),env,ctx);assert.equal(response.status,200);assert.equal(gameCalls,2);assert.equal(tokenCalls,1);}
  finally{globalThis.fetch=original;}
});
