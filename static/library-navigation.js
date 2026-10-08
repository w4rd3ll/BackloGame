'use strict';
const collectionFilterLabels = {
  platformFilter:'Платформа',genreFilter:'Жанр',seriesFilter:'Серия',tagFilter:'Тег',priorityFilter:'Приоритет',
  releaseFrom:'Дата выхода от',releaseTo:'Дата выхода до',addedFrom:'Дата добавления от',addedTo:'Дата добавления до',librarySearch:'Поиск'
};
let selectedCollectionId='', collectionsSaving=false;
function captureCollectionState() {
  return {...Object.fromEntries(Object.keys(collectionFilterLabels).map(id=>[id,$(id).value])),
    unknownRelease:$('unknownRelease').checked,status:statusFilter,sort:$('sortField').value,direction,view:viewMode};
}
function applyCollectionState(state) {
  statusFilter=state.status||'';
  activeCategoryView=statusFilter||'all';
  for(const id of Object.keys(collectionFilterLabels)) {
    const control=$(id),value=state[id]||'';
    // Keep a saved filter even if its last matching game was removed.
    if(control.tagName==='SELECT' && value && ![...control.options].some(o=>o.value===value))control.add(new Option(value,value));
    control.value=value;
  }
  $('unknownRelease').checked=!!state.unknownRelease;
  $('sortField').value=state.sort;direction=state.direction;viewMode=state.view;
  render();persistView();
}
function activeLibraryFilters() {
  const result=[];
  if(statusFilter)result.push({id:'status',label:t('Категория'),value:statusFilter==='favorites'?t('Избранное'):statusFilter==='not-favorites'?t('Не в избранном'):displayValue(statusFilter)});
  for(const [id,label] of Object.entries(collectionFilterLabels))if($(id).value)result.push({id,label:t(label),value:displayValue($(id).value)});
  if($('unknownRelease').checked)result.push({id:'unknownRelease',label:t('Только без даты выхода'),value:''});
  return result;
}
function clearLibraryFilter(id) {
  if(id==='status')statusFilter='';else if(id==='unknownRelease')$(id).checked=false;else $(id).value='';
  render();persistView();
}
function renderLibraryNavigation() {
  const filters=activeLibraryFilters();
  $('activeFilters').innerHTML=filters.map(f=>`<button type="button" class="filterChip" data-clear-filter="${f.id}" title="${e(t('Убрать фильтр'))}">${e(f.label)}${f.value?': '+e(f.value):''} <span aria-hidden="true">×</span></button>`).join('')+(filters.length?`<button type="button" class="text" id="clearAllLibraryFilters">${t('Сбросить всё')}</button>`:'');
  $('activeFilters').hidden=!filters.length;
  $('activeFilters').querySelectorAll('[data-clear-filter]').forEach(button=>button.onclick=()=>clearLibraryFilter(button.dataset.clearFilter));
  if($('clearAllLibraryFilters'))$('clearAllLibraryFilters').onclick=()=>{
    statusFilter='';Object.keys(collectionFilterLabels).forEach(id=>$(id).value='');$('unknownRelease').checked=false;render();persistView();
  };
  const collections=preferences.saved_collections||[];
  if(!collections.some(item=>item.id===selectedCollectionId))selectedCollectionId='';
  $('savedCollection').innerHTML=`<option value="">${t('Выбрать подборку')}</option>`+collections.map(item=>`<option value="${e(item.id)}">${e(item.name)}</option>`).join('');
  $('savedCollection').value=selectedCollectionId;
  $('savedCollection').disabled=collectionsSaving;
  $('saveCollection').disabled=collectionsSaving||collections.length>=100;
  $('updateCollection').disabled=collectionsSaving||!selectedCollectionId;
  $('deleteCollection').disabled=collectionsSaving||!selectedCollectionId;
}
async function storeCollections(items, selection) {
  if(collectionsSaving)return;
  collectionsSaving=true;renderLibraryNavigation();
  try {
    const result=await api('/api/settings',{saved_collections:items});
    preferences={...preferences,saved_collections:result.saved_collections};selectedCollectionId=selection;
    toast(t('Сохранено'));
  } catch(error) {toast(error.message,true);throw error;}
  finally {collectionsSaving=false;renderLibraryNavigation();}
}
const collectionNameDialog=document.createElement('dialog');collectionNameDialog.className='collectionNameDialog';document.body.append(collectionNameDialog);
function openSaveCollection() {
  const state=captureCollectionState();
  collectionNameDialog.innerHTML=`<form id="collectionNameForm"><div class="dialogHead"><h2>${t('Сохранить подборку')}</h2><button type="button" id="closeCollectionName" aria-label="${t('Закрыть')}">✕</button></div><label>${t('Название подборки')}<input id="collectionName" required maxlength="80" autocomplete="off"></label><div class="detailActions"><button class="primary" type="submit">${t('Сохранить')}</button></div></form>`;
  const close=()=>{if(!collectionsSaving)collectionNameDialog.close();};
  $('closeCollectionName').onclick=close;wireDialogBackdrop(collectionNameDialog,close);
  collectionNameDialog.oncancel=event=>{if(collectionsSaving)event.preventDefault();};
  $('collectionNameForm').onsubmit=async event=>{
    event.preventDefault();const name=$('collectionName').value.trim();if(!name||collectionsSaving)return;
    const button=event.submitter;button.disabled=true;
    try {const id=crypto.randomUUID();await storeCollections([...(preferences.saved_collections||[]),{id,name,state}],id);collectionNameDialog.close();}
    catch {} finally {button.disabled=false;}
  };
  collectionNameDialog.showModal();$('collectionName').focus();
}
$('savedCollection').onchange=()=>{
  selectedCollectionId=$('savedCollection').value;
  const item=(preferences.saved_collections||[]).find(x=>x.id===selectedCollectionId);
  if(item)applyCollectionState(item.state);else renderLibraryNavigation();
};
$('saveCollection').onclick=openSaveCollection;
$('updateCollection').onclick=()=>{
  if(!selectedCollectionId||collectionsSaving)return;
  const state=captureCollectionState();
  storeCollections((preferences.saved_collections||[]).map(item=>item.id===selectedCollectionId?{...item,state}:item),selectedCollectionId).catch(()=>{});
};
$('deleteCollection').onclick=()=>{
  if(!selectedCollectionId||collectionsSaving)return;
  storeCollections((preferences.saved_collections||[]).filter(item=>item.id!==selectedCollectionId),'').catch(()=>{});
};
const renderBeforeNavigation=render;
render=function(){renderBeforeNavigation();renderLibraryNavigation();};
renderLibraryNavigation();
let libraryJumpBuffer='',libraryJumpTime=0,libraryJumpTarget=null;
function libraryTypeJump(event) {
  if(event.defaultPrevented||event.ctrlKey||event.altKey||event.metaKey||event.isComposing||event.repeat||document.querySelector('dialog[open]')||event.target?.closest('input,textarea,select,button,[contenteditable]:not([contenteditable="false"]),[role="textbox"]')) {
    libraryJumpBuffer='';return;
  }
  if(event.key==='Escape'){libraryJumpBuffer='';libraryJumpTarget?.classList.remove('keyboardTarget');return;}
  if(event.key.length!==1||!/[\p{L}\p{N}]/u.test(event.key))return;
  const now=Date.now();libraryJumpBuffer=(now-libraryJumpTime>1000?'':libraryJumpBuffer)+event.key;libraryJumpTime=now;
  const prefix=normalizeLibrarySearch(libraryJumpBuffer);
  const game=filteredGames().find(game=>normalizeLibrarySearch(game.title).startsWith(prefix));
  if(!game)return;
  const card=$('games').querySelector(`[data-id="${game.id}"]`);if(!card)return;
  event.preventDefault();libraryJumpTarget?.classList.remove('keyboardTarget');libraryJumpTarget=card;
  card.classList.add('keyboardTarget');card.focus({preventScroll:true});card.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
}
document.addEventListener('keydown',libraryTypeJump);
