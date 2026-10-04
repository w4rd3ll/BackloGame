'use strict';
const gridDialog=document.createElement('dialog');gridDialog.className='gridDialog';document.body.append(gridDialog);
let gridSession=0;
let gridHoverCleanup=()=>{};
function wireGridHover(dialog){
  const popup=document.createElement('div');popup.className='gridHoverPreview';popup.hidden=true;
  popup.setAttribute('aria-hidden','true');dialog.append(popup);
  const events=new AbortController();let timer=null,active=null;
  function hide(){clearTimeout(timer);timer=null;active=null;popup.hidden=true;popup.replaceChildren();}
  function show(target){
    if(active===target)return;
    hide();active=target;
    timer=setTimeout(()=>{
      if(!dialog.open||!target.isConnected||active!==target)return;
      const width=Number(target.dataset.hoverWidth||target.naturalWidth||600);
      const height=Number(target.dataset.hoverHeight||target.naturalHeight||900);
      const scale=Math.min(1,(innerWidth-32)*.65/width,(innerHeight-32)*.88/height,660/height,820/width);
      const w=Math.max(1,width*scale),h=Math.max(1,height*scale),r=target.getBoundingClientRect();
      const left=r.right+14+w<=innerWidth-16?r.right+14:Math.max(16,r.left-w-14);
      popup.style.left=left+'px';popup.style.top=Math.max(16,Math.min(r.top,innerHeight-h-16))+'px';
      popup.style.width=w+'px';popup.style.height=h+'px';
      const image=document.createElement('img');image.alt='';image.referrerPolicy='no-referrer';
      image.onerror=()=>{if(active===target)hide();};
      image.src=target.dataset.hoverUrl||target.src;popup.replaceChildren(image);popup.hidden=false;
    },250);
  }
  const targetOf=event=>event.target.closest('.gridAsset,#gridPreview img');
  dialog.addEventListener('mouseover',event=>{const target=targetOf(event);if(target&&window.matchMedia('(hover:hover)').matches)show(target);},{signal:events.signal});
  dialog.addEventListener('mouseout',event=>{if(active&&!active.contains(event.relatedTarget))hide();},{signal:events.signal});
  dialog.addEventListener('click',event=>{if(event.target.closest('button,input,select,summary'))hide();},{signal:events.signal});
  dialog.addEventListener('scroll',hide,{signal:events.signal,passive:true});
  window.addEventListener('resize',hide,{signal:events.signal,passive:true});
  dialog.addEventListener('close',hide,{signal:events.signal});
  return ()=>{hide();events.abort();popup.remove();};
}
async function openSteamGrid(game,initialOrientation='portrait'){
  if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}
  if(catalogBatchRunning||coversUpdating){toast(t('Дождись обновления каталога'),true);return;}
  const session=++gridSession;
  gridHoverCleanup();
  let orientation=initialOrientation,target=null,page=0,revision=0,saving=false,assets=[],chosen=null,loading=false,hasMore=false;
  gridDialog.innerHTML=`<div class="dialogHead"><div><h2>${t('Выбрать обложку из каталога')}</h2><p class="hint">${e(game.title)}</p></div><button id="gridClose" aria-label="${t('Закрыть')}">✕</button></div><form id="gridSearch"><input id="gridQuery" value="${e(game.original_title||game.title)}" aria-label="${t('Название игры')}" required maxlength="150"><button>${t('Найти')}</button></form><div id="gridMatches" class="gridMatches"></div><div class="gridTabs"><button data-grid-tab="portrait">${t('Вертикальная')}</button><button data-grid-tab="landscape">${t('Горизонтальная')}</button><button id="gridReset" class="text">${t('Вернуть исходную обложку')}</button></div><p id="gridStatus" class="hint" role="status"></p><div class="gridLayout"><div><nav id="gridPages" class="gridPagination" aria-label="${t('Страницы обложек')}" hidden><button id="gridPrevious">← ${t('Назад')}</button><div id="gridPageNumbers"></div><button id="gridNext">${t('Далее')} →</button></nav><div id="gridAssets" class="gridAssets"></div></div><aside id="gridPreview"><p class="hint">${t('Выбери обложку для предпросмотра')}</p></aside></div><p class="hint">${t('Вертикальная обложка — карточки и описание. Горизонтальная — список. Обе сохраняются на компьютере.')}</p>`;
  gridHoverCleanup=wireGridHover(gridDialog);
  const filters=document.createElement('div');filters.className='gridFilters';
  const choices={nsfw:[['false','Скрыть'],['any','Все'],['true','Только Adult']],humor:[['false','Скрыть'],['any','Все'],['true','Только юмор']],sizes:[['all','Все размеры'],['standard','Стандартные']],style:[['all','Все стили'],['alternate','Альтернативный'],['blurred','Размытый'],['material','Материальный'],['no_logo','Без логотипа'],['white_logo','Белый логотип']],motion:[['static','Статичные'],['animated','Анимированные'],['both','Все']],mime:[['all','Все форматы'],['image/png','PNG'],['image/jpeg','JPEG'],['image/webp','WebP']],epilepsy:[['false','Скрыть'],['any','Все'],['true','Только мигающие']]};
  const filterSelect=(key,label)=>`<label><span>${t(label)}</span><select data-grid-filter="${key}" aria-label="${t(label)}">${choices[key].map(([value,text])=>`<option value="${value}">${t(text)}</option>`).join('')}</select></label>`;
  filters.innerHTML=`<details class="gridContentFilter"><summary>${t('Содержимое')}</summary><div class="gridFilterPopover gridContentChoices">${[['standard','Стандартные'],['adult','Adult'],['humor','Юмор']].map(([value,label])=>`<label class="check"><input type="checkbox" data-grid-content="${value}">${t(label)}</label>`).join('')}</div></details>`+filterSelect('sizes','Размеры')+`<details class="gridExtraFilters"><summary>${t('Фильтры')}</summary><div class="gridFilterPopover">${filterSelect('style','Стиль')}${filterSelect('motion','Анимация')}${filterSelect('mime','Формат файла')}${filterSelect('epilepsy','Мигающие изображения')}<small>${t('Сохраняется для всех игр')}</small></div></details>`;
  gridDialog.querySelector('.gridTabs').append(filters);
  const filterDefaults={content:['standard'],sizes:'all',style:'all',motion:'static',mime:'all',epilepsy:'false'};
  function restoreFilters(){const saved={...filterDefaults,...preferences.steamgriddb_filters};filters.querySelectorAll('select').forEach(select=>select.value=saved[select.dataset.gridFilter]);filters.querySelectorAll('[data-grid-content]').forEach(input=>input.checked=saved.content.includes(input.dataset.gridContent));filters.querySelector('.gridContentFilter summary').textContent=t('Содержимое')+' · '+saved.content.length;}
  restoreFilters();
  filters.querySelectorAll('select,[data-grid-content]').forEach(select=>select.onchange=async()=>{
    const values={...Object.fromEntries([...filters.querySelectorAll('select')].map(control=>[control.dataset.gridFilter,control.value])),content:[...filters.querySelectorAll('[data-grid-content]:checked')].map(input=>input.dataset.gridContent)};
    lock(true);
    try{preferences=await api('/api/settings',{steamgriddb_filters:values});restoreFilters();lock(false);if(target)await load();else $('gridStatus').textContent=t('Фильтры сохранены для всех игр');}
    catch(err){restoreFilters();$('gridStatus').textContent=t(err.message);}
    finally{lock(false);}
  });
  const close=()=>{if(!saving){revision++;gridDialog.close();}};
  const provider=document.createElement('select');provider.id='gridProvider';provider.setAttribute('aria-label',t('Источник'));
  provider.innerHTML='<option value="steamgriddb">SteamGridDB</option><option value="metacritic">Metacritic</option><option value="steam">Steam</option><option value="wikipedia">Wikipedia / Wikidata</option>';
  $('gridSearch').insertBefore(provider,$('gridSearch').querySelector('button'));
  provider.onchange=()=>{if(!saving){const next=provider.value;close();openCatalogUpdate(game,'cover',next,orientation);}};
  $('gridClose').onclick=close;gridDialog.oncancel=event=>{if(saving)event.preventDefault();else revision++;};
  gridDialog.onclick=event=>{if(event.target===gridDialog){const r=gridDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}};
  function tabs(){
    gridDialog.querySelectorAll('[data-grid-tab]').forEach(button=>{button.classList.toggle('primary',button.dataset.gridTab===orientation);button.setAttribute('aria-pressed',String(button.dataset.gridTab===orientation));});
    $('gridAssets').dataset.orientation=orientation;
    $('gridReset').disabled=!games.find(g=>g.id===game.id)?.custom_covers?.[orientation];
  }
  function lock(value){saving=value;if(value){revision++;loading=false;}gridDialog.querySelectorAll('button,input,select').forEach(x=>x.disabled=value);if(!value){tabs();pagination();}}
  async function applyCover(row){
    if(saving||loading||!row)return;
    lock(true);
    try{await api('/api/steamgriddb/apply',{id:game.id,gallery:row.gallery,asset:row.id});await reload();renderInspector();$('gridStatus').textContent=t('Обложка сохранена');toast(t('Обложка сохранена'));}
    catch(err){$('gridStatus').textContent=t(err.message);}
    finally{lock(false);}
  }
  function draw(){
    $('gridAssets').innerHTML=assets.map((row,i)=>`<button class="gridAsset ${chosen===row?'selected':''}" data-grid-asset="${i}" data-hover-url="${e(row.url)}" data-hover-width="${row.width}" data-hover-height="${row.height}" aria-label="${e(row.author+' · '+row.width+' × '+row.height)}"><img src="${e(row.thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer"><small>${row.width} × ${row.height}</small></button>`).join('');
    $('gridAssets').querySelectorAll('[data-grid-asset]').forEach(button=>{
      const row=assets[Number(button.dataset.gridAsset)];
      button.ondblclick=()=>applyCover(row);
      button.onclick=()=>{
      chosen=assets[Number(button.dataset.gridAsset)];
      $('gridAssets').querySelector('.selected')?.classList.remove('selected');
      button.classList.add('selected');
      $('gridPreview').innerHTML=`<button id="gridUse" class="primary">${t('Использовать обложку')}</button><p>${e(chosen.author)} · ${chosen.width} × ${chosen.height}</p><img src="${e(chosen.url)}" alt="${t('Предпросмотр')}" referrerpolicy="no-referrer">`;
      $('gridUse').onclick=()=>applyCover(row);
      $('gridPreview').querySelector('img').ondblclick=()=>applyCover(row);
      };
    });
  }
  function pagination(){
    $('gridPages').hidden=!target;
    $('gridPrevious').disabled=saving||loading||page===0;
    $('gridNext').disabled=saving||loading||!hasMore||page>=100;
    const numbers=[...new Set([0,Math.max(0,page-1),page,...(hasMore&&page<100?[page+1]:[])])];
    $('gridPageNumbers').innerHTML=numbers.map(number=>`<button data-grid-page="${number}" class="${number===page?'primary':''}" ${saving||loading?'disabled':''} ${number===page?'aria-current="page"':''}>${number+1}</button>`).join('');
    $('gridPageNumbers').querySelectorAll('button').forEach(button=>button.onclick=()=>load(Number(button.dataset.gridPage)));
  }
  async function load(nextPage=0){
    if(!target)return;
    const request=++revision;loading=true;assets=[];chosen=null;draw();pagination();
    $('gridPreview').innerHTML=`<p class="hint">${t('Выбери обложку для предпросмотра')}</p>`;
    $('gridAssets').setAttribute('aria-busy','true');
    $('gridStatus').textContent=t('Загружаем обложки…');tabs();
    try{
      const result=await api('/api/steamgriddb/grids',{...target,orientation,page:nextPage});if(request!==revision||session!==gridSession||!gridDialog.open)return;
      page=nextPage;hasMore=result.more;assets=result.items.map(row=>({...row,gallery:result.gallery}));chosen=null;draw();
      $('gridPreview').innerHTML=`<p class="hint">${t('Выбери обложку для предпросмотра')}</p>`;
      $('gridStatus').textContent=`${t('Страница')} ${page+1} · `+(assets.length?`${t('Обложки:')} ${assets.length}`:t('Обложки не найдены. Попробуй поиск по названию.'));
      gridDialog.scrollTop=0;
    }catch(err){if(request===revision&&session===gridSession)$('gridStatus').textContent=t(err.message);}
    finally{if(request===revision&&session===gridSession){loading=false;$('gridAssets').setAttribute('aria-busy','false');pagination();}}
  }
  async function search(){
    const request=++revision;target=null;page=0;hasMore=false;loading=false;assets=[];chosen=null;draw();$('gridAssets').setAttribute('aria-busy','false');$('gridPages').hidden=true;$('gridPreview').textContent='';$('gridMatches').textContent='';$('gridStatus').textContent=t('Ищем в каталоге…');
    try{
      const result=await api('/api/steamgriddb/search',{query:$('gridQuery').value});if(request!==revision||session!==gridSession||!gridDialog.open)return;
      $('gridMatches').innerHTML=result.items.map((row,i)=>`<button data-grid-match="${i}">${e(row.title)}</button>`).join('');
      $('gridStatus').textContent=result.items.length?t('Выбери соответствующую игру'):t('Ничего не найдено');
      $('gridMatches').querySelectorAll('[data-grid-match]').forEach(button=>button.onclick=()=>{target={kind:'game',game:result.items[Number(button.dataset.gridMatch)].id};$('gridMatches').querySelectorAll('button').forEach(b=>b.classList.toggle('primary',b===button));load();});
    }catch(err){if(request===revision&&session===gridSession)$('gridStatus').textContent=t(err.message);}
  }
  $('gridSearch').onsubmit=event=>{event.preventDefault();if(!saving)search();};
  gridDialog.querySelectorAll('[data-grid-tab]').forEach(button=>button.onclick=()=>{orientation=button.dataset.gridTab;tabs();load();});
  $('gridPrevious').onclick=()=>{if(page>0&&!loading)load(page-1);};
  $('gridNext').onclick=()=>{if(hasMore&&!loading)load(page+1);};
  $('gridReset').onclick=async()=>{
    lock(true);
    try{await api('/api/steamgriddb/reset',{id:game.id,orientation});await reload();renderInspector();$('gridStatus').textContent=t('Исходная обложка восстановлена');}
    catch(err){$('gridStatus').textContent=t(err.message);}
    finally{lock(false);}
  };
  tabs();gridDialog.showModal();
  const steam=steamSource(game);
  if(steam){target={kind:'steam',game:Number(steam.split(':')[1])};await load();}else await search();
}
document.addEventListener('contextmenu',event=>{
  const row=event.target.closest('.game'),image=event.target.closest('[data-cover-id]');
  const game=games.find(g=>g.id===Number(row?.dataset.id||image?.dataset.coverId));if(!game)return;
  event.preventDefault();const menu=row?quickMenu:$('coverMenu');menu.hidden=false;
  if(!row){menuGame=game;$('chooseThumbnail').hidden=!cropArtwork(game).src;$('resetThumbnail').hidden=!game.thumbnail_crop;}
  menu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-menu.offsetHeight-8))+'px';
  menu.style.left=Math.max(8,Math.min(event.clientX,innerWidth-menu.offsetWidth-8))+'px';
});
const settingsBeforeGrid=renderSettings;
renderSettings=function(){
  settingsBeforeGrid();const panel=document.createElement('section');panel.className='gridSettings';
  panel.innerHTML=`<h3>SteamGridDB</h3><p id="gridKeyStatus" class="hint"></p><form id="gridKeyForm"><input id="gridKey" type="password" autocomplete="new-password" placeholder="API key" aria-label="SteamGridDB API key" minlength="16" maxlength="128" required><button>${t('Сохранить ключ')}</button><button id="gridKeyRemove" type="button">${t('Удалить ключ')}</button></form><details><summary>${t('Инструкция')}</summary><ol><li>${t('Войди на SteamGridDB через свой аккаунт Steam.')}</li><li><a href="https://www.steamgriddb.com/profile/preferences/api" target="_blank" rel="noopener noreferrer">${t('Открой Preferences → API и создай API-ключ.')}</a></li><li>${t('Вставь ключ в поле выше и нажми «Сохранить ключ».')}</li><li>${t('ПКМ по игре → Выбрать обложку из каталога → SteamGridDB. Выбери отдельно вертикальную и горизонтальную обложку.')}</li></ol><p class="hint">${t('Ключ хранится только в личной папке данных. Он не включается в экспорт библиотеки и резервные копии.')}</p></details>`;
  $('steamSourcePanel').append(panel);
  const sizeLabel=document.createElement('label');sizeLabel.className='coverSizeSetting';
  sizeLabel.innerHTML=`${t('Максимальный размер обложки')}<select id="coverMaxSize" aria-label="${t('Максимальный размер обложки')}">${[12,32,64,128].map(size=>`<option value="${size}" ${size===(preferences.cover_max_mb||64)?'selected':''}>${size} ${t('МБ')}</option>`).join('')}</select>`;
  $('cacheAllCovers').closest('.settingsSection').insertBefore(sizeLabel,$('cacheAllCovers').closest('.settingsRow'));
  $('coverMaxSize').onchange=async event=>{const control=event.target;control.disabled=true;try{preferences=await api('/api/settings',{cover_max_mb:Number(control.value)});toast(t('Сохранено'));}catch(err){control.value=preferences.cover_max_mb||64;toast(t(err.message),true);}finally{control.disabled=false;}};
  function status(result){if(panel.isConnected){panel.querySelector('#gridKeyStatus').textContent=t(result.configured?'Ключ сохранён':'Ключ не задан');panel.querySelector('#gridKeyRemove').disabled=!result.configured;}}
  api('/api/steamgriddb/status',{}).then(status).catch(err=>{if(panel.isConnected)panel.querySelector('#gridKeyStatus').textContent=t(err.message);});
  $('gridKeyForm').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{const result=await api('/api/steamgriddb/key',{key:$('gridKey').value});$('gridKey').value='';status(result);});};
  $('gridKeyRemove').onclick=event=>busy(event.currentTarget,async()=>{status(await api('/api/steamgriddb/key',{key:''}));$('gridKey').value='';});
};
