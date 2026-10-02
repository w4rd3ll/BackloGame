'use strict';
const shareDialog=document.createElement('dialog');
shareDialog.id='shareDialog';
document.body.append(shareDialog);
function openSharing(){
  const selected=filteredGames().map(game=>game.id);
  if(!selected.length){toast(t('Нет игр для отправки'),true);return;}
  let saving=false;
  shareDialog.innerHTML=`<div class="dialogHead"><h2>${t('Поделиться списком')}</h2><button id="closeSharing" aria-label="${t('Закрыть')}">✕</button></div><form id="shareForm"><label>${t('Название списка')}<input id="shareTitle" value="${e($('viewTitle').textContent)}" maxlength="200" required></label><p class="hint">${t('Игр в файле:')} ${selected.length}. ${t('Учитываются текущие фильтры и порядок игр.')}</p><label class="check"><input id="shareCovers" type="checkbox" checked>${t('Включить обложки')}</label><p class="hint">${t('Обложки уменьшаются для отправки; оригиналы сохраняются.')}</p><label class="check"><input id="shareNotes" type="checkbox">${t('Включить мои заметки')}</label><p class="hint">${t('Один HTML-файл — открывается без интернета и установки программы.')}</p><p id="shareResult" class="hint" role="status"></p><div class="detailActions"><button type="button" id="cancelSharing">${t('Отмена')}</button><button class="primary" id="saveSharing">${t('Сохранить HTML')}</button></div></form>`;
  const close=()=>{if(!saving)shareDialog.close();};
  $('closeSharing').onclick=close;$('cancelSharing').onclick=close;
  shareDialog.oncancel=event=>{if(saving)event.preventDefault();};
  shareDialog.onclick=event=>{if(event.target===shareDialog){const rect=shareDialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)close();}};
  $('shareForm').onsubmit=async event=>{
    event.preventDefault();if(saving)return;
    saving=true;shareDialog.querySelectorAll('input,button').forEach(control=>control.disabled=true);
    $('shareResult').textContent=t('Готовим файл…');
    try{
      const result=await api('/api/share',{ids:selected,title:$('shareTitle').value.trim(),language:uiLanguage,covers:$('shareCovers').checked,notes:$('shareNotes').checked});
      const url=URL.createObjectURL(new Blob([result.html],{type:'text/html;charset=utf-8'}));
      const link=document.createElement('a');link.href=url;link.download=result.filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
      $('shareResult').textContent=t('Файл готов. Передай его другу.')+` ${t('Размер файла:')} ${(new Blob([result.html]).size/1048576).toFixed(1)} ${t('МБ')}.`+(result.missing_covers?` ${t('Без сохранённой обложки:')} ${result.missing_covers}.`:'');
    }catch(error){$('shareResult').textContent=t(error.message);}
    finally{saving=false;shareDialog.querySelectorAll('input,button').forEach(control=>control.disabled=false);}
  };
  shareDialog.showModal();
}
$('shareButton').onclick=openSharing;
