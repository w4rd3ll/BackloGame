'use strict';
function todayDate(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function completedText(value){return /^\d{4}-\d{2}-\d{2}$/.test(value||'')?value.split('-').reverse().join('.'):'';}
const completionOption=document.createElement('option');completionOption.value='completed_at';completionOption.dataset.i18n='По дате прохождения';completionOption.textContent=t('По дате прохождения');$('sortField').append(completionOption);
const contentBeforeDates=gameContent;
gameContent=function(g){
  let html=contentBeforeDates(g);
  const date=g.status==='Пройдено'?completedText(g.completed_at):'';
  if(viewMode==='compact'){
    if(date)html=html.replace(/<\/span>$/,` · <time datetime="${e(g.completed_at)}">${date}</time></span>`);
  }else{
    html=html.replace(/<h3>(.*?)<\/h3>/, '<h3><span class="gameName">$1</span></h3>');
    if(date)html=html.replace(/(<span class="status [^"]*">)(.*?)(<\/span>)/,`$1<span class="statusLabel">$2</span><time class="completionDate" datetime="${e(g.completed_at)}">${date}</time>$3`);
  }
  return html;
};
const inspectorBeforeDates=renderInspector;
renderInspector=function(){
  inspectorBeforeDates();
  const form=$('detailForm'),g=games.find(x=>x.id===selectedId);if(!form||!g)return;
  const status=form.elements.namedItem('status');
  let dates=(g.playthroughs||[]).map(row=>({...row})),pendingIndex=-1;
  const section=document.createElement('section');section.className='completionHistory';
  status.closest('.formGrid').after(section);
  function drawDates(){
    section.innerHTML=`<h3>${t('История прохождений')}</h3><div class="completionChips">${dates.map((row,i)=>`<span class="completionChip"><time datetime="${e(row.date)}">${completedText(row.date)}</time><input class="historyPlatform" list="platformOptions" data-history-platform="${i}" value="${e(row.platform)}" aria-label="${t('Платформа прохождения')} ${completedText(row.date)}" maxlength="140"><button type="button" data-remove-date="${i}" aria-label="${t('Удалить дату')} ${completedText(row.date)}">×</button></span>`).join('')||`<span class="hint">${t('Дат прохождения пока нет')}</span>`}</div><button type="button" class="text" id="addCompletion">＋ ${t('Добавить прохождение')}</button>`;
    section.querySelectorAll('[data-history-platform]').forEach(input=>input.oninput=()=>{dates[Number(input.dataset.historyPlatform)].platform=input.value.trim()||'Пока неизвестно';dirty=true;});
    section.querySelectorAll('[data-remove-date]').forEach(button=>button.onclick=()=>{const index=Number(button.dataset.removeDate);dates.splice(index,1);if(index===pendingIndex)pendingIndex=-1;else if(index<pendingIndex)pendingIndex--;dirty=true;drawDates();});
    $('addCompletion').onclick=async()=>{const row=await choosePlaythrough(form.elements.namedItem('platform').value);if(row){dates.push(row);dirty=true;drawDates();}};
  }
  drawDates();
  status.addEventListener('change',async()=>{
    const previous=status.dataset.previous||g.status;status.dataset.previous=status.value;
    if(status.value==='Пройдено'&&previous!=='Пройдено'){
      const date=await choosePlaythrough(form.elements.namedItem('platform').value);
      if(!date){status.value=previous;status.dataset.previous=previous;return;}
      if(pendingIndex>=0)dates.splice(pendingIndex,1);pendingIndex=dates.length;dates.push(date);dirty=true;drawDates();
    }else if(pendingIndex>=0){dates.splice(pendingIndex,1);pendingIndex=-1;drawDates();}
  });
  form.onsubmit=async event=>{
    event.preventDefault();if(completeDialog.open)return;
    const values=Object.fromEntries(new FormData(form));
    const history=dates;
    await busy(event.submitter,async()=>{await api('/api/save',{id:g.id,game:{...g,...values,playthroughs:history,platform:values.platform||'Пока неизвестно'}});dirty=false;await reload();renderInspector();toast(t('Изменения сохранены'));});
  };

};
const completeDialog=document.createElement('dialog');completeDialog.className='dateDialog';document.body.append(completeDialog);
async function choosePlaythrough(platform){
  const date=await chooseCompletionDate(null,platform||'Пока неизвестно');
  return date;
}
function chooseCompletionDate(initial,platform){return new Promise(resolve=>{
  completeDialog.innerHTML=`<form method="dialog"><h2>${t('Дата прохождения')}</h2><input id="completionChoice" type="date" required value="${e(initial||todayDate())}">${platform!==undefined?`<label>${t('Платформа прохождения')}<input id="completionPlatform" list="platformOptions" value="${e(platform)}" maxlength="140" required></label>`:''}<div class="detailActions"><button type="button" id="cancelCompletion">${t('Отмена')}</button><button class="primary">${t('Сохранить')}</button></div></form>`;
  let result=null;
  completeDialog.onclose=()=>resolve(result);
  $('cancelCompletion').onclick=()=>completeDialog.close();
  completeDialog.querySelector('form').onsubmit=event=>{event.preventDefault();result=platform===undefined?$('completionChoice').value:{date:$('completionChoice').value,platform:$('completionPlatform').value.trim()||'Пока неизвестно'};completeDialog.close();};completeDialog.showModal();
});}
const updateBeforeDates=quickUpdate;
quickUpdate=async function(ids,patch){
  if(patch.status==='Пройдено'&&!patch.completed_at){const g=ids.length===1?games.find(x=>x.id===ids[0]):null;const date=await chooseCompletionDate(g?.status==='Пройдено'?g.completed_at:null);if(!date)return false;patch={...patch,completed_at:date};}
  return updateBeforeDates(ids,patch);
};
let activeCategoryView=null,categoryViewTimer;
const renderBeforeCategoryViews=render;
render=function(){
  const key=statusFilter||'all';
  if(activeCategoryView!==key){
    const v=preferences.category_sorts?.[key]||{field:'manual_order',direction:-1,view:'cards'};
    if([...$('sortField').options].some(o=>o.value===v.field))$('sortField').value=v.field;
    direction=v.direction===1?1:-1;viewMode=['cards','list','compact'].includes(v.view)?v.view:'cards';activeCategoryView=key;
  }
  renderBeforeCategoryViews();
};
const persistBeforeCategoryViews=persistView;
const restoreBeforeCategoryViews=restoreView;
restoreView=function(){restoreBeforeCategoryViews();activeCategoryView=null;};
persistView=function(){
  persistBeforeCategoryViews();
  preferences.category_sorts={...(preferences.category_sorts||{}),[statusFilter||'all']:{field:$('sortField').value,direction,view:viewMode}};
  clearTimeout(categoryViewTimer);
  categoryViewTimer=setTimeout(async()=>{try{await api('/api/settings',{category_sorts:preferences.category_sorts});}catch(err){toast(err.message,true);}},100);
};

const libraryDialog=document.createElement('dialog');libraryDialog.id='libraryImportDialog';document.body.append(libraryDialog);
const libraryButton=document.createElement('button');libraryButton.id='libraryImportButton';libraryButton.textContent='⇄';libraryButton.title=t('Импорт библиотеки');libraryButton.setAttribute('aria-label',libraryButton.title);$('addButton').before(libraryButton);
libraryButton.dataset.i18nTitle='Импорт библиотеки';libraryButton.dataset.i18nAriaLabel='Импорт библиотеки';
libraryButton.onclick=openRemoteLibrary;
let libraryPreview='',libraryItems=[],libraryChoices={},librarySelected=new Set(),libraryLoading=false,libraryNewOnly=false;
const mergeFields=['status','completed_at','platform','image','description','notes','release_date','tags'];
const mergeLabels={'status':'Статус','completed_at':'Дата прохождения','platform':'Платформа','image':'Обложка','description':'Описание','notes':'Моя заметка','release_date':'Дата выхода','tags':'Теги'};
function openRemoteLibrary(){
  if(libraryLoading){libraryDialog.showModal();return;}
  libraryPreview='';libraryItems=[];libraryChoices={};librarySelected.clear();libraryNewOnly=false;
  libraryDialog.innerHTML=`<div class="dialogHead"><h2>${t('Импорт библиотеки')}</h2><button id="closeLibraryImport">✕</button></div><form id="libraryLoadForm" class="libraryLoad"><select id="libraryProvider"><option value="hltb">HowLongToBeat</option><option value="hltb-csv">HLTB CSV</option><option value="steam">Steam</option></select><input id="libraryProfile" type="text" placeholder="https://howlongtobeat.com/user/…"><input id="libraryCsv" type="file" accept=".csv,text/csv" hidden><input id="librarySteamKey" type="password" autocomplete="off" placeholder="Steam Web API key" hidden><button class="primary">${t('Загрузить список')}</button></form><p id="libraryHelp" class="hint"></p><p id="libraryProgress" role="status"></p><div id="libraryPreviewControls" hidden><input id="libraryFind" type="search" placeholder="${t('Поиск: название, серия, заметка…')}"><div class="settingsRow"><button id="libraryShowNew" hidden aria-pressed="false">${t('Показать новые')}</button><button id="librarySelectAll">${t('Выбрать видимые')}</button><button id="libraryConfirmDuplicates">${t('Применить ко всем совпадениям')}</button><button id="librarySkipDuplicates">${t('Пропустить все совпадения')}</button></div><div id="libraryRows"></div><div class="detailActions"><span id="librarySelectedCount"></span><button id="libraryApply" class="primary">${t('Добавить выбранные')}</button></div></div>`;
  $('closeLibraryImport').onclick=()=>libraryDialog.close();
  const sourceChange=()=>{const source=$('libraryProvider').value;$('libraryProfile').hidden=source==='hltb-csv';$('libraryCsv').hidden=source!=='hltb-csv';$('librarySteamKey').hidden=source!=='steam';$('libraryHelp').innerHTML=source==='steam'?`<a href="https://steamcommunity.com/dev/apikey" target="_blank" rel="noopener noreferrer">Steam Web API key ↗</a> · ${t('Ключ используется один раз и не сохраняется.')}`:t('HLTB — публичный список по ссылке или CSV. Статусы распределяются автоматически.');};
  $('libraryProvider').onchange=sourceChange;sourceChange();
  $('libraryLoadForm').onsubmit=async event=>{
    event.preventDefault();if(libraryLoading)return;
    try{
      libraryLoading=true;setLibraryBusy(true);$('libraryPreviewControls').hidden=true;
      const provider=$('libraryProvider').value,payload={provider,profile:$('libraryProfile').value,api_key:$('librarySteamKey').value};
      if(provider==='hltb-csv'){const file=$('libraryCsv').files[0];if(!file)throw Error(t('Выбери CSV-файл'));if(file.size>10000000)throw Error(t('Файл больше 10 МБ'));payload.csv=await file.text();}
      const response=await api('/api/library-sync/preview',payload);$('librarySteamKey').value='';
      const result=await pollLibraryJob(response.job);libraryPreview=response.job;libraryItems=result.items;libraryChoices={};librarySelected=new Set();
      $('libraryProgress').textContent=`${t('Игр:')} ${libraryItems.length}`+(provider==='steam'?' · '+(result.steam_baseline?t('Исходный список Steam сохранён. Новые игры появятся после следующей проверки.'):t('Новых:')+' '+result.steam_new_count):'');$('libraryShowNew').hidden=provider!=='steam';$('libraryShowNew').textContent=t('Показать новые');$('libraryShowNew').setAttribute('aria-pressed','false');libraryNewOnly=false;$('libraryPreviewControls').hidden=false;renderLibraryRows();
    }catch(err){$('libraryProgress').textContent=t(err.message);}
    finally{libraryLoading=false;setLibraryBusy(false);}
  };
  $('libraryFind').oninput=renderLibraryRows;
  $('libraryShowNew').onclick=()=>{libraryNewOnly=!libraryNewOnly;librarySelected.clear();$('libraryShowNew').textContent=t(libraryNewOnly?'Показать все':'Показать новые');$('libraryShowNew').setAttribute('aria-pressed',String(libraryNewOnly));renderLibraryRows();};
  const clearSelection=document.createElement('button');clearSelection.textContent=t('Снять выделение');$('librarySelectAll').after(clearSelection);clearSelection.onclick=()=>{librarySelected.clear();renderLibraryRows();};
  $('librarySelectAll').onclick=()=>{libraryItems.forEach((x,i)=>{if(!x.ambiguous&&libraryVisible(x)){librarySelected.add(i);if(x.existing_id&&!libraryChoices[i])libraryChoices[i]={fields:['status','completed_at','tags'],overwrite:false};}});renderLibraryRows();};
  $('librarySkipDuplicates').onclick=()=>{libraryItems.forEach((x,i)=>{if(x.existing_id){librarySelected.delete(i);delete libraryChoices[i];}});renderLibraryRows();};
  $('libraryConfirmDuplicates').onclick=()=>{
    const first=Object.values(libraryChoices)[0]||{fields:['status','completed_at','tags'],overwrite:false};
    libraryItems.forEach((x,i)=>{if(x.existing_id&&!x.ambiguous&&libraryVisible(x)){librarySelected.add(i);libraryChoices[i]={fields:[...first.fields],overwrite:first.overwrite};}});renderLibraryRows();
  };
  $('libraryApply').onclick=async()=>{
    if(libraryLoading||!librarySelected.size)return;
    try{libraryLoading=true;setLibraryBusy(true);const response=await api('/api/library-sync/apply',{preview:libraryPreview,selected:[...librarySelected],choices:libraryChoices});const result=await pollLibraryJob(response.job);await reload();renderInspector();$('libraryProgress').textContent=`${t('Добавлено:')} ${result.added} · ${t('Обновлено:')} ${result.updated} · ${t('Пропущено:')} ${result.skipped}`;$('libraryPreviewControls').hidden=true;}
    catch(err){$('libraryProgress').textContent=t(err.message);await reload();}
    finally{libraryLoading=false;setLibraryBusy(false);}
  };
  libraryDialog.showModal();
}
function libraryVisible(x){return (!libraryNewOnly||x.steam_new)&&[x.title,x.platform].join(' ').toLocaleLowerCase().includes(($('libraryFind')?.value||'').toLocaleLowerCase());}
function setLibraryBusy(busy){libraryDialog.querySelectorAll('input,select,button:not(#closeLibraryImport)').forEach(x=>x.disabled=busy);if(!busy){libraryDialog.querySelectorAll('[data-library-select]').forEach(x=>x.disabled=!!libraryItems[Number(x.dataset.librarySelect)]?.ambiguous);if($('libraryApply'))updateLibraryCount();}}
async function pollLibraryJob(id){
  for(;;){const response=await fetch('/api/library-sync/job?id='+encodeURIComponent(id),{headers:{'X-Library-Token':token}});const result=await response.json();if(!response.ok||result.state==='error')throw Error(result.error);$('libraryProgress').textContent=`${t('Загрузка…')} ${result.current}/${result.total||'…'}`;if(result.state==='done')return result;await new Promise(r=>setTimeout(r,600));}
}
function renderLibraryRows(){
  $('libraryRows').innerHTML=libraryItems.map((x,i)=>{if(!libraryVisible(x))return '';const choice=libraryChoices[i]||{fields:['status','completed_at','tags'],overwrite:false};
    const old=x.existing||{};
    return `<div class="libraryRow"><label class="check"><input type="checkbox" data-library-select="${i}" ${librarySelected.has(i)?'checked':''} ${x.ambiguous?'disabled':''}>${x.image?`<img src="${e(x.image)}" loading="lazy" referrerpolicy="no-referrer" alt="">`:''}<span><strong>${e(x.title)}</strong><small>${e(displayValue(x.platform))} · ${e(displayValue(x.status))}${x.completed_at?' · '+completedText(x.completed_at):''}</small></span></label>${x.ambiguous?`<p class="warning">${t('Неоднозначное совпадение. Сопоставь игры вручную.')}</p>`:x.existing_id?`<details><summary>${t('Совпадение — выбрать данные')}</summary><p class="hint">${t('Сейчас:')} ${e(displayValue(old.status))} ${completedText(old.completed_at)}</p><div class="mergeFields">${mergeFields.map(field=>`<label class="check"><input type="checkbox" data-library-field="${i}" value="${field}" ${choice.fields.includes(field)?'checked':''}>${t(mergeLabels[field])}<small>${e(field==='image'?(x.image?'✓':'—'):x[field]||'—')}</small></label>`).join('')}</div><label class="check"><input type="checkbox" data-library-overwrite="${i}" ${choice.overwrite?'checked':''}>${t('Заменить заполненные поля')}</label><p class="hint">${t('Без замены заполняются только пустые поля; теги объединяются. Избранное и ручной порядок сохраняются.')}</p></details>`:''}</div>`;}).join('')||`<p class="hint">${t(libraryNewOnly?'Новых игр нет':'Ничего не найдено')}</p>`;
  $('libraryRows').querySelectorAll('[data-library-select]').forEach(c=>c.onchange=()=>{const i=Number(c.dataset.librarySelect);c.checked?librarySelected.add(i):librarySelected.delete(i);if(c.checked&&libraryItems[i].existing_id&&!libraryChoices[i])libraryChoices[i]={fields:['status','completed_at','tags'],overwrite:false};updateLibraryCount();});
  $('libraryRows').querySelectorAll('[data-library-field],[data-library-overwrite]').forEach(c=>c.onchange=()=>{const i=Number(c.dataset.libraryField??c.dataset.libraryOverwrite);const choice=libraryChoices[i]||{fields:['status','completed_at','tags'],overwrite:false};if(c.dataset.libraryField!==undefined)choice.fields=c.checked?[...new Set([...choice.fields,c.value])]:choice.fields.filter(x=>x!==c.value);else choice.overwrite=c.checked;libraryChoices[i]=choice;librarySelected.add(i);const select=$('libraryRows').querySelector(`[data-library-select="${i}"]`);if(select)select.checked=true;updateLibraryCount();});updateLibraryCount();
}
function updateLibraryCount(){$('librarySelectedCount').textContent=t('Выбрано: ')+librarySelected.size;$('libraryApply').disabled=libraryLoading||!librarySelected.size;}
const settingsBeforeRelay=renderSettings;
renderSettings=function(){
  settingsBeforeRelay();
  const nav=$('settingsContent').querySelector('.settingsTabs'),tab=document.createElement('button'),panel=document.createElement('section');
  tab.id='steamSourceTab';tab.textContent=t('Источники');tab.setAttribute('role','tab');tab.setAttribute('aria-controls','steamSourcePanel');tab.setAttribute('aria-selected','false');tab.tabIndex=-1;nav.append(tab);
  panel.id='steamSourcePanel';panel.className='settingsSection';panel.hidden=true;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);
  panel.innerHTML=`<h3>Steam</h3><p class="hint">${t('Публичная библиотека Steam загружается через Cloudflare. Общий ключ хранится в Cloudflare Secrets и не включён в приложение. При импорте можно использовать личный API key.')}</p>`;$('settingsContent').append(panel);
  nav.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{panel.hidden=button!==tab;tab.setAttribute('aria-selected',String(button===tab));tab.tabIndex=button===tab?0:-1;if(button===tab){activeSettingsTab='sources';nav.querySelectorAll('button').forEach(b=>{b.setAttribute('aria-selected',String(b===tab));b.tabIndex=b===tab?0:-1;});$('settingsContent').querySelectorAll('.settingsSection').forEach(s=>s.hidden=s!==panel);}}));
  nav.onkeydown=event=>{const tabs=[...nav.querySelectorAll('[role=tab]')],index=tabs.indexOf(document.activeElement);if(index<0)return;let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();tabs[next].click();tabs[next].focus();};
  if(activeSettingsTab==='sources')tab.click();
};
// Explain the optional key after switching to Steam without changing the HLTB flow.
const openBeforeRelay=openRemoteLibrary;
openRemoteLibrary=function(){
  openBeforeRelay();
  if(libraryLoading)return;
  const select=$('libraryProvider'),original=select.onchange;
  select.onchange=()=>{original();if(select.value==='steam'){$('libraryProfile').placeholder='https://steamcommunity.com/id/…';if(preferences.steam_relay_url){$('librarySteamKey').placeholder=t('Личный API key (необязательно)');$('libraryHelp').textContent=t('Можно оставить ключ пустым: список загрузится через настроенный Steam-сервис.');}}else $('libraryProfile').placeholder='https://howlongtobeat.com/user/…';};
};
libraryButton.onclick=()=>openRemoteLibrary();
libraryDialog.addEventListener('click',event=>{if(event.target===libraryDialog){const r=libraryDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)libraryDialog.close();}});
