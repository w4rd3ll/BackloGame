'use strict';
const markedGames=new Set();
let editingBatch=false;
const mainPane=document.querySelector('main');
const workspace=document.querySelector('.workspace');
let panelWidths={};
try{panelWidths=JSON.parse(localStorage.getItem('myGamesPanels')||'{}');}catch{}
const originalApplyPanels=applyPanels;
applyPanels=function(){originalApplyPanels();for(const [key,value] of Object.entries(panelWidths))if(['left','right'].includes(key)&&Number.isFinite(value))workspace.style.setProperty('--'+key+'-width',((key==='left'?sidebarCollapsed:inspectorCollapsed)?0:value)+'px');};

function offerUndo(key){
  toast(t("Игра удалена"));
  clearTimeout(toastTimer);
  const button=document.createElement('button');button.textContent=t("Вернуть");button.className='undoButton';
  $('toast').append(' ',button);
  button.onclick=()=>busy(button,async()=>{await api('/api/undo-delete',{undo:key});await reload();toast(t("Игра восстановлена"));});
  toastTimer=setTimeout(()=>$('toast').hidden=true,60000);
}
async function quickUpdate(ids,patch){
  if(editingBatch)return false;
  if(dirty&&ids.includes(selectedId)){toast(t("Сначала сохрани изменения в открытой карточке"),true);return false;}
  editingBatch=true;
  try{await api('/api/bulk',{ids,patch});await reload();if(ids.includes(selectedId))renderInspector();toast(t("Изменения сохранены"));return true;}
  catch(err){toast(err.message,true);return false;}finally{editingBatch=false;}
}
function favoriteAction(game){return quickUpdate([game.id],{favorite:!game.favorite});}
const oldRender=render;
render=function(){
  const scroll=mainPane.scrollTop;const initial=!render.didRestoreScroll;render.didRestoreScroll=true;
  oldRender();
  for(const id of markedGames)if(!games.some(g=>g.id===id))markedGames.delete(id);
  $('games').querySelectorAll('.game').forEach(row=>{
    const id=Number(row.dataset.id),game=games.find(g=>g.id===id);
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='gameCheck';checkbox.checked=markedGames.has(id);checkbox.setAttribute('aria-label',t("Выбрать ")+game.title);checkbox.draggable=false;
    checkbox.onchange=()=>{checkbox.checked?markedGames.add(id):markedGames.delete(id);row.classList.toggle('batchSelected',checkbox.checked);updateBatchBar();};
    const star=document.createElement('button');star.type='button';star.className='gameStar';star.textContent=game.favorite?'★':'☆';star.title=game.favorite?t("Убрать из избранного"):t("Добавить в избранное");star.setAttribute('aria-label',star.title+': '+game.title);star.setAttribute('aria-pressed',String(!!game.favorite));star.draggable=false;star.onclick=()=>favoriteAction(game);
    row.prepend(checkbox);
    if(viewMode==='compact')row.querySelector('.compactTitle').before(star);else{const heading=row.querySelector('h3');heading.title=game.title;heading.prepend(star);}
    row.classList.toggle('batchSelected',markedGames.has(id));
    row.onkeydown=event=>{if(event.target!==row)return;if(event.key==='Enter'||event.key===' '){event.preventDefault();selectGame(id);}};
  });
  updateBatchBar();renderColumnHeaders();
  mainPane.scrollTop=initial?(Number(localStorage.getItem('myGamesScroll'))||0):scroll;
};
const batchBar=document.createElement('div');batchBar.id='batchBar';batchBar.className='batchBar';
batchBar.innerHTML=`<label class="check"><input id="markVisible" type="checkbox"> ${t("Выбрать видимые")}</label><span id="markedCount"></span><button id="batchEdit">${t("Изменить выбранные")}</button><button id="unmarkAll" class="text">${t("Снять выделение")}</button>`;
$('games').before(batchBar);
$('markVisible').onchange=()=>{for(const g of filteredGames())$('markVisible').checked?markedGames.add(g.id):markedGames.delete(g.id);render();};
$('unmarkAll').onclick=()=>{markedGames.clear();render();};
function updateBatchBar(){refreshFixedLabels();const visible=filteredGames();const count=visible.filter(g=>markedGames.has(g.id)).length;$('markVisible').checked=visible.length>0&&count===visible.length;$('markVisible').indeterminate=count>0&&count<visible.length;$('markedCount').textContent=t("Выбрано: ")+markedGames.size;$('batchEdit').disabled=!markedGames.size;$('unmarkAll').hidden=!markedGames.size;}
const columnHeaders=document.createElement('div');columnHeaders.className='compactHeaders';columnHeaders.setAttribute('aria-label',t("Сортировка списка"));$('games').before(columnHeaders);
function renderColumnHeaders(){columnHeaders.hidden=viewMode!=='compact';columnHeaders.innerHTML='<span></span><span></span><span></span>'+[['title',t("Название")],['platform',t("Платформа")],['status',t("Статус")]].map(([key,label])=>`<button data-sort="${key}">${label}${$('sortField').value===key?(direction===1?' ↑':' ↓'):''}</button>`).join('');columnHeaders.querySelectorAll('button').forEach(b=>b.onclick=()=>{if($('sortField').value===b.dataset.sort)direction*=-1;else{$('sortField').value=b.dataset.sort;direction=1;}render();persistView();});}

const editDialog=document.createElement('dialog');editDialog.id='batchDialog';document.body.append(editDialog);
$('batchEdit').onclick=()=>{
  editDialog.innerHTML=`<div class="dialogHead"><h2>${t("Изменить")} ${markedGames.size} ${t("игр")}</h2><button type="button" id="closeBatch" aria-label="${t("Закрыть")}">✕</button></div><p class="hint">${t("Заполненные поля применятся ко всем выбранным играм.")}</p><form id="batchForm"><label>${t("Статус")}<select name="status"><option value="">${t("Не менять")}</option>${statuses.map(s=>`<option value="${e(s)}">${e(displayValue(s))}</option>`).join('')}</select></label><label>${t("Платформа")}<input name="platform" list="platformOptions" placeholder="${t("Не менять")}"></label><label>${t("Избранное")}<select name="favorite"><option value="">${t("Не менять")}</option><option value="yes">${t("Добавить в избранное")}</option><option value="no">${t("Убрать из избранного")}</option></select></label><button class="primary">${t("Применить")}</button></form>`;
  $('closeBatch').onclick=()=>editDialog.close();
  $('batchForm').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target)),patch={};if(data.status)patch.status=data.status;if(data.platform.trim())patch.platform=data.platform.trim();if(data.favorite)patch.favorite=data.favorite==='yes';if(!Object.keys(patch).length){toast(t("Выбери, что изменить"));return;}if(await quickUpdate([...markedGames],patch))editDialog.close();};
  editDialog.showModal();
};
const quickMenu=document.createElement('div');quickMenu.id='quickMenu';quickMenu.className='coverMenu';quickMenu.hidden=true;document.body.append(quickMenu);
document.addEventListener('contextmenu',event=>{
  const row=event.target.closest('.game');if(!row)return;
  event.preventDefault();hideCoverMenu();const game=games.find(g=>g.id===Number(row.dataset.id));
  quickMenu.innerHTML=`<button id="quickFavorite">${game.favorite?t("☆ Убрать из избранного"):t("★ Добавить в избранное")}</button><label>${t("Статус")}<select id="quickStatus">${statuses.map(s=>`<option value="${e(s)}" ${s===game.status?'selected':''}>${e(displayValue(s))}</option>`).join('')}</select></label><label>${t("Платформа")}<select id="quickPlatform">${availablePlatforms().map(s=>`<option value="${e(s)}" ${s===(game.platform||'Пока неизвестно')?'selected':''}>${e(displayValue(s))}</option>`).join('')}</select></label>${cropArtwork(game).src?`<button id="quickCrop">${t("Выбрать миниатюру")}</button>`:''}`;
  quickMenu.hidden=false;quickMenu.style.left=Math.max(8,Math.min(event.clientX,innerWidth-quickMenu.offsetWidth-8))+'px';quickMenu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-quickMenu.offsetHeight-8))+'px';
  const close=()=>quickMenu.hidden=true;
  $('quickFavorite').onclick=()=>{close();favoriteAction(game);};
  $('quickStatus').onchange=()=>{const status=$('quickStatus').value;close();quickUpdate([game.id],{status});};
  $('quickPlatform').onchange=()=>{const platform=$('quickPlatform').value;close();quickUpdate([game.id],{platform});};
  if($('quickCrop'))$('quickCrop').onclick=()=>{close();openCrop(game);};
});
document.addEventListener('click',event=>{if(!event.target.closest('#quickMenu'))quickMenu.hidden=true;});
document.addEventListener('keydown',event=>{if(event.key==='Escape')quickMenu.hidden=true;});
document.addEventListener('scroll',()=>quickMenu.hidden=true,true);

for(const side of ['left','right']){
  const pane=$(side==='left'?'sidebar':'inspector');
  const handle=document.createElement('div');handle.className='panelResizer '+side;handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-label',side==='left'?t("Ширина левой панели"):t("Ширина правой панели"));pane.append(handle);
  function resize(width){panelWidths[side]=Math.round(Math.max(side==='left'?180:280,Math.min(width,Math.min(side==='left'?400:650,innerWidth*.45))));applyPanels();handle.setAttribute('aria-valuenow',String(panelWidths[side]));localStorage.setItem('myGamesPanels',JSON.stringify(panelWidths));}
  handle.onpointerdown=event=>{event.preventDefault();handle.setPointerCapture(event.pointerId);const start=event.clientX,width=pane.getBoundingClientRect().width;handle.onpointermove=move=>resize(width+(side==='left'?1:-1)*(move.clientX-start));handle.onpointerup=()=>{handle.onpointermove=null;document.body.classList.remove('resizing');};document.body.classList.add('resizing');};
  handle.onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();resize(pane.getBoundingClientRect().width+(event.key==='ArrowRight'?1:-1)*(side==='left'?1:-1)*10);};
  // Inspector contents are rebuilt, so keep its divider on the workspace instead.
  if(side==='right'){workspace.append(handle);handle.classList.add('workspaceResizer');}
}
const oldSettings=renderSettings;
renderSettings=function(){
  oldSettings();
  const nav=$('settingsContent').querySelector('.settingsTabs');
  const b=document.createElement('button');b.textContent=t("Резервные копии");b.setAttribute('role','tab');b.id='backupTab';b.setAttribute('aria-controls','backupPanel');b.setAttribute('aria-selected','false');nav.append(b);
  const panel=document.createElement('section');panel.id='backupPanel';panel.className='settingsSection';panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby','backupTab');panel.hidden=true;
  panel.innerHTML=`<h3>${t("Резервные копии")}</h3><p class="hint">${t("Автоматическая копия перед первым изменением за день. Храним последние 10 копий, включая ручные. Библиотека, настройки и сохранённые обложки входят в ZIP. Перед восстановлением сохраняется текущее состояние.")}</p><div class="settingsRow"><button id="createBackup">${t("Создать копию")}</button><button id="downloadFullBackup">${t("Экспорт полной копии")}</button><button id="uploadBackup">${t("Восстановить из файла")}</button><input id="backupFile" type="file" accept=".zip,application/zip" hidden></div><div id="backupList"></div>`;
  $('settingsContent').append(panel);
  nav.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{panel.hidden=button!==b;b.setAttribute('aria-selected',String(button===b));if(button===b){activeSettingsTab='backups';nav.querySelectorAll('button').forEach(x=>{x.setAttribute('aria-selected',String(x===b));x.tabIndex=x===b?0:-1;});$('settingsContent').querySelectorAll('.settingsSection').forEach(x=>x.hidden=x!==panel);loadBackups();}}));
  async function loadBackups(){try{const data=await api('/api/backups');$('backupList').innerHTML=data.items.length?data.items.map(x=>`<div class="backupRow"><span>${e(x.name.replace(/^library-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-\d+\.zip$/, '$3.$2.$1 $4:$5:$6'))}<small>${(x.size/1048576).toFixed(1)} ${t("МБ")}</small></span><a href="/api/backup-download?name=${encodeURIComponent(x.name)}" download>${t("Скачать")}</a><button data-restore="${e(x.name)}">${t("Восстановить")}</button></div>`).join(''):`<p class="hint">${t("Копий пока нет.")}</p>`; $('backupList').querySelectorAll('[data-restore]').forEach(button=>button.onclick=()=>restoreAction(()=>api('/api/backup-restore',{name:button.dataset.restore}),button));}catch(err){toast(err.message,true);}}
  async function restoreAction(action,button){if(dirty){toast(t("Сначала сохрани изменения в карточке"),true);return;}if(!confirm(t("Заменить текущую библиотеку этой копией? Перед восстановлением будет создана копия текущего состояния.")))return;await busy(button,async()=>{await action();markedGames.clear();selectedId=null;await reload();renderInspector();await loadBackups();toast(t("Библиотека восстановлена"));});}
  $('createBackup').onclick=()=>busy($('createBackup'),async()=>{await api('/api/backup-create',{});await loadBackups();toast(t("Резервная копия создана"));});
  $('downloadFullBackup').onclick=()=>busy($('downloadFullBackup'),async()=>{const result=await api('/api/backup-create',{});const a=document.createElement('a');a.href='/api/backup-download?name='+encodeURIComponent(result.name);a.download=result.name;a.click();await loadBackups();});
  $('uploadBackup').onclick=()=>$('backupFile').click();
  $('backupFile').onchange=async()=>{const file=$('backupFile').files[0];if(!file)return;if(file.size>200000000){toast(t("Максимальный размер — 200 МБ"),true);return;}await restoreAction(async()=>{const response=await fetch('/api/backup-upload',{method:'POST',headers:{'X-Library-Token':token,'Content-Type':'application/zip'},body:file});const result=await response.json();if(!response.ok)throw new Error(t(result.error));},$('uploadBackup'));$('backupFile').value='';};
  const allTabs=[...nav.querySelectorAll('button')];allTabs.forEach((button,index)=>button.onkeydown=event=>{let next;if(event.key==='ArrowRight')next=(index+1)%allTabs.length;else if(event.key==='ArrowLeft')next=(index+allTabs.length-1)%allTabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=allTabs.length-1;else return;event.preventDefault();allTabs[next].click();allTabs[next].focus();});
  if(activeSettingsTab==='backups')b.click();
};
// Remember the reading position across re-renders and application restarts.
let scrollTimer;
mainPane.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>{try{localStorage.setItem('myGamesScroll',String(mainPane.scrollTop));}catch{}},150);});
const firstReload=reload;
reload=async function(){await firstReload();if(!reload.restored){reload.restored=true;try{mainPane.scrollTop=Number(localStorage.getItem('myGamesScroll'))||0;}catch{}}};

function refreshFixedLabels(){
  const label=$('markVisible').parentElement;
  // This label contains a checkbox; update only its label text.
  if(label.lastChild.nodeType===3)label.lastChild.textContent=' '+t('Выбрать видимые');
  $('batchEdit').textContent=t('Изменить выбранные');$('unmarkAll').textContent=t('Снять выделение');
  columnHeaders.setAttribute('aria-label',t('Сортировка списка'));
  document.querySelectorAll('.panelResizer').forEach(node=>node.setAttribute('aria-label',t(node.classList.contains('left')?'Ширина левой панели':'Ширина правой панели')));
}
