// Fixed, read-only IGDB queries. Credentials are Cloudflare Secrets only.
let tokenState=null,tokenPending=null,nextRequest=0;
const fields='id,name,slug,summary,cover.image_id,artworks.image_id,screenshots.image_id,genres.name,involved_companies.company.name,involved_companies.developer,platforms.name,first_release_date,collections.name,franchises.name';
const text=(value,max=300)=>typeof value==='string'?value.slice(0,max):'';
const names=rows=>[...new Set((Array.isArray(rows)?rows:[]).map(row=>text(row?.name)).filter(Boolean))];
const image=(row,size)=>/^[a-zA-Z0-9_]{1,100}$/.test(row?.image_id||'')?'https://images.igdb.com/igdb/image/upload/t_'+size+'/'+row.image_id+'.jpg':'';
export function normalizeGame(row){
  if(!Number.isSafeInteger(row?.id)||row.id<=0||!text(row.name))return null;
  const url=/^[a-z0-9-]{1,200}$/.test(row.slug||'')?'https://www.igdb.com/games/'+row.slug:'https://www.igdb.com/games/'+row.id;
  const series=names(row.collections); // Collections are game series; franchises can span several series.
  let date='';if(Number.isSafeInteger(row.first_release_date)){
    const value=new Date(row.first_release_date*1000);if(Number.isFinite(value.getTime()))date=value.toISOString().slice(0,10);
  }
  return {source_id:'igdb:'+row.id,title:text(row.name),original_title:text(row.name),provider:'IGDB',
    description:text(row.summary,14000),description_language:'original',description_url:url,source_url:url,
    image:image(row.cover,'cover_big'),landscape_image:image(row.artworks?.[0]||row.screenshots?.[0],'screenshot_big'),
    genre:names(row.genres).join(', '),developer:names((row.involved_companies||[]).filter(c=>c.developer).map(c=>c.company)).join(', '),
    available_platforms:names(row.platforms).join(', '),release_date:date,series:series.join('; '),franchises:names(row.franchises).join('; ')};
}
async function jsonRequest(url,options){
  const response=await fetch(url,{...options,redirect:'manual',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Object.assign(Error('Upstream unavailable'),{status:response.status});
  const raw=await response.text();if(raw.length>3000000)throw Error('Response too large');return JSON.parse(raw);
}
async function accessToken(env){
  if(tokenState&&tokenState.client===env.IGDB_CLIENT_ID&&tokenState.secret===env.IGDB_CLIENT_SECRET&&tokenState.until>Date.now())return tokenState.value;
  if(!tokenPending)tokenPending=(async()=>{
    const data=await jsonRequest('https://id.twitch.tv/oauth2/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({client_id:env.IGDB_CLIENT_ID,client_secret:env.IGDB_CLIENT_SECRET,grant_type:'client_credentials'})});
    if(typeof data.access_token!=='string'||!Number.isFinite(data.expires_in)||data.expires_in<1)throw Error('Invalid token response');
    tokenState={client:env.IGDB_CLIENT_ID,secret:env.IGDB_CLIENT_SECRET,value:data.access_token,until:Date.now()+Math.max(0,data.expires_in-60)*1000};return data.access_token;
  })().finally(()=>{tokenPending=null;});
  return tokenPending;
}
async function games(env,query,retry=true){
  const token=await accessToken(env);
  const slot=Math.max(Date.now(),nextRequest);nextRequest=slot+275;
  if(slot>Date.now())await new Promise(resolve=>setTimeout(resolve,slot-Date.now()));
  try{return await jsonRequest('https://api.igdb.com/v4/games',{method:'POST',headers:{'Client-ID':env.IGDB_CLIENT_ID,Authorization:'Bearer '+token,Accept:'application/json'},body:query});}
  catch(error){if(error.status===401&&retry){tokenState=null;return games(env,query,false);}throw error;}
}
export async function igdbRoute(request,env,ctx,respond){
  const url=new URL(request.url),search=url.pathname==='/v1/igdb/search';
  if(!search&&url.pathname!=='/v1/igdb/game')return respond({error:'Not found'},404);
  const allowed=search?'q':'id',value=url.searchParams.get(allowed);
  if([...url.searchParams.keys()].some(k=>k!==allowed)||url.searchParams.getAll(allowed).length!==1||
     (search?typeof value!=='string'||!value.trim()||value.length>150||/[\x00-\x1f]/.test(value):!/^\d{1,10}$/.test(value||'')||Number(value)<=0))return respond({error:'Invalid IGDB query'},400);
  if(!env.IGDB_CLIENT_ID||!env.IGDB_CLIENT_SECRET||!env.IGDB_RATE_LIMIT)return respond({error:'IGDB service is not configured'},503);
  try{
    const limited=await env.IGDB_RATE_LIMIT.limit({key:request.headers.get('CF-Connecting-IP')||'unknown'});
    if(!limited.success)return respond({error:'Too many IGDB requests. Try again shortly.'},429);
    const canonical=search?value.trim().toLowerCase():String(Number(value));
    const cacheKey=new Request(url.origin+'/cached-igdb-'+(search?'search?q=':'game?id=')+encodeURIComponent(canonical));
    const cache=globalThis.caches?.default,cached=cache?await cache.match(cacheKey):null;
    if(cached)return respond(await cached.json());
    const query=search?'search '+JSON.stringify(value.trim())+'; fields '+fields+'; limit 20;':'fields '+fields+'; where id = '+Number(value)+'; limit 1;';
    const rows=await games(env,query);if(!Array.isArray(rows))throw Error('Invalid IGDB response');
    const items=rows.slice(0,20).map(normalizeGame).filter(Boolean),body=search?{items}:{game:items[0]||null};
    if(!search&&!body.game)return respond({error:'IGDB game not found'},404);
    if(cache)ctx.waitUntil(cache.put(cacheKey,new Response(JSON.stringify(body),{headers:{'Content-Type':'application/json','Cache-Control':'public,max-age=1800'}})));
    return respond(body);
  }catch(error){return respond({error:error.status===429?'IGDB request limit reached. Try again shortly.':'IGDB is temporarily unavailable.',...(Number.isInteger(error.status)?{upstream_status:error.status}:{})},error.status===429?429:502);}
}
