// Public Steam libraries only. Store STEAM_API_KEY as a Cloudflare Secret.
const respond = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});

export function profileName(value) {
  let name=String(value||'').trim();
  if(name.startsWith('https://')) {
    const url=new URL(name);
    if(url.hostname!=='steamcommunity.com'||url.username||url.password||url.port||url.search||url.hash)throw Error('Invalid profile');
    const match=url.pathname.match(/^\/(?:id|profiles)\/([A-Za-z0-9_-]{1,64})\/?$/);
    if(!match)throw Error('Invalid profile');
    name=match[1];
  }
  if(!/^[A-Za-z0-9_-]{1,64}$/.test(name))throw Error('Invalid profile');
  return name;
}

async function steam(path,params,key) {
  const url=new URL('https://api.steampowered.com/'+path);
  url.search=new URLSearchParams({...params,key});
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),15000);
  let response;
  try {
    response=await fetch(url.toString(),{redirect:'manual',signal:controller.signal,headers:{Accept:'application/json'}});
  }catch {
    throw Object.assign(Error('Steam request failed'),{reason:'network'});
  }finally {clearTimeout(timer);}
  if(!response.ok)throw Object.assign(Error('Steam unavailable'),{upstreamStatus:response.status});
  const raw=await response.text();
  if(raw.length>8000000)throw Error('Library too large');
  try {return JSON.parse(raw).response;}
  catch {throw Object.assign(Error('Invalid Steam response'),{reason:'invalid_json'});}
}

export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url);
    if(request.method!=='GET')return respond({error:'Method not allowed'},405);
    const configured=/^[a-fA-F0-9]{32}$/.test(env.STEAM_API_KEY||'');
    if(url.pathname==='/health')return respond({app:'backlogame-steam-relay',configured},configured?200:503);
    if(url.pathname!=='/v1/steam/library')return respond({error:'Not found'},404);
    if(!configured)return respond({error:'Steam service is not configured'},503);
    if([...url.searchParams.keys()].some(key=>key!=='profile')||url.searchParams.getAll('profile').length!==1)return respond({error:'Provide one Steam profile'},400);
    let name;
    try{name=profileName(url.searchParams.get('profile'));}catch{return respond({error:'Invalid Steam profile'},400);}
    // Bind Cloudflare's rate limiter before exposing this service publicly.
    if(!env.LIBRARY_RATE_LIMIT)return respond({error:'Rate limiter is not configured'},503);
    let stage='rate_limit';
    try {
      const limited=await env.LIBRARY_RATE_LIMIT.limit({key:request.headers.get('CF-Connecting-IP')||'unknown'});
      if(!limited.success)return respond({error:'Too many requests. Try again shortly.'},429);
      stage='cache';
      const cacheKey=new Request(url.origin+'/cached-steam-library?profile='+encodeURIComponent(name));
      const cache=globalThis.caches?.default;
      const cached=cache?await cache.match(cacheKey):null;
      if(cached)return respond(await cached.json());
      let id=name;
      if(!/^765\d{14}$/.test(id)) {
        stage='resolve_profile';
        const profile=await steam('ISteamUser/ResolveVanityURL/v1/',{vanityurl:name},env.STEAM_API_KEY);
        id=profile?.steamid;
        if(profile?.success!==1||!/^765\d{14}$/.test(id))return respond({error:'Steam profile not found'},400);
      }
      stage='owned_games';
      const library=await steam('IPlayerService/GetOwnedGames/v1/',{steamid:id,include_appinfo:'1',include_played_free_games:'1',skip_unvetted_apps:'0'},env.STEAM_API_KEY);
      if(!Number.isInteger(library?.game_count))return respond({error:'Steam game details must be public'},400);
      stage='validate_library';
      const rows=library.games||[];
      if(!Array.isArray(rows)||rows.length!==library.game_count||rows.length>10000)throw Error('Incomplete library');
      const games=rows.map(row=>{
        const appid=String(row.appid),title=String(row.name||appid).trim();
        if(!/^\d{1,10}$/.test(appid)||!title||title.length>300)throw Error('Invalid library');
        return {title,source_id:'steam:'+appid};
      });
      const body={games};
      if(cache)ctx.waitUntil(cache.put(cacheKey,new Response(JSON.stringify(body),{headers:{'Content-Type':'application/json','Cache-Control':'public,max-age=300'}})));
      return respond(body);
    }catch (failure) {
      // Never return upstream URLs, exception text, tokens, or headers.
      const body={error:'Steam is temporarily unavailable. Try again later.',code:stage};
      if(['TypeError','ReferenceError','SyntaxError','Error','TimeoutError'].includes(failure?.name))body.kind=failure.name;
      if(['network','invalid_json'].includes(failure?.reason))body.reason=failure.reason;
      if(Number.isInteger(failure?.upstreamStatus))body.upstream_status=failure.upstreamStatus;
      return respond(body,502);
    }
  }
};
