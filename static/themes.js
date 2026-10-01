'use strict';
const appThemes = [
  {id:'teal',name:'Бирюзовая',accent:'#50c8bd',bg:'#10171c'},
  {id:'red',name:'Красная',accent:'#ef7779',bg:'#1b1215'},
  {id:'pink',name:'Розовая',accent:'#ed91c5',bg:'#1a121d'},
  {id:'green',name:'Зелёная',accent:'#6bc99b',bg:'#111b17'},
  {id:'yellow',name:'Жёлтая',accent:'#e6c15f',bg:'#1b1911'},
  {id:'blue',name:'Голубая',accent:'#70baf2',bg:'#101923'},
  {id:'purple',name:'Фиолетовая',accent:'#b49af1',bg:'#171322'},
  {id:'mono',name:'Монохромная',accent:'#bec6ce',bg:'#16181b'}
];
function themeMix(a,b,amount){
  const rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
  const first=rgb(a),second=rgb(b);
  return '#'+first.map((value,i)=>Math.round(value+(second[i]-value)*amount).toString(16).padStart(2,'0')).join('');
}
function themePalette(theme){
  const {bg,accent}=theme,mix=amount=>themeMix(bg,accent,amount),light=amount=>themeMix(bg,'#ffffff',amount);
  return {
    bg,panel:light(.025),card:light(.055),line:mix(.19),text:themeMix('#edf3f6',accent,.025),muted:light(.61),accent,
    'accent-bg':mix(.22),'accent-text':themeMix(accent,'#ffffff',.35),'accent-line':accent+'66',
    input:light(.015),button:light(.065),'button-hover':mix(.16),'card-top':light(.065),'card-bottom':light(.04),
    'cover-bg':mix(.12),'cover-from':mix(.17),'cover-to':light(.12),primary:mix(.67),'primary-border':mix(.82),'primary-hover':mix(.78),
    'focus-ring':accent+'26','accent-outline':accent+'66','chip-line':mix(.26),'text-soft':light(.75),
    'logo-upper':mix(.63),'logo-lower':themeMix(accent,'#ffffff',.2),'logo-suffix':themeMix(accent,'#ffffff',.55),
    backdrop:bg+'cc',toast:mix(.13),'toast-line':mix(.42),'selection-bg':mix(.23)
  };
}
function applyTheme(value){
  const theme=appThemes.find(item=>item.id===value)||appThemes[0];
  Object.entries(themePalette(theme)).forEach(([name,color])=>document.documentElement.style.setProperty('--'+name,color));
  document.documentElement.dataset.theme=theme.id;
  const icon=document.querySelector('.appIcon');if(icon)icon.src='/themes/icon-'+theme.id+'.svg';
  const favicon=document.getElementById('themeFavicon');if(favicon)favicon.href='/themes/icon-'+theme.id+'.svg';
  try{localStorage.setItem('backlogame-theme',theme.id);}catch{}
}
try{applyTheme(localStorage.getItem('backlogame-theme'));}catch{applyTheme('teal');}
function themePicker(){
  return `<fieldset class="themePicker"><legend>${t('Цветовая тема')}</legend><div class="themeGrid">${appThemes.map(theme=>`<button type="button" class="themeChoice" data-theme-choice="${theme.id}" aria-pressed="${(preferences.theme||'teal')===theme.id}"><span class="themePreview" aria-hidden="true"><span></span><i></i><i></i></span><span>${t(theme.name)}</span></button>`).join('')}</div><p class="hint">${t('Тема меняет интерфейс, логотип и иконку. Цвета обложек и обозначения статусов сохраняются.')}</p></fieldset>`;
}
function bindThemePicker(){
  document.querySelectorAll('[data-theme-choice]').forEach(button=>button.onclick=async()=>{
    if(settingsSaving)return;
    const previous=preferences.theme||'teal',next=button.dataset.themeChoice;
    settingsSaving=true;applyTheme(next);
    const buttons=[...document.querySelectorAll('[data-theme-choice]')];
    buttons.forEach(item=>{item.disabled=true;item.setAttribute('aria-pressed',String(item===button));});
    try{preferences=await api('/api/settings',{theme:next});applyTheme(preferences.theme);$('settingsStatus').textContent=t('Сохранено');}
    catch(error){applyTheme(previous);buttons.forEach(item=>item.setAttribute('aria-pressed',String(item.dataset.themeChoice===previous)));toast(error.message,true);}
    finally{settingsSaving=false;buttons.forEach(item=>item.disabled=false);}
  });
}
