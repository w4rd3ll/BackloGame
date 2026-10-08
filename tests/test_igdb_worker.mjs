import assert from 'node:assert/strict';
import test from 'node:test';
import worker from '../deploy/cloudflare-steam/worker.mjs';
import {normalizeGame,searchTerms,searchQueries,rankSearch} from '../deploy/cloudflare-steam/igdb.mjs';
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
    assert.equal(calls[1].url,'https://api.igdb.com/v4/games');assert.ok(calls[1].options.body.includes('where name ~ "Portal";'));assert.ok(calls[2].options.body.startsWith('search "Portal";'));assert.ok(calls[2].options.body.includes('limit 100;'));
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

test('exact original sorts before sequels and duplicate records are removed',()=>{
 const result=rankSearch([{id:2,name:"Assassin's Creed II"},{id:1,name:"Assassin's Creed",first_release_date:1194912000},{id:1,name:"Assassin's Creed",first_release_date:1194912000}],"Assassin's Creed");
 assert.equal(result.length,2);assert.equal(result[0].source_id,'igdb:1');
});
test('year suffix filters release dates and is excluded from title search',()=>{
 for(const query of ["Assassin's Creed 2007","Assassin's Creed (2007)"]){
  assert.deepEqual(searchTerms(query),{title:"Assassin's Creed",year:2007});
  const queries=searchQueries(query);assert(queries[1].startsWith('search "Assassin\'s Creed";'));
  assert(queries.every(q=>q.includes('first_release_date >=')));
  const rows=rankSearch([{id:1,name:"Assassin's Creed",first_release_date:1194912000},{id:2,name:"Assassin's Creed II",first_release_date:1258416000}],query);
  assert.equal(rows.length,1);assert.equal(rows[0].source_id,'igdb:1');
 }
 assert.deepEqual(searchTerms('Cyberpunk 2077'),{title:'Cyberpunk 2077',year:null});
});

test('expanded search keeps original first within a bounded lightweight response',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async(url,options)=>url.includes('oauth2')?Response.json({access_token:'fixture-token',expires_in:3600}):Response.json(options.body.includes('where name ~')?[{id:1,name:'Example',first_release_date:1194912000}]:Array.from({length:100},(_,i)=>({id:i+2,name:'Example '+i+' '+'.'.repeat(90),summary:'Long metadata must not enter search results'.repeat(100)})));
 try{
  const response=await worker.fetch(req('search?q=Example'),env,ctx),raw=await response.text(),items=JSON.parse(raw).items;
  assert.equal(response.status,200);assert.equal(items[0].source_id,'igdb:1');assert(items.length>20);
  assert(new TextEncoder().encode(raw).length<=12000);assert(!raw.includes('Long metadata'));
 }finally{globalThis.fetch=original;}
});
