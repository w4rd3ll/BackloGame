'use strict';
let updateStatus=null,updatePoll=null;
function updateMessage(state){
  if(state.state==='checking')return t('Проверяем обновления…');
  if(state.state==='downloading')return t('Скачивание…')+' '+Math.round(state.downloaded/Math.max(1,state.total)*100)+'%';
  if(state.state==='ready')return t('Обновление скачано и проверено.');
  if(state.state==='error')return t(state.error);
  if(state.available)return t('Доступна новая версия: ')+state.latest;
  return state.state==='checked'?t('Установлена актуальная версия.'):t('Обновления ещё не проверялись.');
}
function drawUpdateStatus(){
  if(!$('updateState')||!updateStatus)return;
  const state=updateStatus,working=['checking','downloading'].includes(state.state);
  $('updateVersion').textContent=t('Текущая версия: ')+state.current;
  $('updateState').textContent=updateMessage(state);
  if(state.previous_failed)$('updateState').textContent+=' '+t('Предыдущее обновление не установилось. Старая версия восстановлена; можно повторить попытку.');
  $('updateNotes').textContent=state.notes||'';
  $('updateRelease').href=state.url;
  $('checkUpdates').disabled=working;
  $('downloadUpdate').hidden=!state.available||!state.verified||state.state==='ready';
  $('downloadUpdate').disabled=working;
  $('installUpdate').hidden=state.state!=='ready'||!state.can_install;
  $('updateBrowserHint').hidden=state.state!=='ready'||state.can_install;
}
async function pollUpdate(notify=false){
  clearTimeout(updatePoll);
  try{
    updateStatus=await api('/api/updates');drawUpdateStatus();
    if(['checking','downloading'].includes(updateStatus.state))updatePoll=setTimeout(()=>pollUpdate(notify),700);
    else if(notify&&updateStatus.available)toast(t('Доступна новая версия: ')+updateStatus.latest);
  }catch(error){if($('updateState'))$('updateState').textContent=error.message;}
}
const settingsBeforeUpdates=renderSettings;
renderSettings=function(){
  settingsBeforeUpdates();
  const nav=$('settingsContent').querySelector('.settingsTabs'),tab=document.createElement('button'),panel=document.createElement('section');
  tab.textContent=t('Обновления');tab.id='updatesTab';tab.type='button';tab.setAttribute('role','tab');tab.setAttribute('aria-controls','updatesPanel');tab.setAttribute('aria-selected','false');tab.tabIndex=-1;
  panel.id='updatesPanel';panel.className='settingsSection';panel.hidden=true;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);
  panel.innerHTML=`<h3>${t('Обновления программы')}</h3><p id="updateVersion"></p><label class="check"><input id="autoCheckUpdates" type="checkbox" ${preferences.auto_check_updates!==false?'checked':''}>${t('Проверять обновления при запуске')}</label><p class="hint">${t('Новые версии загружаются с GitHub. Установка запускается вручную; база, обложки и настройки сохраняются. Хранится одна предыдущая версия программы.')}</p><div class="detailActions"><button id="checkUpdates">${t('Проверить обновления')}</button><button id="downloadUpdate" hidden>${t('Скачать обновление')}</button><button id="installUpdate" class="primary" hidden>${t('Установить и перезапустить')}</button><a id="updateRelease" href="https://github.com/w4rd3ll/BackloGame/releases" target="_blank" rel="noopener">${t('Релизы на GitHub')}</a></div><p id="updateState" role="status"></p><p id="updateBrowserHint" class="hint" hidden>${t('Автоустановка доступна в портативном Windows-приложении. В браузере скачанный архив проверен, но код программы не заменяется.')}</p><pre id="updateNotes" class="releaseNotes"></pre>`;
  nav.append(tab);$('settingsContent').append(panel);
  nav.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{
    panel.hidden=button!==tab;tab.setAttribute('aria-selected',String(button===tab));tab.tabIndex=button===tab?0:-1;
    if(button===tab){activeSettingsTab='updates';nav.querySelectorAll('button').forEach(item=>{item.setAttribute('aria-selected',String(item===tab));item.tabIndex=item===tab?0:-1;});$('settingsContent').querySelectorAll('.settingsSection').forEach(item=>item.hidden=item!==panel);pollUpdate();}
  }));
  nav.onkeydown=event=>{const tabs=[...nav.querySelectorAll('[role=tab]')],index=tabs.indexOf(document.activeElement);let next;if(index<0)return;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();tabs[next].click();tabs[next].focus();};
  $('autoCheckUpdates').onchange=async event=>{const control=event.target;control.disabled=true;try{preferences=await api('/api/settings',{auto_check_updates:control.checked});}catch(error){control.checked=!control.checked;toast(error.message,true);}finally{control.disabled=false;}};
  for(const [id,action] of [['checkUpdates','check'],['downloadUpdate','download']])$(id).onclick=()=>busy($(id),async()=>{updateStatus=await api('/api/updates/'+action,{});drawUpdateStatus();pollUpdate();});
  $('installUpdate').onclick=()=>{if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}busy($('installUpdate'),()=>api('/api/updates/install',{}));};
  if(activeSettingsTab==='updates')tab.click();else drawUpdateStatus();
};
let updateStartupAttempts=0;
async function checkUpdatesOnStartup(){
  if(!token){if(++updateStartupAttempts<60)setTimeout(checkUpdatesOnStartup,500);return;}
  if(preferences.auto_check_updates===false)return;
  try{updateStatus=await api('/api/updates/check',{});pollUpdate(true);}catch{}
}
setTimeout(checkUpdatesOnStartup,500);
