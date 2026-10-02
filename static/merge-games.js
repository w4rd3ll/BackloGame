'use strict';
const mergeDialog=document.createElement('dialog');mergeDialog.className='mergeDialog';document.body.append(mergeDialog);
const mergeButton=document.createElement('button');mergeButton.id='mergeGames';mergeButton.disabled=true;$('batchEdit').after(mergeButton);
const batchBeforeMerge=updateBatchBar;
updateBatchBar=function(){batchBeforeMerge();mergeButton.textContent=t('Объединить');mergeButton.disabled=markedGames.size!==2;mergeButton.title=t('Выбери ровно две карточки одной игры');};
updateBatchBar();
mergeButton.onclick=async()=>{
  if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}
  const ids=[...markedGames],selected=ids.map(id=>games.find(g=>g.id===id));if(ids.length!==2||selected.some(g=>!g))return;
  const option=g=>`<option value="${g.id}">${e(g.title)} · ${e(displayValue(g.platform))} · ${e(displayValue(g.status))}</option>`;
  mergeDialog.innerHTML=`<div class="dialogHead"><h2>${t('Объединить карточки')}</h2><button id="closeMerge" aria-label="${t('Закрыть')}">✕</button></div><p class="hint">${t('Объединяй только одну и ту же игру. Разные издания могут отличаться.')}</p><div class="mergeChoices"><label>${t('Основная карточка: название, описание и обложка')}<select id="mergePrimary">${selected.map(option).join('')}</select></label><label>${t('Текущие платформа и статус')}<select id="mergeCurrent">${selected.map(option).join('')}</select></label></div><div id="mergeResult" role="status"></div><div class="detailActions"><button id="cancelMerge">${t('Отмена')}</button><button id="applyMerge" class="primary" disabled>${t('Объединить')}</button></div>`;
  $('mergeCurrent').value=String((selected.find(g=>g.status!=='Пройдено')||selected[1]).id);
  let version=0,preview=null,applying=false;
  const close=()=>{if(!applying)mergeDialog.close();};$('closeMerge').onclick=close;$('cancelMerge').onclick=close;
  mergeDialog.oncancel=event=>{if(applying)event.preventDefault();};
  mergeDialog.onclick=event=>{if(event.target===mergeDialog){const r=mergeDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}};
  async function refresh(){
    const revision=++version;preview=null;$('applyMerge').disabled=true;$('mergeResult').textContent=t('Загрузка…');
    try{
      const result=await api('/api/merge-preview',{ids,primary:Number($('mergePrimary').value),current:Number($('mergeCurrent').value)});if(revision!==version)return;
      preview=result;const g=result.game;
      $('mergeResult').innerHTML=`<div class="mergePreview">${g.image_local||g.image?`<img src="${e(g.image_local||g.image)}" alt="" referrerpolicy="no-referrer">`:''}<div><h3>${e(g.title)}</h3><p>${e(displayValue(g.platform))} · ${e(displayValue(g.status))}</p><p>${g.favorite?'★ '+t('Избранное'):''}</p></div></div><h3>${t('История прохождений')}</h3><div class="mergeHistory">${g.playthroughs.map(row=>`<p>${completedText(row.date)} · ${e(displayValue(row.platform))}</p>`).join('')||`<p class="hint">${t('Дат прохождения пока нет')}</p>`}</div>${g.notes?`<h3>${t('Моя заметка')}</h3><p class="mergeNotes">${e(g.notes)}</p>`:''}<p class="hint">${t('Заметки, теги, серии и история объединяются. Исходные данные обеих карточек сохраняются в архиве; перед объединением создаётся резервная копия.')}</p>`;
      $('applyMerge').disabled=false;
    }catch(err){if(revision===version)$('mergeResult').textContent=t(err.message);}
  }
  $('mergePrimary').onchange=refresh;$('mergeCurrent').onchange=refresh;
  $('applyMerge').onclick=async()=>{
    if(!preview||applying)return;applying=true;mergeDialog.querySelectorAll('button,select').forEach(x=>x.disabled=true);
    try{
      const result=await api('/api/merge',{ids,primary:Number($('mergePrimary').value),current:Number($('mergeCurrent').value),signature:preview.signature});markedGames.clear();dirty=false;selectedId=result.id;mergeDialog.close();await reload();renderInspector();
      toast(t('Карточки объединены'));clearTimeout(toastTimer);const undo=document.createElement('button');undo.textContent=t('Отменить объединение');$('toast').append(' ',undo);
      undo.onclick=async()=>{if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}await busy(undo,async()=>{await api('/api/merge-undo',{undo:result.undo});await reload();renderInspector();toast(t('Объединение отменено'));});};
      toastTimer=setTimeout(()=>$('toast').hidden=true,600000);
    }catch(err){toast(t(err.message),true);mergeDialog.querySelectorAll('button,select').forEach(x=>x.disabled=false);await refresh();}
    finally{applying=false;}
  };
  mergeDialog.showModal();await refresh();
};
const inspectorBeforeMerge=renderInspector;
renderInspector=function(){
  inspectorBeforeMerge();const g=games.find(x=>x.id===selectedId),form=$('detailForm');if(!form||!g?.merge_archive?.length)return;
  const archive=document.createElement('details');archive.className='mergeArchive';
  archive.innerHTML=`<summary>${t('Исходные карточки')} (${g.merge_archive.length})</summary>`+g.merge_archive.map(row=>`<section><strong>${e(row.title)}</strong><p class="hint">${e(displayValue(row.platform))} · ${e(displayValue(row.status))}</p>${/^https?:\/\//.test(row.source_url||'')?`<a href="${e(row.source_url)}" target="_blank" rel="noopener noreferrer">${t('Источник')} ↗</a>`:''}${row.description?`<details><summary>${t('Описание')}</summary><p class="mergeNotes">${e(row.description)}</p></details>`:''}${row.notes?`<p class="mergeNotes">${e(row.notes)}</p>`:''}</section>`).join('');form.querySelector('.completionHistory').after(archive);
};
