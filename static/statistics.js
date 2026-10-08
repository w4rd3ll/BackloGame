'use strict';
function statisticsModel(items,{platform='',category='',from='',to='',monthly=false}={}){
  const inRange=date=>date&&(!from||date>=from)&&(!to||date<=to);
  const history=g=>g.playthroughs||(g.completion_dates||(g.completed_at?[g.completed_at]:[])).map(date=>({date,platform:g.platform||'Пока неизвестно'}));
  const selected=items.filter(g=>(!platform||g.platform===platform||history(g).some(row=>row.platform===platform))&&(!category||g.status===category));
  const dates=g=>history(g).filter(row=>!platform||row.platform===platform).map(row=>row.date);
  const completed=g=>dates(g).some(inRange)||(!from&&!to&&g.status==='Пройдено');
  const timeline=new Map(),genres=new Map(),platforms=new Map(),releases=new Map();
  function bucket(date,type,id){if(!inRange(date))return;const key=date.slice(0,monthly?7:4);if(!timeline.has(key))timeline.set(key,{label:key,added:[],finished:[]});timeline.get(key)[type].push(id);}
  function group(map,label,g){if(!map.has(label))map.set(label,{label,ids:[],completed:0});const row=map.get(label);row.ids.push(g.id);row.completed+=Number(completed(g));}
  for(const g of selected){
    bucket((typeof localDay==='function'?localDay(g.added_at):(g.added_at||'').slice(0,10)),'added',g.id);
    for(const date of dates(g))bucket(date,'finished',g.id);
    for(const genre of new Set((g.genre||'').split(',').map(x=>x.trim()).filter(Boolean)))group(genres,genre,g);
    const currentPlatform=g.platform||'Пока неизвестно';
    if(!platforms.has(currentPlatform))platforms.set(currentPlatform,{label:currentPlatform,ids:[],completed:0,completedIds:[]});
    platforms.get(currentPlatform).ids.push(g.id);
    const finishedPlatforms=new Set(history(g).filter(row=>(!platform||row.platform===platform)&&inRange(row.date)).map(row=>row.platform));
    if(!from&&!to&&g.status==='Пройдено'&&!history(g).length)finishedPlatforms.add(currentPlatform);
    for(const label of finishedPlatforms){if(!platforms.has(label))platforms.set(label,{label,ids:[],completed:0,completedIds:[]});const row=platforms.get(label);row.completed++;row.completedIds.push(g.id);}
    if(/^\d{4}/.test(g.release_date||''))group(releases,g.release_date.slice(0,4),g);
  }
  const ranked=map=>[...map.values()].sort((a,b)=>b.ids.length-a.ids.length||a.label.localeCompare(b.label));
  return {selected,completed:selected.filter(completed),playing:selected.filter(g=>g.status==='Играю'),replaying:selected.filter(g=>g.status==='Перепрохожу'),backlog:selected.filter(g=>['Хочу пройти','Бэклог'].includes(g.status)),events:selected.flatMap(g=>dates(g).filter(inRange)),unknown:selected.filter(g=>g.status==='Пройдено'&&!dates(g).length).length,timeline:[...timeline.values()].sort((a,b)=>a.label.localeCompare(b.label)),genres:ranked(genres),platforms:ranked(platforms),releases:[...releases.values()].sort((a,b)=>b.label.localeCompare(a.label))};
}
function statisticsPieRows(rows,limit=8){
  const ranked=rows.filter(row=>row.ids.length).map(row=>({...row,count:row.ids.length})).sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label));
  const visible=ranked.slice(0,limit),rest=ranked.slice(limit);
  if(rest.length)visible.push({label:'Другие',count:rest.reduce((n,row)=>n+row.count,0),ids:[...new Set(rest.flatMap(row=>row.ids))]});
  const total=visible.reduce((n,row)=>n+row.count,0);
  return {total,rows:visible.map(row=>({...row,percentage:row.count/total*100}))};
}
if(typeof document!=='undefined'){
  const statsDialog=document.createElement('dialog');statsDialog.className='statisticsDialog';document.body.append(statsDialog);
  let statsIDs=null,statsSelectionLabel='',statsChartMode='bars';
  try{statsChartMode=localStorage.getItem('backlogame-statistics-chart')==='pie'?'pie':'bars';}catch{}
  const filteredBeforeStats=filteredGames;
  filteredGames=function(){return filteredBeforeStats().filter(g=>!statsIDs||statsIDs.has(g.id));};
  const renderBeforeStats=render;
  render=function(){renderBeforeStats();if(statsIDs){const button=document.createElement('button');button.className='text statsSelection';button.textContent=t('Статистика')+': '+statsSelectionLabel+' ×';button.onclick=()=>{statsIDs=null;render();};$('activeFilters').append(button);}};
  const resetBeforeStats=$('resetFilters').onclick;
  $('resetFilters').onclick=()=>{statsIDs=null;resetBeforeStats();};
  function showGames(ids,label){
    if(dirty){toast(t('Сначала сохрани изменения в карточке'),true);return;}
    statsDialog.close();statsIDs=null;resetBeforeStats();statusFilter='';statsIDs=new Set(ids);statsSelectionLabel=label;render();
  }
  function drawPie(target,rows,title){
    const model=statisticsPieRows(rows),ns='http://www.w3.org/2000/svg';
    const colors=['#58d4c4','#71aaf7','#bd90f3','#f38ab8','#f2b466','#e1d36c','#88ce8d','#f27f76','#8dacc0'];
    const wrap=document.createElement('div');wrap.className='statsPieWrap';target.append(wrap);
    const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 220 220');svg.classList.add('statsPie');svg.setAttribute('role','group');svg.setAttribute('aria-label',title);wrap.append(svg);
    const legend=document.createElement('div');legend.className='statsPieLegend';wrap.append(legend);
    let offset=0;
    model.rows.forEach((row,index)=>{
      const label=displayValue(row.label==='Другие'?t('Другие'):row.label),percentage=row.percentage.toLocaleString(uiLanguage==='ru'?'ru':'en',{maximumFractionDigits:1})+'%';
      const name=label+': '+row.count+' · '+percentage;
      const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx','110');circle.setAttribute('cy','110');circle.setAttribute('r','80');circle.setAttribute('pathLength','100');circle.setAttribute('fill','none');circle.setAttribute('stroke',colors[index]);circle.setAttribute('stroke-width','30');circle.setAttribute('transform','rotate(-90 110 110)');circle.setAttribute('stroke-dasharray',`${Math.max(0,row.percentage-Math.min(.4,row.percentage*.15))} ${100-row.percentage+Math.min(.4,row.percentage*.15)}`);circle.setAttribute('stroke-dashoffset',-offset);offset+=row.percentage;
      circle.setAttribute('role','button');circle.setAttribute('tabindex','0');circle.setAttribute('aria-label',name);const tooltip=document.createElementNS(ns,'title');tooltip.textContent=name;circle.append(tooltip);svg.append(circle);
      circle.onclick=()=>showGames(row.ids,label);circle.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();circle.onclick();}};
      const button=document.createElement('button');button.className='statsPieKey';button.title=name;button.innerHTML=`<i></i><span>${e(label)}</span><strong>${row.count}<small>${percentage}</small></strong>`;button.querySelector('i').style.backgroundColor=colors[index];button.onclick=circle.onclick;legend.append(button);
      for(const [element,other] of [[circle,button],[button,circle]]){element.onmouseenter=element.onfocus=()=>other.classList.add('highlight');element.onmouseleave=element.onblur=()=>other.classList.remove('highlight');}
    });
    const center=document.createElementNS(ns,'text');center.setAttribute('x','110');center.setAttribute('y','110');center.setAttribute('text-anchor','middle');center.classList.add('statsPieTotal');center.textContent=model.total;svg.append(center);
    const caption=document.createElementNS(ns,'text');caption.setAttribute('x','110');caption.setAttribute('y','134');caption.setAttribute('text-anchor','middle');caption.classList.add('statsPieCaption');caption.textContent=title===t('По жанрам')?t('Упоминаний'):t('Всего');svg.append(caption);
  }
  function renderStatistics(){
    const model=statisticsModel(games,{platform:$('statsPlatform').value,category:$('statsCategory').value,from:$('statsFrom').value,to:$('statsTo').value,monthly:$('statsScale').value==='month'});
    const output=$('statsOutput');output.replaceChildren();
    const cards=document.createElement('div');cards.className='statsCards';output.append(cards);
    for(const [label,items] of [[t('Всего игр'),model.selected],[t('Пройденные игры'),model.completed],[t('Играю'),model.playing],[t('Перепрохожу'),model.replaying],[t('В бэклоге'),model.backlog]]){
      const button=document.createElement('button');button.className='statsCard';button.innerHTML=`<span>${e(label)}</span><strong>${items.length}</strong>`;button.onclick=()=>showGames(items.map(g=>g.id),label);cards.append(button);
    }
    const summary=document.createElement('p');summary.className='hint';summary.textContent=t('Прохождений с датой')+': '+model.events.length+' · '+t('Без даты прохождения')+': '+model.unknown;output.append(summary);
    const switcher=document.createElement('div');switcher.className='statsChartSwitch';switcher.setAttribute('role','group');switcher.setAttribute('aria-label',t('Вид диаграмм'));
    for(const [mode,label] of [['bars',t('Столбики')],['pie',t('Круговые')]]){const button=document.createElement('button');button.textContent=(mode==='pie'?'◉ ':'▥ ')+label;button.setAttribute('aria-pressed',String(mode===statsChartMode));button.onclick=()=>{statsChartMode=mode;try{localStorage.setItem('backlogame-statistics-chart',mode);}catch{}renderStatistics();};switcher.append(button);}
    const hint=document.createElement('span');hint.className='hint';hint.textContent=t('Жанры, платформы и годы выпуска');switcher.append(hint);output.append(switcher);
    const grid=document.createElement('div');grid.className='statsGrid';output.append(grid);
    function section(title,hint){const section=document.createElement('section');section.className='statsChart';section.innerHTML=`<h3>${e(title)}</h3><p class="hint">${e(hint)}</p>`;grid.append(section);return section;}
    const activity=section(t('Пополнение и прохождения'),t('Добавлено / прохождений. Повторные прохождения учитываются отдельно.'));activity.classList.add('statsWide');
    const chart=document.createElement('div');chart.className='statsTimeline';activity.append(chart);
    const peak=Math.max(1,...model.timeline.flatMap(row=>[row.added.length,row.finished.length]));
    for(const row of model.timeline){
      const column=document.createElement('div');column.className='statsColumn';
      for(const [key,label] of [['added',t('Добавлено')],['finished',t('Прохождения')]]){
        const button=document.createElement('button');button.className='statsColumnBar '+key;button.style.setProperty('--bar-height',(row[key].length/peak*170)+'px');button.title=label+': '+row[key].length;button.setAttribute('aria-label',row.label+' '+button.title);button.innerHTML=`<span>${row[key].length}</span>`;button.onclick=()=>showGames(row[key],row.label+' · '+label);column.append(button);
      }
      const label=document.createElement('span');label.className='statsYear';label.textContent=row.label;column.append(label);chart.append(column);
    }
    if(!model.timeline.length)chart.textContent=t('Нет данных за выбранный период');
    for(const [title,rows] of [[t('По жанрам'),model.genres],[t('По платформам'),model.platforms],[t('По годам выпуска'),model.releases]]){
      const target=section(title,statsChartMode==='pie'?t('Доля среди указанных значений. Нажми, чтобы открыть игры.'):title===t('По платформам')?t('Текущая платформа / пройдено на ней. Нажми, чтобы открыть игры.'):t('В библиотеке / пройдено. Нажми, чтобы открыть игры.'));
      const missing=title===t('По жанрам')?model.selected.filter(g=>!g.genre?.trim()).length:title===t('По годам выпуска')?model.selected.filter(g=>!/^\d{4}/.test(g.release_date||'')).length:0;
      if(missing){const note=document.createElement('p');note.className='hint';note.textContent=t('Не указано')+': '+missing;target.append(note);}
      if(statsChartMode==='pie'&&rows.length){drawPie(target,rows,title);grid.insertBefore(target,activity);continue;}
      const peak=Math.max(1,...rows.map(row=>Math.max(row.ids.length,row.completed)));
      const list=document.createElement('div');list.className='statsRanked';target.append(list);
      for(const row of rows){const button=document.createElement('button');button.className='statsRank';button.innerHTML=`<span>${e(displayValue(row.label))}</span><strong>${row.ids.length} <small>/ ${row.completed}</small></strong><span class="statsMeter"><i></i><b></b></span>`;button.querySelector('i').style.width=(row.ids.length/peak*100)+'%';button.querySelector('b').style.width=(row.completed/peak*100)+'%';button.onclick=()=>showGames([...new Set([...row.ids,...(row.completedIds||[])])],displayValue(row.label));list.append(button);}
      if(!rows.length)list.textContent=t('Нет данных');
    }
    if(model.genres.length){const note=document.createElement('p');note.className='hint';note.textContent=t('Игра с несколькими жанрами учитывается в каждом из них.');output.append(note);}
  }
  $('statisticsButton').onclick=()=>{
    statsDialog.innerHTML=`<div class="dialogHead"><div><div class="eyebrow">BACKLOGAME</div><h2>${t('Статистика')}</h2></div><button id="closeStatistics" aria-label="${t('Закрыть')}">✕</button></div><p class="hint">${t('Твоя библиотека в цифрах. Период ограничивает активность; состав библиотеки — платформа и категория.')}</p><div class="statsFilters"><label>${t('Платформа')}<select id="statsPlatform"><option value="">${t('Все платформы')}</option>${[...new Set(games.flatMap(g=>[g.platform,...(g.playthroughs||[]).map(row=>row.platform)]).filter(Boolean))].sort().map(x=>`<option value="${e(x)}">${e(displayValue(x))}</option>`).join('')}</select></label><label>${t('Категории')}<select id="statsCategory"><option value="">${t('Все игры')}</option>${statuses.map(x=>`<option value="${e(x)}">${e(displayValue(x))}</option>`).join('')}</select></label><label>${t('С даты')}<input id="statsFrom" type="date"></label><label>${t('По дату')}<input id="statsTo" type="date"></label><label>${t('Группировать')}<select id="statsScale"><option value="year">${t('По годам')}</option><option value="month">${t('По месяцам')}</option></select></label><button id="statsReset">${t('Сбросить')}</button></div><div id="statsOutput"></div>`;
    $('closeStatistics').onclick=()=>statsDialog.close();
    wireDialogBackdrop(statsDialog,()=>statsDialog.close());
    statsDialog.querySelectorAll('select,input').forEach(input=>input.onchange=()=>{if($('statsFrom').value&&$('statsTo').value&&$('statsFrom').value>$('statsTo').value){$('statsTo').setCustomValidity(t('Конечная дата раньше начальной'));$('statsTo').reportValidity();return;}$('statsTo').setCustomValidity('');renderStatistics();});
    $('statsReset').onclick=()=>{statsDialog.querySelectorAll('input,select').forEach(input=>input.value=input.id==='statsScale'?'year':'');$('statsTo').setCustomValidity('');renderStatistics();};
    renderStatistics();statsDialog.showModal();
  };
}
