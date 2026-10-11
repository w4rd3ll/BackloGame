'use strict';
const coverUploadDialog=document.createElement('dialog');coverUploadDialog.className='coverUploadDialog';document.body.append(coverUploadDialog);
function openCoverUpload(game) {
  if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}
  if(catalogBatchRunning||coversUpdating){toast(t('Дождись обновления каталога'),true);return;}
  let saving=false,previewUrl='';
  const releasePreview=()=>{if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl='';}};
  coverUploadDialog.innerHTML=`<div class="dialogHead"><div><h2>${t('Загрузить свою обложку')}</h2><p class="hint">${e(game.title)}</p></div><button id="closeCoverUpload" aria-label="${t('Закрыть')}">✕</button></div><form id="coverUploadForm"><label>${t('Формат обложки')}<select id="coverUploadOrientation"><option value="portrait">${t('Вертикальная')}</option><option value="landscape">${t('Горизонтальная')}</option></select></label><label>${t('Файл обложки')}<input id="coverUploadFile" type="file" accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"></label><p class="hint">PNG, JPEG, GIF, WebP · ${preferences.cover_max_mb||64} ${t('МБ')}</p><div class="settingsRow"><button id="applyCoverUpload" class="primary" disabled>${t('Использовать обложку')}</button><button id="resetCoverUpload" type="button">${t('Вернуть исходную обложку')}</button></div><p id="coverUploadStatus" role="status"></p><img id="coverUploadPreview" alt="${t('Предпросмотр')}" hidden></form>`;
  const close=()=>{if(!saving)coverUploadDialog.close();};
  coverUploadDialog.onclose=releasePreview;coverUploadDialog.oncancel=event=>{if(saving)event.preventDefault();};wireDialogBackdrop(coverUploadDialog,close);
  $('closeCoverUpload').onclick=close;
  const update=()=>{
    $('applyCoverUpload').disabled=saving||!$('coverUploadFile').files[0];
    $('resetCoverUpload').disabled=saving||!games.find(g=>g.id===game.id)?.custom_covers?.[$('coverUploadOrientation').value];
  };
  $('coverUploadOrientation').onchange=update;
  $('coverUploadFile').onchange=()=>{
    releasePreview();const file=$('coverUploadFile').files[0];$('coverUploadStatus').textContent='';
    $('coverUploadPreview').hidden=!file;
    if(file){previewUrl=URL.createObjectURL(file);$('coverUploadPreview').src=previewUrl;}
    update();
  };
  const lock=value=>{saving=value;coverUploadDialog.querySelectorAll('input,select,button').forEach(control=>control.disabled=value);if(!value)update();};
  $('coverUploadForm').onsubmit=async event=>{
    event.preventDefault();const file=$('coverUploadFile').files[0];if(!file||saving)return;
    const limit=preferences.cover_max_mb||64;
    if(file.size>limit*1024*1024){$('coverUploadStatus').textContent=t('Обложка больше {size} МБ').replace('{size}',limit);return;}
    const orientation=$('coverUploadOrientation').value;lock(true);$('coverUploadStatus').textContent=t('Подождите…');
    try {
      const response=await fetch(`/api/covers/upload?id=${game.id}&orientation=${orientation}`,{method:'POST',headers:{'X-Library-Token':token,'Content-Type':'application/octet-stream'},body:file});
      const result=await response.json();if(!response.ok)throw new Error(t(result.error)||t('Ошибка запроса'));
      await reload();renderInspector();$('coverUploadStatus').textContent=t('Обложка сохранена');toast(t('Обложка сохранена'));
    } catch(error) {$('coverUploadStatus').textContent=error.message;toast(error.message,true);}
    finally {lock(false);}
  };
  $('resetCoverUpload').onclick=async()=>{
    if(saving)return;lock(true);
    try {await api('/api/steamgriddb/reset',{id:game.id,orientation:$('coverUploadOrientation').value});await reload();renderInspector();$('coverUploadStatus').textContent=t('Исходная обложка восстановлена');}
    catch(error){$('coverUploadStatus').textContent=error.message;}
    finally{lock(false);}
  };
  update();coverUploadDialog.showModal();
}
const inspectorBeforeCoverUpload=renderInspector;
renderInspector=function(){
  inspectorBeforeCoverUpload();const game=games.find(g=>g.id===selectedId),source=$('inspector').querySelector('.detailSource');
  if(!game||!source)return;
  const button=document.createElement('button');button.className='text';button.textContent=t('Загрузить свою обложку');button.onclick=()=>openCoverUpload(game);source.append(button);
};
document.addEventListener('contextmenu',event=>{
  const row=event.target.closest('.game'),image=event.target.closest('[data-cover-id]');
  const game=games.find(g=>g.id===Number(row?.dataset.id||image?.dataset.coverId));if(!game)return;
  const menu=row?quickMenu:$('coverMenu');menu.querySelectorAll('[data-upload-cover]').forEach(button=>button.remove());
  const button=document.createElement('button');button.dataset.uploadCover='yes';button.textContent=t('Загрузить свою обложку');
  button.onclick=()=>{menu.hidden=true;openCoverUpload(game);};menu.append(button);
  menu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-menu.offsetHeight-8))+'px';
  menu.style.left=Math.max(8,Math.min(event.clientX,innerWidth-menu.offsetWidth-8))+'px';
});
