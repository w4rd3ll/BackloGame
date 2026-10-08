const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes={},calls=[],checks=['steam','igdb','metacritic','wikipedia'].map(provider=>({dataset:{catalogSource:provider},checked:true,disabled:false}));
function node(){return {value:'Portal',disabled:false,innerHTML:'',textContent:'',querySelectorAll:()=>[],classList:{add(){},remove(){}},getBoundingClientRect:()=>({})};}
const dialog=node();dialog.open=false;dialog.showModal=()=>dialog.open=true;dialog.close=()=>dialog.open=false;
dialog.querySelectorAll=selector=>selector==='[data-catalog-source]'?checks:[];
dialog.querySelector=selector=>checks.find(input=>selector.includes('"'+input.dataset.catalogSource+'"'));
const ctx=vm.createContext({document:{createElement:()=>dialog,body:{append:()=>{}}},wireDialogBackdrop:()=>{},preferences:{catalog_sources:checks.map(x=>x.dataset.catalogSource)},$:id=>nodes[id]||(nodes[id]=node()),t:x=>x,e:x=>x,displayValue:x=>x,toast:()=>{},busy:()=>{},api:async(path,body)=>{calls.push({path,body});return path==='/api/settings'?body:{items:[]};}});
vm.runInContext(fs.readFileSync('static/catalog-tools.js','utf8').split('const inspectorBeforeCatalog=')[0],ctx);
(async()=>{
 await vm.runInContext("openCatalogComparison({id:1,title:'Portal',platform:'PC'})",ctx);
 assert.equal(calls.filter(x=>x.path.startsWith('/api/search')).length,4);
 for(const provider of ['steam','igdb','metacritic']){
  const input=checks.find(x=>x.dataset.catalogSource===provider);input.checked=false;await input.onchange();
 }
 assert.deepEqual(Array.from(ctx.preferences.catalog_sources),['wikipedia']);
 const last=calls.slice(calls.map(x=>x.path).lastIndexOf('/api/settings')+1);
 assert.equal(last.length,1);assert.match(last[0].path,/provider=wikipedia$/);
 assert.match(nodes.catalogComparisonResults.innerHTML,/min-width:560px/);
 assert(!nodes.catalogComparisonResults.innerHTML.includes('<strong>Steam</strong>'));
 const remaining=checks.find(x=>x.checked);assert(remaining.disabled);
 const count=calls.length;remaining.checked=false;await remaining.onchange();assert.equal(calls.length,count);assert(remaining.checked);
 const again=calls.length;await vm.runInContext("openCatalogComparison({id:2,title:'Other',platform:'PC'})",ctx);
 assert.equal(calls.length-again,1);assert.match(calls.at(-1).path,/provider=wikipedia$/);
 console.log('Saved catalog choices: selected-only requests, dynamic columns, last-checkbox protection, reopening: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
