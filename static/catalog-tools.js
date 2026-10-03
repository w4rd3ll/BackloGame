'use strict';
const catalogUpdateDialog=document.createElement('dialog');catalogUpdateDialog.className='catalogUpdateDialog';document.body.append(catalogUpdateDialog);
const catalogBatchDialog=document.createElement('dialog');catalogBatchDialog.className='catalogBatchDialog';document.body.append(catalogBatchDialog);
let catalogBatchRunning=false,catalogUpdateSession=0;
async function openCatalogUpdate(game,mode='metadata',requestedProvider=null,orientation='portrait'){
  if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}
  if(catalogBatchRunning){toast(t('Дождись обновления каталога'),true);return;}
  if(mode==='cover'&&(!requestedProvider||requestedProvider==='steamgriddb')){await openSteamGrid(game,orientation);return;}
  if(mode==='metadata'){await openCatalogComparison(game);return;}
  const provider=requestedProvider||(steamSource(game)?'steam':game.source_id?.startsWith('wiki:')?'wikipedia':'metacritic');
  const session=++catalogUpdateSession;
  catalogUpdateDialog.innerHTML=`<div class="dialogHead"><h2>${t(mode==='cover'?'Выбрать обложку из каталога':'Обновить сведения из каталога')}</h2><button id="closeCatalogUpdate" aria-label="${t('Закрыть')}">✕</button></div><p class="hint">${e(game.title)} · ${e(displayValue(game.platform))}</p><form id="catalogUpdateSearch"><input id="catalogUpdateQuery" value="${e(game.original_title||game.title)}" required maxlength="300" aria-label="${t('Название игры')}"><select id="catalogUpdateProvider" aria-label="${t('Источник')}"><option value="metacritic">Metacritic</option><option value="steam">Steam</option><option value="wikipedia">Wikipedia / Wikidata</option></select><button class="primary">${t('Найти')}</button></form><p class="hint">${t('Выбери соответствующую игру. Прогресс, даты прохождений, заметки и основная ссылка сохраняются.')}</p><div id="catalogUpdateResults"></div><div id="catalogUpdatePreview"></div>`;
  $('catalogUpdateProvider').value=provider;
  if(mode==='cover'){
    const option=document.createElement('option');option.value='steamgriddb';option.textContent='SteamGridDB';$('catalogUpdateProvider').prepend(option);
    const format=document.createElement('select');format.id='catalogCoverOrientation';format.setAttribute('aria-label',t('Формат обложки'));format.innerHTML=`<option value="portrait">${t('Вертикальная')}</option><option value="landscape">${t('Горизонтальная')}</option>`;format.value=orientation;$('catalogUpdateSearch').after(format);
  }
  let serial=0,applying=false;
  const close=()=>{if(!applying)catalogUpdateDialog.close();};$('closeCatalogUpdate').onclick=close;catalogUpdateDialog.oncancel=event=>{if(applying)event.preventDefault();};
  catalogUpdateDialog.onclick=event=>{if(event.target===catalogUpdateDialog){const r=catalogUpdateDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}};
  async function search(){
    const revision=++serial;$('catalogUpdateResults').hidden=false;$('catalogUpdateResults').textContent=t('Ищем в каталоге…');$('catalogUpdatePreview').textContent='';
    try{
      const result=await api('/api/search?q='+encodeURIComponent($('catalogUpdateQuery').value)+'&provider='+$('catalogUpdateProvider').value);if(revision!==serial||session!==catalogUpdateSession)return;
      $('catalogUpdateResults').innerHTML=result.items.map((item,i)=>`<div class="catalogRow">${item.image?`<img src="${e(item.image)}" alt="" referrerpolicy="no-referrer">`:''}<div class="catalogText"><strong>${e(item.title)}</strong><small>${e(providerLabel(item.provider))}</small></div><button data-update-candidate="${i}">${t('Выбрать')}</button></div>`).join('')||`<p class="hint">${t('Ничего не найдено. Попробуй другое название, другой каталог или ручное добавление.')}</p>`;
      $('catalogUpdateResults').querySelectorAll('[data-update-candidate]').forEach(button=>button.onclick=()=>busy(button,async()=>{
        const selection=++serial,item=result.items[Number(button.dataset.updateCandidate)];$('catalogUpdatePreview').textContent=t('Загрузка…');
        try{
          const fresh=await api('/api/details?source='+encodeURIComponent(item.source_id));if(selection!==serial||session!==catalogUpdateSession)return;
          $('catalogUpdateResults').hidden=true;
          $('catalogUpdatePreview').innerHTML=`<button id="backCatalogResults" class="text">← ${t('Другой результат')}</button><div class="catalogSelected">${fresh.image?`<img src="${e(fresh.image)}" alt="" referrerpolicy="no-referrer">`:''}<h3>${e(fresh.title)}</h3>${mode==='metadata'?`<p class="description">${e(descriptionPreview(fresh.description||''))}</p><p>${t('Серии, через ;')}: ${e(game.series||fresh.series||t('Не указана'))}</p>`:''}<button id="applyCatalogUpdate" class="primary" ${mode==='cover'&&!fresh.image?'disabled':''}>${t(mode==='cover'?'Использовать обложку':'Применить сведения')}</button></div>`;
          $('backCatalogResults').onclick=()=>{$('catalogUpdateResults').hidden=false;$('catalogUpdatePreview').textContent='';};
          $('applyCatalogUpdate').onclick=()=>busy($('applyCatalogUpdate'),async()=>{
            applying=true;catalogUpdateDialog.querySelectorAll('input,select,button').forEach(x=>x.disabled=true);
            try{await api('/api/catalog/apply',{id:game.id,source:item.source_id,mode,...(mode==='cover'?{orientation:$('catalogCoverOrientation').value}:{})});await reload();renderInspector();catalogUpdateDialog.close();toast(t(mode==='cover'?'Обложка обновлена':'Сведения обновлены'));}
            finally{applying=false;catalogUpdateDialog.querySelectorAll('input,select,button').forEach(x=>x.disabled=false);}
          });
        }catch(err){if(selection===serial&&session===catalogUpdateSession)$('catalogUpdatePreview').textContent=t(err.message);}
      }));
    }catch(err){if(revision===serial&&session===catalogUpdateSession)$('catalogUpdateResults').textContent=t(err.message);}
  }
  $('catalogUpdateSearch').onsubmit=event=>{event.preventDefault();search();};$('catalogUpdateProvider').onchange=()=>{if($('catalogUpdateProvider').value==='steamgriddb'){const format=$('catalogCoverOrientation').value;serial++;catalogUpdateDialog.close();openSteamGrid(game,format);}else search();};
  catalogUpdateDialog.showModal();await search();
}
const catalogComparisonFields=[['title','Название'],['description','Описание'],['genre','Жанры, через запятую'],['developer','Разработчик'],['available_platforms','Доступные платформы'],['release_date','Дата выхода'],['series','Серии, через ;'],['image','Обложка']];
function catalogComparisonProviderLabel(provider){return {steam:'Steam',metacritic:'Metacritic',wikipedia:'Wikipedia / Wikidata'}[provider]||provider;}
function catalogFieldValue(game,field){return field==='release_date'?(game.release_date||game.release_label||''):field==='image'?(game.custom_covers?.portrait?.url||game.image||''):game[field]||'';}
function catalogChosenFields(selected,states){
  return Object.fromEntries(Object.entries(selected).filter(([,provider])=>provider&&states[provider]?.game).map(([field,provider])=>[field,states[provider].source]));
}
async function openCatalogComparison(game){
  const providers=['steam','metacritic','wikipedia'],session=++catalogUpdateSession;
  const states=Object.fromEntries(providers.map(provider=>[provider,{items:[],game:null,source:'',loading:true,error:'',revision:0}]));
  const selected={};let revision=0,applying=false;
  catalogUpdateDialog.classList.add('catalogComparisonDialog');
  catalogUpdateDialog.innerHTML=`<div class="dialogHead"><h2>${t('Обновить сведения из каталога')}</h2><button id="closeCatalogUpdate" aria-label="${t('Закрыть')}">✕</button></div><p class="hint">${e(game.title)} · ${e(displayValue(game.platform))}</p><form id="catalogUpdateSearch"><input id="catalogUpdateQuery" value="${e(game.original_title||game.title)}" required maxlength="300" aria-label="${t('Название игры')}"><button class="primary">${t('Найти во всех каталогах')}</button></form><p class="hint">${t('Выбери игру в каждом каталоге, затем отметь, какие сведения взять. Остальные поля сохранятся.')}</p><div id="catalogComparisonResults"></div><div class="catalogComparisonActions"><span id="catalogSelectionCount" class="hint" role="status"></span><button id="applyCatalogFields" class="primary" disabled>${t('Применить выбранное')}</button></div>`;
  const active=()=>session===catalogUpdateSession&&catalogUpdateDialog.open;
  const close=()=>{if(!applying){catalogUpdateDialog.close();++catalogUpdateSession;catalogUpdateDialog.classList.remove('catalogComparisonDialog');}};
  $('closeCatalogUpdate').onclick=close;catalogUpdateDialog.oncancel=event=>{event.preventDefault();close();};
  catalogUpdateDialog.onclick=event=>{if(event.target===catalogUpdateDialog){const r=catalogUpdateDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}};
  function value(item,field){
    const content=catalogFieldValue(item,field);
    if(!content)return `<span class="hint">${t('Нет данных')}</span>`;
    if(field==='image')return `<img class="catalogCompareCover" src="${e(item.custom_covers?.portrait?.local||item.image_local||content)}" alt="" referrerpolicy="no-referrer">`;
    if(field==='description')return `<div class="catalogCompareDescription">${e(content)}</div>`;
    return `<span>${e(Array.isArray(content)?content.join(', '):content)}</span>`;
  }
  function updateCount(){const count=Object.keys(catalogChosenFields(selected,states)).length;$('catalogSelectionCount').textContent=t('Выбрано полей:')+' '+count;$('applyCatalogFields').disabled=!count||applying;}
  function draw(){
    if(!active()||applying)return;
    $('catalogComparisonResults').innerHTML=`<div class="catalogComparisonScroll"><table class="catalogComparisonTable"><thead><tr><th>${t('Поле')}</th><th>${t('Сейчас в библиотеке')}</th>${providers.map(provider=>{const state=states[provider];return `<th><strong>${e(catalogComparisonProviderLabel(provider))}</strong><select data-compare-provider="${provider}" aria-label="${e(catalogComparisonProviderLabel(provider))}: ${t('Выбрать игру')}" ${state.loading?'disabled':''}><option value="">${t('Выбрать игру')}</option>${state.items.map((item,index)=>`<option value="${index}" ${item.source_id===state.source?'selected':''}>${e(item.title)}</option>`).join('')}</select>${state.loading?`<p class="hint" role="status">${t('Загрузка…')}</p>`:state.error?`<p class="warning">${e(t(state.error))}</p>`:!state.items.length?`<p class="hint">${t('Ничего не найдено')}</p>`:''}</th>`;}).join('')}</tr></thead><tbody>${catalogComparisonFields.map(([field,label])=>`<tr><th scope="row">${t(label)}</th><td class="${!selected[field]?'catalogFieldSelected':''}"><label class="catalogFieldChoice"><input type="radio" name="catalog-field-${field}" data-compare-field="${field}" value="" ${!selected[field]?'checked':''} aria-label="${t(label)}: ${t('Оставить текущее')}">${value(game,field)}</label></td>${providers.map(provider=>{const state=states[provider],available=state.game&&catalogFieldValue(state.game,field);return `<td class="${selected[field]===provider?'catalogFieldSelected':''}"><label class="catalogFieldChoice"><input type="radio" name="catalog-field-${field}" data-compare-field="${field}" value="${provider}" ${selected[field]===provider?'checked':''} ${!available||state.loading?'disabled':''} aria-label="${t(label)}: ${e(catalogComparisonProviderLabel(provider))}">${state.game?value(state.game,field):'<span class="hint">—</span>'}</label></td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;
    $('catalogComparisonResults').querySelectorAll('[data-compare-field]').forEach(input=>input.onchange=()=>{selected[input.dataset.compareField]=input.value;draw();});
    $('catalogComparisonResults').querySelectorAll('[data-compare-provider]').forEach(input=>input.onchange=()=>selectCandidate(input.dataset.compareProvider,input.value));
    updateCount();
  }
  async function selectCandidate(provider,index){
    const state=states[provider],item=state.items[Number(index)],selection=++state.revision,searchRevision=revision;
    for(const field of Object.keys(selected))if(selected[field]===provider)delete selected[field];
    state.game=null;state.source='';state.error='';
    if(index===''||!item){draw();return;}
    state.source=item.source_id;state.loading=true;draw();
    try{const fresh=await api('/api/details?raw=1&source='+encodeURIComponent(item.source_id));if(active()&&revision===searchRevision&&selection===state.revision)state.game=fresh;}
    catch(error){if(active()&&revision===searchRevision&&selection===state.revision)state.error=error.message;}
    finally{if(active()&&revision===searchRevision&&selection===state.revision){state.loading=false;draw();}}
  }
  async function search(){
    if(applying)return;
    const searchRevision=++revision,query=$('catalogUpdateQuery').value.trim();
    for(const field of Object.keys(selected))delete selected[field];
    for(const state of Object.values(states)){state.items=[];state.game=null;state.source='';state.error='';state.loading=true;state.revision++;}draw();
    const normalize=text=>text.toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
    await Promise.allSettled(providers.map(async provider=>{
      const state=states[provider];
      try{
        const result=await api('/api/search?q='+encodeURIComponent(query)+'&provider='+provider);
        if(!active()||revision!==searchRevision)return;
        state.items=result.items;state.loading=false;draw();
        const exact=state.items.map((item,index)=>({item,index})).filter(({item})=>normalize(item.title)===normalize(query));
        if(exact.length===1)await selectCandidate(provider,String(exact[0].index));
      }catch(error){if(active()&&revision===searchRevision){state.error=error.message;state.loading=false;draw();}}
    }));
  }
  $('catalogUpdateSearch').onsubmit=event=>{event.preventDefault();search();};
  $('applyCatalogFields').onclick=()=>busy($('applyCatalogFields'),async()=>{
    const fields=catalogChosenFields(selected,states);if(!Object.keys(fields).length)return;
    applying=true;catalogUpdateDialog.querySelectorAll('input,select,button').forEach(input=>input.disabled=true);
    try{await api('/api/catalog/apply',{id:game.id,mode:'metadata',fields});await reload();renderInspector();applying=false;close();toast(t('Сведения обновлены'));}
    finally{applying=false;if(active()){catalogUpdateDialog.querySelectorAll('input,select,button').forEach(input=>input.disabled=false);draw();}}
  });
  catalogUpdateDialog.showModal();draw();await search();
}
const inspectorBeforeCatalog=renderInspector;
renderInspector=function(){
  inspectorBeforeCatalog();const game=games.find(g=>g.id===selectedId);if(!game)return;
  if($('refreshMetadata'))$('refreshMetadata').onclick=()=>openCatalogUpdate(game);
  else{const b=document.createElement('button');b.id='refreshMetadata';b.className='text';b.textContent=t('Обновить сведения');b.onclick=()=>openCatalogUpdate(game);$('inspector').querySelector('.detailSource').append(b);}
  const coverButton=document.createElement('button');coverButton.className='text';coverButton.textContent=t('Выбрать обложку из каталога');coverButton.onclick=()=>openCatalogUpdate(game,'cover');$('inspector').querySelector('.detailSource').append(coverButton);
};
document.addEventListener('contextmenu',event=>{
  const row=event.target.closest('.game'),image=event.target.closest('[data-cover-id]');
  const game=games.find(g=>g.id===Number(row?.dataset.id||image?.dataset.coverId));if(!game)return;
  const menu=row?quickMenu:$('coverMenu');
  menu.querySelectorAll('[data-catalog-action]').forEach(x=>x.remove());
  const coverButton=document.createElement('button');coverButton.dataset.catalogAction='cover';coverButton.textContent=t('Выбрать обложку из каталога');coverButton.onclick=()=>{menu.hidden=true;openCatalogUpdate(game,'cover');};menu.append(coverButton);
  if(row){
    const info=document.createElement('button');info.dataset.catalogAction='metadata';info.textContent=t('Обновить сведения');info.onclick=()=>{menu.hidden=true;openCatalogUpdate(game);};menu.append(info);
    const merge=document.createElement('button');merge.dataset.catalogAction='merge';merge.textContent=t('Объединить выбранные');merge.disabled=markedGames.size!==2||!markedGames.has(game.id);merge.title=t('Выбери ровно две карточки одной игры');merge.onclick=()=>{menu.hidden=true;mergeButton.click();};menu.append(merge);
  }
  menu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-menu.offsetHeight-8))+'px';
});
async function runCatalogBatch(mode,provider='auto',missing=true){
  if(catalogBatchRunning||coversUpdating||settingsSaving){toast(t('Дождись текущего сохранения'),true);return;}
  if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}
  const queue=games.filter(g=>mode==='series'?!g.series?.trim():!missing||!g.image_local);
  catalogBatchRunning=true;coversUpdating=true;settingsSaving=true;let stop=false,done=0,skipped=0,failed=[];
  catalogBatchDialog.innerHTML=`<div class="dialogHead"><h2>${t(mode==='series'?'Заполнить пустые серии':'Обновление обложек')}</h2><button id="closeCatalogBatch" disabled aria-label="${t('Закрыть')}">✕</button></div><p id="catalogBatchProgress" role="status"></p><progress id="catalogBatchMeter" max="${Math.max(1,queue.length)}" value="0"></progress><p class="hint">${t('Заполненные серии сохраняются. Неоднозначные совпадения пропускаются. Остановка сохранит уже полученные результаты.')}</p><button id="stopCatalogBatch">${t('Остановить')}</button><details id="catalogBatchErrors" hidden><summary>${t('Ошибки')}</summary><div></div></details>`;
  const close=()=>{if(!catalogBatchRunning)catalogBatchDialog.close();else stop=true;};catalogBatchDialog.oncancel=event=>{if(catalogBatchRunning){event.preventDefault();stop=true;}};$('stopCatalogBatch').onclick=()=>{stop=true;$('stopCatalogBatch').disabled=true;};$('closeCatalogBatch').onclick=close;
  catalogBatchDialog.showModal();
  try{
    if(queue.length)await api('/api/backup-create',{});
    for(let i=0;i<queue.length&&!stop;i++){
      const game=queue[i];$('catalogBatchProgress').textContent=`${i+1} / ${queue.length} · ${game.title}`;
      try{const result=await api('/api/catalog/automatic',{id:game.id,mode,provider});Object.assign(game,result.game);result.changed?done++:skipped++;}
      catch(err){failed.push(game.title+': '+t(err.message));}
      $('catalogBatchMeter').value=i+1;
      if(!stop)await new Promise(resolve=>setTimeout(resolve,500));
    }
    await reload();renderInspector();
    $('catalogBatchProgress').textContent=`${t('Обновлено:')} ${done} · ${t('Пропущено:')} ${skipped} · ${t('Ошибки')}: ${failed.length}`+(stop?' · '+t('Остановлено'):'');
    $('catalogBatchErrors').hidden=!failed.length;$('catalogBatchErrors').querySelector('div').textContent=failed.join('\n');
  }catch(err){$('catalogBatchProgress').textContent=t(err.message);}
  finally{catalogBatchRunning=false;coversUpdating=false;settingsSaving=false;$('closeCatalogBatch').disabled=false;$('stopCatalogBatch').hidden=true;renderSettings();render();}
}
const settingsBeforeCatalog=renderSettings;
renderSettings=function(){
  settingsBeforeCatalog();
  const panel=$('cacheAllCovers').closest('.settingsSection'),controls=document.createElement('div');controls.className='catalogBatchControls';
  controls.innerHTML=`<label>${t('Источник альтернативных обложек')}<select id="catalogCoverProvider"><option value="auto">${t('Авто: Steam → Metacritic → Wikipedia')}</option><option value="metacritic">Metacritic</option><option value="steam">Steam</option><option value="wikipedia">Wikipedia / Wikidata</option></select></label><div class="settingsRow"><button id="catalogMissingCovers">${t('Заполнить отсутствующие обложки')}</button><button id="catalogAllCovers">${t('Обновить обложки из каталога')}</button></div><p class="hint">${t('Автоматически выбирается только точное совпадение. Для другой версии игры выбери обложку вручную через ПКМ.')}</p>`;
  panel.append(controls);$('catalogMissingCovers').onclick=()=>runCatalogBatch('cover',$('catalogCoverProvider').value,true);$('catalogAllCovers').onclick=()=>runCatalogBatch('cover',$('catalogCoverProvider').value,false);
  const source=$('steamSourcePanel'),section=document.createElement('div');
  section.innerHTML=`<h3>${t('Серии игр')}</h3><p class="hint">${t('Steam и Metacritic дают обложки и сведения. Серии берутся из Wikidata: только явно связанные игры, без догадок по названию.')}</p><button id="catalogFillSeries">${t('Заполнить пустые серии')}</button>`;source.append(section);$('catalogFillSeries').onclick=()=>runCatalogBatch('series');
};
