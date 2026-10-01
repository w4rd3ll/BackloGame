const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fields = new Map();
const get = id => {
  if(!fields.has(id)) fields.set(id,{value:'',checked:false,options:[],textContent:'',className:'',hidden:false,querySelectorAll:()=>[],querySelector:()=>({}),addEventListener:()=>{}});
  return fields.get(id);
};
get('sortField').value='title';
const context=vm.createContext({document:{getElementById:get,querySelector:()=>({})},window:{addEventListener:()=>{}},localStorage:{getItem:()=>null,setItem:()=>{}},fetch:()=>new Promise(()=>{}),setTimeout,clearTimeout,console,Date,URL,Blob});
vm.runInContext(fs.readFileSync('static/i18n.js','utf8'),context);
vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
const run = code => vm.runInContext(code,context);
run(`games=[
 {id:1,title:'Бета',platform:'PC',genre:'RPG, Экшен',series:'Серия',tags:'На потом',priority:'Высокий',release_date:'2015',added_at:'2026-10-01T00:00:00Z',status:'Играю'},
 {id:2,title:'Альфа',platform:'Steam Deck',genre:'RPG',priority:'Низкий',release_date:'2020-05-01',added_at:'2026-09-20T00:00:00Z',status:'Хочу пройти'},
 {id:3,title:'Гамма',platform:'Пока неизвестно',added_at:'2026-09-01T00:00:00Z',status:'Пройдено'}
]; direction=1;`);
const ids=()=>Array.from(run('filteredGames().map(g=>g.id)'));
assert.deepEqual(ids(),[2,1,3]);
run('direction=-1'); assert.deepEqual(ids(),[3,1,2]);
get('sortField').value='release_date';run('direction=1');assert.deepEqual(ids(),[1,2,3]);
run('direction=-1');assert.deepEqual(ids(),[2,1,3]);
get('releaseFrom').value='2015-06-01';get('releaseTo').value='2015-08';assert.deepEqual(ids(),[1]);
get('releaseFrom').value='';get('releaseTo').value='';get('unknownRelease').checked=true;assert.deepEqual(ids(),[3]);
get('unknownRelease').checked=false;get('genreFilter').value='RPG';assert.deepEqual(ids(),[2,1]);
get('platformFilter').value='PC';assert.deepEqual(ids(),[1]);
get('genreFilter').value='';get('platformFilter').value='';get('librarySearch').value='на потом';assert.deepEqual(ids(),[1]);
get('librarySearch').value='';get('sortField').value='priority';run('direction=-1');assert.deepEqual(ids(),[1,3,2]);
run('statusFilter="Хочу пройти"');assert.deepEqual(ids(),[2]);
run('games[0].favorite=true;games[2].favorite=true;statusFilter="favorites"');assert.deepEqual(ids(),[1,3]);
get('platformFilter').value='PC';assert.deepEqual(ids(),[1]);get('platformFilter').value='';
run('savedPlatforms=["Steam","steam","Моя консоль"]');
const platforms=Array.from(run('availablePlatforms()'));
assert.equal(platforms.filter(p=>p.toLowerCase()==='steam').length,1);
assert.ok(platforms.includes('Моя консоль'));
assert.ok(run('platformControl("Steam").includes(\'value="Steam" selected\')'));
run('statusFilter="not-favorites"');assert.deepEqual(ids(),[2]);
get('genreFilter').value='RPG';assert.deepEqual(ids(),[2]);get('genreFilter').value='';
const resources=run('gameResources({title:"Half-Life 2: Episode One",source_id:"steam:380",description_url:"https://ru.wikipedia.org/?curid=123"})');
assert.equal(resources[0].url,'https://store.steampowered.com/app/380/');
assert.equal(resources[1].url,'https://ru.wikipedia.org/?curid=123');
assert.equal(new URL(resources[2].url).searchParams.get('nm'),'Half-Life 2: Episode One');
const manual=run('gameResources({title:"Игра & тест"})');
assert.equal(new URL(manual[0].url).searchParams.get('term'),'Игра & тест');
assert.equal(new URL(manual[1].url).searchParams.get('search'),'Игра & тест');
get('sortField').value='manual_order';run('statusFilter="";games[0].manual_order=3;games[1].manual_order=1;games[2].manual_order=2;direction=-1');
assert.deepEqual(ids(),[2,3,1]);
get('genreFilter').value='RPG';assert.deepEqual(ids(),[2,1]);get('genreFilter').value='';
run('games[0].series="Half-Life; Portal";games[1].series="Portal";games[2].series="Half-Life 2"');
assert.deepEqual(Array.from(run('seriesParts(" Half-Life ; Portal; ; Portal ")')),['Half-Life','Portal']);
get('seriesFilter').value='Portal';assert.deepEqual(ids(),[2,1]);
get('seriesFilter').value='Half-Life';assert.deepEqual(ids(),[1]);
get('seriesFilter').value='Half-Life 2';assert.deepEqual(ids(),[3]);
get('seriesFilter').value='';
console.log('Filters, sorting and multiple series separated by semicolons: OK');
// Display labels must not change the raw values used by filters and saves.
assert.equal(run('uiLanguage'), 'en');
assert.equal(run('displayValue("Хочу пройти")'), 'Want to play');
assert.equal(run('displayValue("Описание")'), 'Описание');
assert.equal(run('displayValue("Моя консоль")'), 'Моя консоль');
assert.match(run('platformControl("Пока неизвестно")'), /value="Пока неизвестно" selected>Unknown/);
const original=run('JSON.stringify(games)');
run('uiLanguage="ru"');assert.equal(run('displayValue("Хочу пройти")'), 'Хочу пройти');
assert.equal(run('JSON.stringify(games)'), original);
run('uiLanguage="en"');assert.match(run('gameContent(games[2])'), /Unknown/);
assert.doesNotMatch(run('gameContent(games[2])'), /Released: Не указана/);
console.log('English/Russian labels, stable storage values and custom names: OK');
