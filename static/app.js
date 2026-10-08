'use strict';
const $ = id => document.getElementById(id);
function wireDialogBackdrop(dialog, close) {
  let pressedOutside = false;
  const outside = event => {
    const r = dialog.getBoundingClientRect();
    return event.target === dialog && (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom);
  };
  dialog.onpointerdown = event => { pressedOutside = event.button === 0 && outside(event); };
  dialog.onpointercancel = () => { pressedOutside = false; };
  dialog.onclick = event => {
    const dismiss = pressedOutside && event.button === 0 && outside(event);
    pressedOutside = false;
    if (dismiss) close();
  };
}
const librarySearchCache = new WeakMap();
function normalizeLibrarySearch(value) {
  return String(value || '').normalize('NFKD').toLocaleLowerCase().replace(/ё/g,'е').replace(/[\u0300-\u036f]/g,'').replace(/[’‘`']/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
}
function librarySearchTerms(query) {
  return [...String(query).matchAll(/(-?)"([^"]+)"|(-?)([^\s"]+)/g)].map(m=>({exclude:!!(m[1]||m[3]),value:normalizeLibrarySearch(m[2]||m[4])})).filter(term=>term.value);
}
function matchesLibrarySearch(game, terms) {
  const raw = [game.title,game.original_title,game.notes,game.tags,game.series,game.platform,game.genre,game.developer].join(' ');
  let entry = librarySearchCache.get(game);
  if (!entry || entry.raw !== raw) { entry={raw,text:normalizeLibrarySearch(raw)}; librarySearchCache.set(game,entry); }
  return terms.every(term=>term.exclude ? !entry.text.includes(term.value) : entry.text.includes(term.value));
}

let statuses = ['Хочу пройти', 'Играю', 'Перепрохожу', 'Пройдено', 'Отложено', 'Брошено'];
const icons = ['◈', '◷', '▷', '✓', 'Ⅱ', '×'];
let games = [], token = '', selectedId = null, statusFilter = '', direction = -1, viewMode = 'cards';
let catalogSerial = 0, toastTimer, dirty = false;
let savedPlatforms = [];
let preferences = {hidden_categories:[],show_card_notes:true,default_category:'Хочу пройти',language:'en'};
let draggingId = null, savingOrder = false;
let sidebarCollapsed=false, inspectorCollapsed=false;
function availablePlatforms() {
  const unique = new Map();
  ['Пока неизвестно',...savedPlatforms,...games.map(g=>g.platform)].filter(Boolean).forEach(p=>{const value=p.trim();if(!unique.has(value.toLocaleLowerCase()))unique.set(value.toLocaleLowerCase(),value);});
  return [...unique.values()].sort((a,b)=>a.localeCompare(b,'ru'));
}
function platformControl(value) {
  return `<select id="platformChoice" aria-label="${t("Выбрать платформу")}">${availablePlatforms().map(p=>`<option value="${e(p)}" ${p.toLocaleLowerCase()===value.toLocaleLowerCase()?'selected':''}>${e(displayValue(p))}</option>`).join('')}<option value="__custom__">${t("＋ Своя платформа…")}</option></select><input id="platformInput" name="platform" value="${e(value)}" list="platformOptions" placeholder="${t("Название новой платформы")}" hidden>`;
}
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const e = escapeHTML;
function toast(message, error = false) { $('toast').textContent = message; $('toast').className = error ? 'error' : ''; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, error ? 8500 : 4500); }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Library-Token':token}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(t(result.error) || t("Ошибка запроса"));
  return result;
}
async function busy(button, action) {
  const text = button.textContent; button.disabled = true; button.textContent = t("Подождите…");
  try { return await action(); } catch (err) { toast(err.message, true); } finally { button.disabled = false; button.textContent = text; }
}
const dateText = value => !value ? t("Не указана") : value.length <= 7 ? value : new Date(value.length === 10 ? value + 'T12:00:00' : value).toLocaleDateString(uiLanguage==='ru'?'ru-RU':'en-US');
const localDay = value => { const d = new Date(value); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const parts = value => String(value || '').split(',').map(x => x.trim()).filter(Boolean);
const seriesParts = value => [...new Set(String(value || '').split(';').map(x => x.trim()).filter(Boolean))];
const libraryCollator = new Intl.Collator('ru',{numeric:true,sensitivity:'base'});
const libraryTitleCollator = new Intl.Collator('en',{numeric:true,sensitivity:'base'});
const hasNoSeries = value => !seriesParts(value).some(series => series !== 'Без серии');
function descriptionPreview(text) {
  if(text.length<=420)return text;
  const paragraph=text.split(/\n\s*\n/)[0].trim();
  if(paragraph.length>=180&&paragraph.length<=420)return paragraph;
  const start=text.slice(0,420);
  const sentence=Math.max(start.lastIndexOf('. '),start.lastIndexOf('! '),start.lastIndexOf('? '));
  if(sentence>=220)return start.slice(0,sentence+1);
  const space=start.lastIndexOf(' ');
  return start.slice(0,space>300?space:420).trimEnd()+'…';
}
const coverSource=(game,orientation='portrait')=>game.custom_covers?.[orientation]?.local||game.custom_covers?.[orientation]?.url||game.image_local||game.image;
const cropArtwork=game=>game.custom_covers?.portrait?{image:game.custom_covers.portrait.url,src:coverSource(game)}:{image:game.image,src:game.image_local||game.image};
function thumbnailSource(game){
  const image=game.thumbnail_crop?.image;if(!image)return '';
  for(const cover of Object.values(game.custom_covers||{}))if(cover.url===image)return cover.local||cover.url;
  return image===game.image?game.image_local||game.image:'';
}
function croppedCover(image,crop,cls='cover',id='') {
  return `<div class="${cls} thumbnailCrop" ${id?`data-cover-id="${id}"`:''}><img src="${e(image)}" alt="" draggable="false" referrerpolicy="no-referrer" data-crop-width="${crop.width}" data-crop-height="${crop.height}" data-crop-x="${crop.x}" data-crop-y="${crop.y}"></div>`;
}
function cover(game, cls = 'cover') {
  const orientation=cls==='cover'&&viewMode!=='cards'?'landscape':'portrait',src=coverSource(game,orientation);
  if(cls==='cover'&&viewMode!=='cards'&&thumbnailSource(game))return croppedCover(thumbnailSource(game),game.thumbnail_crop,cls,game.id);
  if(!src)return '<div class="coverFallback">✦</div>';
  if(cls==='cover'&&viewMode==='cards')return `<div class="cardArtwork" data-cover-id="${game.id}"><img class="cardBackdrop" src="${e(src)}" alt="" loading="lazy" draggable="false" referrerpolicy="no-referrer" aria-hidden="true"><img class="cover" src="${e(src)}" alt="" loading="lazy" draggable="false" referrerpolicy="no-referrer"></div>`;
  return `<img class="${cls}" data-cover-id="${game.id}" src="${e(src)}" alt="" loading="lazy" draggable="false" referrerpolicy="no-referrer" ${cls==='detailImage'?t("tabindex=\"0\" title=\"Правый клик — выбрать миниатюру\""):''}>`;
}
function wireImages(root) { root.querySelectorAll('img').forEach(img => {
  if(img.dataset.cropWidth){const {cropWidth:w,cropHeight:h,cropX:x,cropY:y}=img.dataset;Object.assign(img.style,{width:100/w+'%',height:100/h+'%',left:-100*x/w+'%',top:-100*y/h+'%'});}
  img.addEventListener('error', () => { if(img.classList.contains('cardBackdrop')){img.remove();return;}const placeholder = document.createElement('div'); placeholder.className = 'coverFallback'; placeholder.textContent = '✦'; img.replaceWith(placeholder); }, {once:true});
}); }
function steamSource(game){return [game.source_id,...(game.source_aliases||[])].find(x=>/^steam:\d+$/.test(x||''))||'';}
function gameResources(game) {
  const title = game.original_title || game.title;
  const appid = /^steam:(\d+)$/.exec(steamSource(game))?.[1];
  let wikipedia = `https://${uiLanguage}.wikipedia.org/w/index.php?search=` + encodeURIComponent(title);
  for (const value of [game.description_url, game.source_url]) {
    try { const url = new URL(value); if(url.protocol==='https:' && /^(?:[a-z-]+\.)?wikipedia\.org$/.test(url.hostname)) { wikipedia=url.href;break; } } catch {}
  }
  return [
    {label: appid ? 'Открыть игру в Steam' : 'Найти игру в Steam', url: appid ? `https://store.steampowered.com/app/${appid}/` : 'https://store.steampowered.com/search/?term=' + encodeURIComponent(title), icon:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="16" cy="7" r="5"/><circle cx="16" cy="7" r="2.7"/><circle cx="7" cy="17" r="3.5"/><path d="M9 14l4-4M10 17l6-5M1 13l7 3"/></svg>', cls:'steamResource'},
    {label: wikipedia.includes('?search=') ? 'Найти в Wikipedia' : 'Открыть статью в Wikipedia', url:wikipedia, icon:'<span aria-hidden="true">W</span>', cls:'wikiResource'},
    {label:'Найти на RuTracker', url:'https://rutracker.org/forum/tracker.php?nm=' + encodeURIComponent(title), icon:'<img src="/rutracker-icon.png" alt="" width="21" height="21">', cls:'rutrackerResource'}
  ];
}
function resourceButtons(game) {
  return '<div class="gameResources">' + gameResources(game).map(x=>`<a class="resourceIcon ${x.cls}" href="${e(x.url)}" title="${e(t(x.label))}" aria-label="${e(t(x.label))}" target="_blank" rel="noopener noreferrer">${x.icon}</a>`).join('') + '</div>';
}
function fillOptions(id, values, title, last = '') {
  const select = $(id), previous = select.value;
  if(previous && previous!==last && !values.includes(previous))values=[...values,previous];
  select.innerHTML = `<option value="">${title}</option>` + [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b,'ru')).map(x => `<option value="${e(x)}">${e(id==='platformFilter'?displayValue(x):x)}</option>`).join('');
  if(last)select.innerHTML+=`<option value="${e(last)}">${e(displayValue(last))}</option>`;
  select.value = previous;
}
function rebuildOptions() {
  $('platformOptions').innerHTML = availablePlatforms().map(p=>`<option value="${e(p)}"></option>`).join('');
  fillOptions('platformFilter', games.map(g => g.platform || 'Пока неизвестно'), t("Все платформы"));
  fillOptions('genreFilter', games.flatMap(g => parts(g.genre)), t("Все жанры"));
  fillOptions('seriesFilter', games.flatMap(g => seriesParts(g.series)).filter(series=>series!=='Без серии'), t("Все серии"), 'Без серии');
  fillOptions('tagFilter', games.flatMap(g => parts(g.tags)), t("Все теги"));
}
function dateBound(value, upper = false) {
  value = value.trim();
  if (/^\d{4}$/.test(value)) return value + (upper ? '-12-31' : '-01-01');
  if (/^\d{4}-\d{2}$/.test(value)) { const [y,m] = value.split('-').map(Number); return value + (upper ? '-' + String(new Date(y,m,0).getDate()).padStart(2,'0') : '-01'); }
  return value;
}
function filteredGames() {
  const query = librarySearchTerms($('librarySearch').value);
  const from = dateBound($('releaseFrom').value), to = dateBound($('releaseTo').value, true);
  const result = games.filter(g => {
    if (statusFilter === 'favorites' ? !g.favorite : statusFilter === 'not-favorites' ? !!g.favorite : statusFilter && g.status !== statusFilter) return false;
    if (query.length && !matchesLibrarySearch(g,query)) return false;
    if ($('platformFilter').value && (g.platform || 'Пока неизвестно') !== $('platformFilter').value) return false;
    if ($('genreFilter').value && !parts(g.genre).includes($('genreFilter').value)) return false;
    if ($('seriesFilter').value && ($('seriesFilter').value==='Без серии'?!hasNoSeries(g.series):!seriesParts(g.series).includes($('seriesFilter').value))) return false;
    if ($('tagFilter').value && !parts(g.tags).includes($('tagFilter').value)) return false;
    if ($('priorityFilter').value && (g.priority || 'Обычный') !== $('priorityFilter').value) return false;
    if ($('unknownRelease').checked && g.release_date) return false;
    if (from && (!g.release_date || dateBound(g.release_date,true) < from)) return false;
    if (to && (!g.release_date || dateBound(g.release_date) > to)) return false;
    const added = localDay(g.added_at);
    if ($('addedFrom').value && added < $('addedFrom').value) return false;
    if ($('addedTo').value && added > $('addedTo').value) return false;
    return true;
  });
  const field = $('sortField').value;
  result.sort((a,b) => {
    if (field === 'manual_order') return (a.manual_order || a.id) - (b.manual_order || b.id);
    let av = a[field] || '', bv = b[field] || '';
    if (field === 'priority') { const rank = {'Низкий':1,'Обычный':2,'Высокий':3}; av = rank[av || 'Обычный']; bv = rank[bv || 'Обычный']; }
    if (field === 'status') { av = statuses.indexOf(av) + 1; bv = statuses.indexOf(bv) + 1; }
    if (!av && bv) return 1; if (av && !bv) return -1;
    const comparison = typeof av === 'number' ? av - bv : (field==='title'?libraryTitleCollator:libraryCollator).compare(String(av),String(bv));
    return comparison * direction || libraryTitleCollator.compare(a.title,b.title);
  });
  return result;
}
function gameContent(g){
  if(viewMode==='compact')return `${cover(g)}<span class="compactTitle" title="${e(g.title)}">${e(g.title)}</span><span class="compactPlatform" title="${e(displayValue(g.platform||'Пока неизвестно'))}">${e(displayValue(g.platform||'Пока неизвестно'))}</span><span class="compactStatus status ${g.status==='Играю'?'playing':g.status==='Пройдено'?'done':''}" title="${e(displayValue(g.status))}">${e(displayValue(g.status))}</span>`;
  const clean=value=>String(value||'').trim()&&!/^[\s\-–—]+$/.test(value)?String(value).trim():'';
  const mode=preferences.card_details||'both';
  const note=preferences.show_card_notes?[...(mode!=='series'?[clean(g.notes)]:[]),...(mode!=='notes'?[clean(g.series)]:[])].filter(Boolean).join(' · '):'';
  return `${cover(g)}<div class="gameBody ${note?'hasCardDetails':'noCardDetails'}"><h3>${e(g.title)}</h3><div class="chips">${g.favorite&&viewMode!=='cards'?`<span class="chip favoriteMark">${t("★ Избранное")}</span>`:''}<span class="chip">${e(displayValue(g.platform || 'Пока неизвестно'))}</span>${g.priority==='Высокий'?`<span class="chip">${t("★ В приоритете")}</span>`:''}</div><span class="status ${g.status==='Играю'?'playing':g.status==='Пройдено'?'done':''}">○ ${e(displayValue(g.status))}</span>${note?`<p class="note">${e(note)}</p>`:''}<div class="meta">${t("Выход:")} ${e(dateText(g.release_date) === t("Не указана") ? g.release_label || t("Не указана") : dateText(g.release_date))} ${t("· Добавлено")} ${e(dateText(g.added_at))}</div></div>`;
}
function render() {
  applyPanels();
  if(preferences.hidden_categories.includes(statusFilter)) statusFilter='';
  $('statusNav').innerHTML = ['',...statuses].map((status,i) => `<button class="${statusFilter===status?'active':''}" data-status="${e(status)}"><span>${({'':'◈','Хочу пройти':'◷','Бэклог':'◷','Играю':'▷','Перепрохожу':'↻','Пройдено':'✓','Отложено':'Ⅱ','Брошено':'×'})[status]||'○'} &nbsp; ${e(status?displayValue(status):t('Все игры'))}</span><span class="badge">${games.filter(g => !status || g.status===status).length}</span></button>`).join('') + `<button class="${statusFilter==='favorites'?'active':''}" data-status="favorites"><span>${t("★ &nbsp; Избранное")}</span><span class="badge">${games.filter(g=>g.favorite).length}</span></button><button class="${statusFilter==='not-favorites'?'active':''}" data-status="not-favorites"><span>${t("☆ &nbsp; Не в избранном")}</span><span class="badge">${games.filter(g=>!g.favorite).length}</span></button>`;
  $('statusNav').querySelectorAll('button').forEach(b => b.onclick = () => { statusFilter=b.dataset.status; render(); persistView(); });
  $('statusNav').querySelectorAll('button').forEach(b=>{b.hidden=preferences.hidden_categories.includes(b.dataset.status);});
  if(preferences.hidden_categories.includes(statusFilter)) statusFilter='';
  const visible = filteredGames();
  $('viewTitle').textContent = statusFilter === 'favorites' ? t("Избранное") : statusFilter === 'not-favorites' ? t("Не в избранном") : statusFilter ? displayValue(statusFilter) : t("Все игры");
  $('count').textContent = `${visible.length} ${t("из")} ${games.length} ${t("в библиотеке")}`;
  $('games').className = viewMode==='compact'?'cards list compact':viewMode==='list'?'cards list':'cards';
  $('viewToggle').value=viewMode;
  $('games').innerHTML = visible.map(g => `<div role="button" tabindex="0" class="game ${g.id===selectedId?'selected':''}" data-id="${g.id}">${gameContent(g)}</div>`).join('');
  $('games').querySelectorAll('.game').forEach(b => {
    b.onclick = event => {if(event.target.closest('input,button'))return;if(!draggingId&&!savingOrder)selectGame(Number(b.dataset.id));};
    b.draggable = $('sortField').value === 'manual_order';
    b.classList.toggle('canDrag',b.draggable);
    b.ondragstart=event=>{if(savingOrder||$('sortField').value!=='manual_order'){event.preventDefault();return;}draggingId=Number(b.dataset.id);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',String(draggingId));b.classList.add('dragging');};
    b.ondragover=event=>{if(!draggingId||draggingId===Number(b.dataset.id))return;event.preventDefault();event.dataTransfer.dropEffect='move';const rect=b.getBoundingClientRect();const after=viewMode!=='cards'?event.clientY>rect.top+rect.height/2:event.clientX>rect.left+rect.width/2;b.dataset.dropAfter=String(after);document.querySelectorAll('.dropBefore,.dropAfter').forEach(x=>x.classList.remove('dropBefore','dropAfter'));b.classList.add(after?'dropAfter':'dropBefore');};
    b.ondrop=async event=>{event.preventDefault();const id=draggingId,target=Number(b.dataset.id),after=b.dataset.dropAfter==='true';draggingId=null;if(!id||id===target||savingOrder)return;savingOrder=true;try{await api('/api/reorder',{id,target,after});await reload();toast(t("Ручной порядок сохранён"));}catch(err){toast(err.message,true);render();}finally{savingOrder=false;}};
    b.ondragend=()=>{draggingId=null;document.querySelectorAll('.dragging,.dropBefore,.dropAfter').forEach(x=>x.classList.remove('dragging','dropBefore','dropAfter'));};
  });
  $('games').classList.toggle('withoutNotes',!preferences.show_card_notes);
  wireImages($('games'));
  $('empty').hidden = visible.length !== 0;
  if (!visible.length) { $('empty').querySelector('h2').textContent = games.length ? t("Ничего не найдено") : t("Здесь начинается твой список"); $('empty').querySelector('p').innerHTML = games.length ? t("Попробуй изменить фильтры или поисковый запрос.") : `${t("Найди игру по названию или добавь её вручную.")}<br>${t("Обложка, описание и другие части серии — в одном месте.")}`; $('emptyAdd').textContent = games.length ? t("＋ Добавить игру") : t("＋ Добавить первую игру"); }
  const active = ['platformFilter','genreFilter','seriesFilter','tagFilter','priorityFilter','releaseFrom','releaseTo','addedFrom','addedTo'].filter(id => $(id).value).length + Number($('unknownRelease').checked);
  $('activeFilters').textContent = active ? `${t("Фильтров:")} ${active}` : '';
  $('sortDirection').textContent = direction === 1 ? t("↑ По возрастанию") : t("↓ По убыванию");
  $('sortDirection').hidden=$('sortField').value==='manual_order';
  $('manualHint').hidden=$('sortField').value!=='manual_order';
}
function persistView() { try { localStorage.setItem('myGamesView',JSON.stringify({statusFilter,direction,viewMode,sidebarCollapsed,inspectorCollapsed,sort:$('sortField').value})); } catch {} }
function restoreView() { try { const v=JSON.parse(localStorage.getItem('myGamesView')||'{}'); statusFilter=[...statuses,'favorites','not-favorites'].includes(v.statusFilter)?v.statusFilter:''; direction=v.direction===1?1:-1;viewMode=['cards','list','compact'].includes(v.viewMode)?v.viewMode:v.listView?'list':'cards';sidebarCollapsed=v.sidebarCollapsed===true;inspectorCollapsed=v.inspectorCollapsed===true; if ([...$('sortField').options].some(o=>o.value===v.sort)) $('sortField').value=v.sort; } catch {} }
async function reload() { const result=await api('/api/library'); games=result.games; savedPlatforms=result.platforms||[]; statuses=result.categories||statuses; preferences=result.settings||preferences;applyLanguage(preferences.language);applyTheme(preferences.theme);token=result.token; rebuildOptions(); render(); }
function selectGame(id, force=false) {
  if (dirty && !force && !confirm(t("Изменения в карточке ещё не сохранены. Перейти к другой игре?"))) return;
  if(id!=null&&inspectorCollapsed){inspectorCollapsed=false;persistView();}
  selectedId=id; dirty=false; applyPanels();
  $('games').querySelectorAll('.game.selected').forEach(row=>row.classList.remove('selected'));
  if(id!=null)$('games').querySelector(`[data-id="${Number(id)}"]`)?.classList.add('selected');
  renderInspector();
}
function renderInspector() {
  const g=games.find(g=>g.id===selectedId); if(!g) { $('inspector').innerHTML=`<div class="inspectorEmpty"><span>◈</span><h2>${t("Каждая игра — своя история")}</h2><p>${t("Выбери игру, чтобы открыть её карточку.")}</p></div>`; return; }
  const description=g.description || t("Описание пока не добавлено. Его можно получить из каталога или написать ниже.");
  const preview=descriptionPreview(description);
  $('inspector').innerHTML=`<div class="detailTitle"><h2>${e(g.title)}</h2><button id="closeInspector" aria-label="${t("Свернуть правую панель")}">✕</button></div><div class="hint">${e(g.genre || t("Жанр не указан"))}${g.developer?' · '+e(g.developer):''}</div>${cover(g,'detailImage')}<div class="detailSource">${(g.description_url||g.source_url)?`<a href="${e(g.description_url||g.source_url)}" target="_blank" rel="noopener noreferrer">${t("Открыть источник ↗")}</a>`:t("Добавлено вручную")}${g.source_id?`<button id="refreshMetadata" class="text">${t("Обновить сведения")}</button>`:''}</div><div class="descriptionHead"><h3>${t("Описание")}</h3>${resourceButtons(g)}</div><p id="gameDescription" class="description">${e(preview)}</p>${preview!==description?`<button id="expandDescription" class="text descriptionToggle" aria-expanded="false" aria-controls="gameDescription">${t("Показать полностью")}</button>`:''}<button id="favoriteButton" class="favoriteButton ${g.favorite?'isFavorite':''}" aria-pressed="${!!g.favorite}">${g.favorite?t("★ В избранном"):t("☆ В избранное")}</button><form id="detailForm"><div class="formGrid"><label>${t("Статус")}<select name="status">${statuses.map(s=>`<option value="${e(s)}" ${s===g.status?'selected':''}>${e(displayValue(s))}</option>`).join('')}</select></label><label>${t("Платформа")}${platformControl(g.platform || 'Пока неизвестно')}</label><label>${t("Дата выхода")}<input name="release_date" value="${e(g.release_date)}" placeholder="${t("ГГГГ-ММ-ДД")}"></label><label>${t("Приоритет")}<select name="priority">${['Высокий','Обычный','Низкий'].map(s=>`<option value="${e(s)}" ${s===(g.priority||'Обычный')?'selected':''}>${e(displayValue(s))}</option>`).join('')}</select></label><label class="full">${t("Теги, через запятую")}<input name="tags" value="${e(g.tags)}" placeholder="${t("На потом, С друзьями…")}"></label><label class="full">${t("Моя заметка")}<textarea name="notes" rows="3" placeholder="${t("Что хочется запомнить?")}">${e(g.notes)}</textarea></label></div><details class="extraFields"><summary>${t("Редактировать сведения")}</summary><div class="formGrid"><label class="full">${t("Название")}<input name="title" value="${e(g.title)}" required maxlength="300"></label><label class="full">${t("Серии, через ;")}<input name="series" value="${e(g.series)}" placeholder="Half-Life; Portal" aria-label="${t("Серии, через ;")}" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="seriesSuggestions"><div id="seriesSuggestions" role="listbox" hidden></div></label><label class="full">${t("Жанры, через запятую")}<input name="genre" value="${e(g.genre)}"></label><label class="full">${t("Описание")}<textarea name="description" rows="3">${e(g.description)}</textarea></label><label class="full">${t("Ссылка на обложку")}<input name="image" type="url" value="${e(g.image)}" placeholder="https://…"></label></div></details><div class="detailActions"><button class="primary" type="submit">${t("Сохранить")}</button><button type="button" id="deleteGame" class="danger">${t("Удалить")}</button></div></form><p class="hint">${t("Добавлено")} ${e(dateText(g.added_at))}</p>`;
  wireImages($('inspector'));
  wireSeriesSuggestions();
  if($('expandDescription'))$('expandDescription').onclick=()=>{const button=$('expandDescription');const expanded=button.getAttribute('aria-expanded')!=='true';$('gameDescription').textContent=expanded?description:preview;button.setAttribute('aria-expanded',String(expanded));button.textContent=expanded?t("Свернуть описание"):t("Показать полностью");};
  $('closeInspector').onclick=()=>{inspectorCollapsed=true;applyPanels();persistView();};
  $('platformChoice').onchange=()=>{ const custom=$('platformChoice').value==='__custom__';$('platformInput').hidden=!custom;if(custom){$('platformInput').value='';$('platformInput').focus();}else $('platformInput').value=$('platformChoice').value;dirty=true; };
  $('favoriteButton').onclick=async()=>{const button=$('favoriteButton');await busy(button,async()=>{const saved=await api('/api/save',{id:g.id,game:{title:g.title,favorite:!g.favorite}});Object.assign(g,saved);render();button.classList.toggle('isFavorite',!!g.favorite);button.setAttribute('aria-pressed',String(!!g.favorite));});button.textContent=g.favorite?t("★ В избранном"):t("☆ В избранное");};

  $('detailForm').oninput=()=>{dirty=true;};
  $('detailForm').onsubmit=async event=>{ event.preventDefault(); const button=event.submitter; const values=Object.fromEntries(new FormData(event.target)); await busy(button,async()=>{await api('/api/save',{id:g.id,game:{...g,...values,platform:values.platform||'Пока неизвестно'}}); dirty=false; await reload(); renderInspector(); toast(t("Изменения сохранены"));}); };
  $('deleteGame').onclick=async()=>{await busy($('deleteGame'),async()=>{const result=await api('/api/delete',{id:g.id}); selectedId=null;dirty=false;await reload();renderInspector();offerUndo(result.undo);});};
  if($('refreshMetadata'))$('refreshMetadata').onclick=async()=>{if(dirty){toast(t("Сначала сохрани изменения в карточке"),true);return;} await busy($('refreshMetadata'),async()=>{ const fresh=await api('/api/details?source='+encodeURIComponent(g.source_id)); await api('/api/save',{id:g.id,game:{...g,...fresh,series:seriesParts(g.series).length>1?g.series:fresh.series||g.series,platform:g.platform,status:g.status,notes:g.notes,tags:g.tags,priority:g.priority}}); await reload(); renderInspector();toast(t("Сведения обновлены"));});};
}
function exists(item) { return games.some(g=>(item.source_id && g.source_id===item.source_id)||(item.qid && g.qid===item.qid)); }
function openAdd() { if(dirty){if(!confirm(t("Изменения ещё не сохранены. Отменить их и открыть добавление игры?")))return;dirty=false;renderInspector();} $('addDialog').showModal(); $('catalogQuery').focus(); }
$('addButton').onclick=openAdd;$('emptyAdd').onclick=openAdd;$('closeDialog').onclick=()=>{$('addDialog').close();catalogSerial++;};
wireDialogBackdrop($('addDialog'),()=>{$('addDialog').close();catalogSerial++;});
$('addDialog').addEventListener('cancel',()=>{catalogSerial++;});
$('catalogForm').onsubmit=async event=>{event.preventDefault();const serial=++catalogSerial;await busy(event.submitter,async()=>{$('catalogResults').innerHTML=`<p class="loading">${t("Ищем в каталоге…")}</p>`;try{const result=await api('/api/search?q='+encodeURIComponent($('catalogQuery').value)+'&provider='+$('provider').value+'&include_extras='+Number($('includeSteamExtras').checked));if(serial!==catalogSerial)return;$('catalogResults').innerHTML=result.items.length?result.items.map((g,i)=>`<div class="catalogRow">${g.image?`<img src="${e(g.image)}" alt="" loading="lazy" draggable="false" referrerpolicy="no-referrer">`:''}<div class="catalogText"><strong>${e(g.title)}</strong><small class="catalogKind">${e(providerLabel(g.provider))}${g.release_date?' · '+e(g.release_date):''}</small>${g.description?`<p>${e(g.description)}</p>`:''}${exists(g)?`<small>${t("Уже в библиотеке")}</small>`:''}</div><button data-index="${i}" ${exists(g)?'disabled':''}>${t("Добавить")}</button></div>`).join(''):`<p class="hint">${t("Ничего не найдено. Попробуй другое название, другой каталог или ручное добавление.")}</p>`;wireImages($('catalogResults'));$('catalogResults').querySelectorAll('button').forEach(b=>b.onclick=()=>busy(b,async()=>{const item=result.items[Number(b.dataset.index)];const enriched=await api('/api/details?source='+encodeURIComponent(item.source_id));const saved=await api('/api/save',{game:{...item,...Object.fromEntries(Object.entries(enriched).filter(([k,v])=>v!==''&&v!=null))}});await reload();selectGame(saved.id,true);b.textContent=t("Добавлено");toast(t(enriched.metadata_warning) || t("Добавлено в библиотеку."));b.dataset.added='yes';}).then(()=>{if(b.dataset.added){b.disabled=true;b.textContent=t("Добавлено");}}));}catch(err){if(serial===catalogSerial)$('catalogResults').innerHTML=`<p class="warning">${e(err.message)}</p>`;throw err;}});};
$('manualForm').onsubmit=async event=>{event.preventDefault();await busy(event.submitter,async()=>{const saved=await api('/api/save',{game:{title:$('manualTitle').value,platform:$('manualPlatform').value||'Пока неизвестно'}});await reload();selectGame(saved.id,true);$('manualTitle').value='';$('addDialog').close();toast(t("Игра добавлена"));});};
['librarySearch','releaseFrom','releaseTo','addedFrom','addedTo'].forEach(id=>$(id).oninput=()=>render());
['platformFilter','genreFilter','seriesFilter','tagFilter','unknownRelease','priorityFilter'].forEach(id=>$(id).onchange=()=>render());
$('sortField').onchange=()=>{render();persistView();};$('sortDirection').onclick=()=>{direction*=-1;render();persistView();};$('viewToggle').onchange=()=>{viewMode=$('viewToggle').value;render();persistView();};
$('resetFilters').onclick=()=>{['platformFilter','genreFilter','seriesFilter','tagFilter','priorityFilter','releaseFrom','releaseTo','addedFrom','addedTo','librarySearch'].forEach(id=>$(id).value='');$('unknownRelease').checked=false;render();};
$('exportButton').onclick=()=>busy($('exportButton'),async()=>{const data=await api('/api/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`BackloGame-${localDay(new Date())}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(t("Экспорт библиотеки готов"));});
$('importButton').onclick=()=>$('importFile').click();$('importFile').onchange=async()=>{const file=$('importFile').files[0];if(!file)return;await busy($('importButton'),async()=>{if(file.size>10000000)throw new Error(t("Файл больше 10 МБ"));let data;try{data=JSON.parse(await file.text());}catch{throw new Error(t("Не удалось прочитать JSON"));}const result=await api('/api/import',data);await reload();toast(`${t("Импорт: добавлено")} ${result.added}${t(", уже были в библиотеке")} ${result.skipped}`);});$('importFile').value='';};
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
document.querySelector('.filterTitle h3').onclick=()=>document.querySelector('.sidebar').classList.toggle('filtersOpen');
restoreView();reload().then(()=>{restoreView();render();}).catch(err=>toast(t("Не удалось загрузить библиотеку: ")+err.message,true));

let settingsSaving=false, activeSettingsTab='general';
function renderSettings() {
  const categories=[...statuses,'favorites','not-favorites'];
  const label=value=>value==='favorites'?t("★ Избранное"):value==='not-favorites'?t("☆ Не в избранном"):displayValue(value);
  const manager=(kind,names,title)=>{const editable=kind==='platform'?names.filter(n=>n!=='Пока неизвестно'):names;return `<section class="settingsSection"><h3>${title}</h3><div class="settingsRow"><input id="${kind}AddName" placeholder="${t("Новое название")}" maxlength="${kind==='category'?100:300}"><button data-kind="${kind}" data-action="add">${t("Добавить")}</button></div><div class="settingsRow"><select id="${kind}Name" aria-label="${title}${t(": выбрать")}">${editable.length?editable.map(n=>`<option value="${e(n)}">${e(displayValue(n))}</option>`).join(''):`<option value="">${t("Нет платформ для изменения")}</option>`}</select><span id="${kind}Usage" class="hint"></span></div><div class="settingsRow"><input id="${kind}RenameName" placeholder="${t("Новое имя выбранного элемента")}"><button data-kind="${kind}" data-action="rename">${t("Переименовать")}</button></div><label>${t("При удалении перенести игры в")}<select id="${kind}Replacement">${names.map(n=>`<option value="${e(n)}" ${kind==='platform'&&n==='Пока неизвестно'?'selected':''}>${e(displayValue(n))}</option>`).join('')}</select></label><button class="danger" data-kind="${kind}" data-action="delete">${t("Удалить выбранный элемент")}</button><p class="hint">${t("Переименование и перенос применяются ко всем играм этой")} ${kind==='category'?t("категории"):t("платформы")}.${kind==='platform'?t(" Можно перенести в «Пока неизвестно», затем выбрать отдельную платформу в карточке каждой игры."):''}</p></section>`;};
  $('settingsContent').innerHTML=`<section class="settingsSection"><h3>${t("Разделы в левом меню")}</h3><p class="hint">${t("Скрытие раздела не удаляет игры. «Все игры» всегда доступен.")}</p><form id="viewSettings"><label>${t("Язык интерфейса")}<select name="language"><option value="en" ${uiLanguage==='en'?'selected':''}>English</option><option value="ru" ${uiLanguage==='ru'?'selected':''}>Русский</option></select></label>${themePicker()}<div class="categoryChecks">${categories.map(value=>`<label class="check"><input type="checkbox" name="visibleCategory" value="${e(value)}" ${preferences.hidden_categories.includes(value)?'':'checked'}>${e(label(value))}</label>`).join('')}</div><label>${t("Категория для новых игр")}<select name="defaultCategory">${statuses.map(value=>`<option value="${e(value)}" ${preferences.default_category===value?'selected':''}>${e(displayValue(value))}</option>`).join('')}</select></label><label class="check"><input type="checkbox" name="showNotes" ${preferences.show_card_notes?'checked':''}> ${t("Что показывать на карточках")}</label><label><select name="cardDetails" aria-label="${t("Что показывать на карточках")}">${[['both','Заметки и серии'],['notes','Заметки'],['series','Серии']].map(([value,text])=>`<option value="${value}" ${(preferences.card_details||'both')===value?'selected':''}>${t(text)}</option>`).join('')}</select></label><p id="settingsStatus" class="hint">${t("Изменения вида сохраняются автоматически.")}</p></form></section>${manager('category',statuses,t("Категории"))}${manager('platform',availablePlatforms(),t("Платформы"))}<section class="settingsSection"><h3>${t("Обложки")}</h3><p class="hint">${t("Локально сохранено:")} ${games.filter(g=>g.image_local).length} ${t("из")} ${games.filter(g=>g.image).length}${t(". Новые обложки сохраняются автоматически.")}</p><div class="settingsRow"><button id="cacheAllCovers">${t("Сохранить имеющиеся обложки")}</button></div><p id="coverUpdateProgress" class="hint">${t("При ошибке обновления сохранённая обложка остаётся.")}</p></section>`;
  const sections=[...$('settingsContent').children];
  const tabs=[['general',t("Меню и вид")],['category',t("Категории")],['platform',t("Платформы")],['covers',t("Обложки")]];
  const navigation=document.createElement('div');navigation.className='settingsTabs';navigation.setAttribute('role','tablist');navigation.setAttribute('aria-label',t("Разделы настроек"));
  navigation.innerHTML=tabs.map(([key,title])=>`<button type="button" role="tab" id="settingsTab-${key}" aria-controls="settingsPanel-${key}" data-settings-tab="${key}">${title}</button>`).join('');
  $('settingsContent').prepend(navigation);
  tabs.forEach(([key],i)=>{sections[i].id='settingsPanel-'+key;sections[i].setAttribute('role','tabpanel');sections[i].setAttribute('aria-labelledby','settingsTab-'+key);});
  const activate=(key,focus=false)=>{
    activeSettingsTab=key;
    tabs.forEach(([value],i)=>{const button=$('settingsTab-'+value),selected=value===key;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;sections[i].hidden=!selected;if(selected&&focus)button.focus();});
    $('settingsDialog').scrollTop=0;
  };
  navigation.querySelectorAll('button').forEach((button,i)=>{
    button.onclick=()=>activate(button.dataset.settingsTab);
    button.onkeydown=event=>{let target;if(event.key==='ArrowRight')target=(i+1)%tabs.length;else if(event.key==='ArrowLeft')target=(i+tabs.length-1)%tabs.length;else if(event.key==='Home')target=0;else if(event.key==='End')target=tabs.length-1;else return;event.preventDefault();activate(tabs[target][0],true);};
  });
  activate(activeSettingsTab);
  bindThemePicker();
  $('cacheAllCovers').onclick=()=>updateAllCovers();
  $('viewSettings').onchange=async()=>{
    if(settingsSaving)return;settingsSaving=true;
    const controls=[...$('viewSettings').querySelectorAll('input,select')];controls.forEach(x=>x.disabled=true);
    const hidden=[...$('viewSettings').querySelectorAll('[name=visibleCategory]:not(:checked)')].map(x=>x.value);
    try{preferences=await api('/api/settings',{hidden_categories:hidden,show_card_notes:$('viewSettings').querySelector('[name=showNotes]').checked,card_details:$('viewSettings').querySelector('[name=cardDetails]').value,default_category:$('viewSettings').querySelector('[name=defaultCategory]').value,language:$('viewSettings').querySelector('[name=language]').value});const changed=uiLanguage!==preferences.language;applyLanguage(preferences.language);rebuildOptions();render();persistView();if(changed){renderInspectorPreservingEdits();renderSettings();}$('settingsStatus').textContent=t("Сохранено");}catch(err){toast(err.message,true);renderSettings();}finally{settingsSaving=false;controls.forEach(x=>x.disabled=false);}
  };
  for(const kind of ['category','platform']) {
    const refreshUsage=()=>{const name=$(kind+'Name').value;$(kind+'Usage').textContent=`${t("Игр:")} ${games.filter(g=>(kind==='category'?g.status:g.platform)===name).length}`;const select=$(kind+'Replacement');[...select.options].forEach(o=>o.disabled=o.value===name);if(select.value===name)select.value=[...select.options].find(o=>!o.disabled)?.value||'';for(const action of ['rename','delete'])$('settingsContent').querySelector(`[data-kind="${kind}"][data-action="${action}"]`).disabled=!name||kind==='platform'&&name==='Пока неизвестно'||action==='delete'&&kind==='category'&&statuses.length<2;};
    $(kind+'Name').onchange=refreshUsage;refreshUsage();
  }
  $('settingsContent').querySelectorAll('[data-action]').forEach(button=>button.onclick=async()=>{
    if(settingsSaving){toast(t("Дождись сохранения настроек"));return;}
    if(dirty){toast(t("Сначала сохрани изменения в карточке игры"),true);return;}
    const {kind,action}=button.dataset;
    const name=action==='add'?$(kind+'AddName').value:$(kind+'Name').value;
    const replacement=action==='rename'?$(kind+'RenameName').value:$(kind+'Replacement').value;
    if(action==='delete'&&!confirm(`${t("Удалить «")}${name}${t("»? Игры будут перенесены в «")}${replacement}».`))return;
    settingsSaving=true;
    try{await busy(button,async()=>{await api(kind==='category'?'/api/categories':'/api/platforms',{action,name,replacement});if(kind==='category'&&statusFilter===name)statusFilter=action==='rename'?replacement:'';await reload();persistView();renderInspector();renderSettings();toast(t("Изменения сохранены"));});}finally{settingsSaving=false;}
  });
}
$('settingsButton').onclick=()=>{renderSettings();$('settingsDialog').showModal();};
$('closeSettings').onclick=()=>$('settingsDialog').close();
wireDialogBackdrop($('settingsDialog'),()=>$('settingsDialog').close());

let coversUpdating=false;
function updateDisplayedCover(game){
  if(selectedId===game.id){const image=$('inspector').querySelector('.detailImage');if(image)image.src=coverSource(game);}
}
async function updateAllCovers(){
  if(coversUpdating||settingsSaving){toast(t("Дождись текущего сохранения"));return;}
  coversUpdating=true;settingsSaving=true;
  const queue=games.filter(g=>g.image&&!g.image_local);
  const controls=[...$('settingsContent').querySelectorAll('button,input,select')];controls.forEach(b=>b.disabled=true);
  let done=0,failed=[];
  try{
    for(const game of queue){
      if($('coverUpdateProgress'))$('coverUpdateProgress').textContent=`${t("Обложки:")} ${done+failed.length+1} ${t("из")} ${queue.length} · ${game.title}`;
      try{const fresh=await api('/api/covers/cache',{id:game.id});Object.assign(game,fresh);updateDisplayedCover(game);done++;}catch(err){failed.push(game.title+': '+err.message);}
    }
    render();renderSettings();
    $('coverUpdateProgress').textContent=`${t("Готово:")} ${done}${t(". Ошибок:")} ${failed.length}.${failed.length?' '+failed.join(' · '):''}`;
    toast(`${t("Обложки: сохранено")} ${done}${t(", ошибок")} ${failed.length}`,!!failed.length);
  }finally{coversUpdating=false;settingsSaving=false;controls.forEach(b=>b.disabled=false);}
}
function wireSeriesSuggestions(){
  const input=$('inspector').querySelector('[name=series]'),list=$('seriesSuggestions');
  if(!input||!list)return;
  let matches=[],active=-1,segmentStart=0,segmentEnd=0;
  const close=()=>{list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');};
  const choose=value=>{
    input.value=input.value.slice(0,segmentStart)+(segmentStart?' ':'')+value+input.value.slice(segmentEnd);
    const caret=segmentStart+(segmentStart?1:0)+value.length;input.focus();input.setSelectionRange(caret,caret);dirty=true;close();
  };
  const paint=()=>{list.innerHTML=matches.map((value,i)=>`<div role="option" id="seriesOption${i}" aria-selected="${i===active}" class="seriesSuggestion ${i===active?'active':''}">${e(value)}</div>`).join('');[...list.children].forEach((item,i)=>{item.onpointerdown=event=>event.preventDefault();item.onclick=()=>choose(matches[i]);});if(active>=0)input.setAttribute('aria-activedescendant','seriesOption'+active);else input.removeAttribute('aria-activedescendant');};
  const show=()=>{
    const caret=input.selectionStart??input.value.length;
    segmentStart=input.value.lastIndexOf(';',caret-1)+1;segmentEnd=input.value.indexOf(';',caret);if(segmentEnd<0)segmentEnd=input.value.length;
    const query=input.value.slice(segmentStart,caret).trim().toLocaleLowerCase();
    const chosen=seriesParts(input.value.slice(0,segmentStart)).map(x=>x.toLocaleLowerCase());
    matches=[...new Set(games.flatMap(g=>seriesParts(g.series)))].filter(value=>query&&value.toLocaleLowerCase().includes(query)&&!chosen.includes(value.toLocaleLowerCase())).sort((a,b)=>a.localeCompare(b,'ru')).slice(0,10);
    active=-1;if(!matches.length){close();return;}paint();list.hidden=false;input.setAttribute('aria-expanded','true');
  };
  input.addEventListener('input',show);input.addEventListener('focus',show);input.addEventListener('click',show);
  input.addEventListener('blur',()=>setTimeout(close,150));
  input.addEventListener('keydown',event=>{
    if(list.hidden)return;
    if(event.key==='Escape'){event.preventDefault();close();}
    else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();active=(active+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length;paint();}
    else if(event.key==='Enter'&&active>=0){event.preventDefault();choose(matches[active]);}
  });
}

$('provider').onchange=()=>{$('extrasControl').hidden=$('provider').value!=='steam';catalogSerial++;$('catalogResults').innerHTML='';};
$('includeSteamExtras').onchange=()=>{catalogSerial++;$('catalogResults').innerHTML=`<p class="hint">${t("Нажми «Найти», чтобы обновить результаты с выбранным фильтром.")}</p>`;};

function applyPanels(){
  const workspace=document.querySelector('.workspace');
  workspace.classList.toggle('sidebarCollapsed',sidebarCollapsed);
  workspace.classList.toggle('inspectorCollapsed',inspectorCollapsed);
  for(const [id,collapsed,side] of [['toggleSidebar',sidebarCollapsed,'левую'],['toggleInspector',inspectorCollapsed,'правую']]){
    const button=$(id),label=t((collapsed?'Показать ':'Свернуть ')+side+' панель');
    button.setAttribute('aria-expanded',String(!collapsed));button.setAttribute('aria-label',label);button.title=label;button.classList.toggle('panelClosed',collapsed);
  }
}
$('toggleSidebar').onclick=()=>{sidebarCollapsed=!sidebarCollapsed;applyPanels();persistView();};
$('toggleInspector').onclick=()=>{inspectorCollapsed=!inspectorCollapsed;applyPanels();persistView();};

// Rebuilding translated labels must preserve the unsaved editor draft.
function renderInspectorPreservingEdits(){
  const form=$('detailForm');const draft=form?Object.fromEntries(new FormData(form)):null;
  const wasDirty=dirty,expanded=$('inspector').querySelector('details')?.open;
  const custom=$('platformChoice')?.value==='__custom__';
  const descriptionExpanded=$('expandDescription')?.getAttribute('aria-expanded')==='true';
  const scroll=$('inspector').scrollTop;
  renderInspector();
  if(draft)for(const [name,value]of Object.entries(draft)){const field=$('detailForm')?.elements.namedItem(name);if(field)field.value=value;}
  if(custom&&$('platformChoice')){$('platformChoice').value='__custom__';$('platformInput').hidden=false;}
  if($('inspector').querySelector('details'))$('inspector').querySelector('details').open=!!expanded;
  if(descriptionExpanded)$('expandDescription')?.click();
  $('inspector').scrollTop=scroll;dirty=wasDirty;
}
function providerLabel(value){return String(value||'').split(' · ').map(part=>t(part)).join(' · ');}
