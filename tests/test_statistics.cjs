const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync('static/statistics.js','utf8'),ctx);
const input=[
 {id:1,status:'Перепрохожу',platform:'PC',genre:'Puzzle, Action, Puzzle',release_date:'2007',added_at:'2020-02-01',completion_dates:['2020-03-01','2022-01-01','2022-01-01']},
 {id:2,status:'Пройдено',platform:'PS5',genre:'Action',added_at:'2022-01-01',completion_dates:[]},
 {id:3,status:'Бэклог',platform:'PC',genre:'Puzzle',added_at:'2023-01-01',completion_dates:[]}
];
function model(options={}){return JSON.parse(vm.runInContext('JSON.stringify(statisticsModel('+JSON.stringify(input)+','+JSON.stringify(options)+'))',ctx));}
const all=model();assert.equal(all.completed.length,2);assert.equal(all.events.length,3);assert.equal(all.unknown,1);
assert.equal(all.genres.find(x=>x.label==='Puzzle').ids.length,2);
assert.equal(all.timeline.find(x=>x.label==='2022').finished.length,2);
const period=model({from:'2022-01-01',to:'2022-12-31',monthly:true});
assert.equal(period.events.length,2);assert.equal(period.completed.length,1);assert.equal(period.selected.length,3);
assert.equal(period.timeline[0].label,'2022-01');
const platform=model({platform:'PC'});assert.equal(platform.selected.length,2);assert.equal(platform.replaying.length,1);
assert.equal(model({category:'Бэклог'}).backlog.length,1);
console.log('Statistics: unique games, repeated events, periods, genre deduplication and category/platform scopes: OK');

const pie=JSON.parse(vm.runInContext('JSON.stringify(statisticsPieRows('+JSON.stringify(Array.from({length:12},(_,i)=>({label:String(i),ids:Array.from({length:12-i},(_,j)=>j)})))+'))',ctx));
assert.equal(pie.rows.length,9);assert.equal(pie.total,78);assert.equal(pie.rows.at(-1).count,10);assert.equal(pie.rows.at(-1).ids.length,4);assert.ok(Math.abs(pie.rows.reduce((n,x)=>n+x.percentage,0)-100)<1e-8);
assert.equal(vm.runInContext('statisticsPieRows([]).total',ctx),0);
assert.equal(vm.runInContext("statisticsPieRows([{label:'Only',ids:[1]}]).rows[0].percentage",ctx),100);
console.log('Pie charts: bounded slices, exact totals, grouped navigation, empty/single-group cases: OK');
const mergedStats=JSON.parse(vm.runInContext("JSON.stringify(statisticsModel([{id:1,status:'Бэклог',platform:'Steam',playthroughs:[{date:'2019-06-14',platform:'PS3'}]}]))",ctx));
assert.equal(mergedStats.completed.length,1);
assert.equal(mergedStats.platforms.find(row=>row.label==='Steam').completed,0);
assert.equal(mergedStats.platforms.find(row=>row.label==='PS3').completed,1);
assert.equal(mergedStats.platforms.find(row=>row.label==='PS3').ids.length,0);
