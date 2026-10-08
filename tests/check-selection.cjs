const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const acorn=require('internal/deps/acorn/acorn/dist/acorn');
const source=fs.readFileSync('static/app.js','utf8');
const node=acorn.parse(source,{ecmaVersion:'latest'}).body.find(n=>n.type==='FunctionDeclaration'&&n.id.name==='selectGame');
const rows=[1,2].map(id=>({id,selected:id===1,classList:{remove(){rows.find(r=>r.classList===this).selected=false;},add(){rows.find(r=>r.classList===this).selected=true;}}}));
let panels=0,inspectors=0,persisted=0,confirmed=0;
const list={querySelectorAll:()=>rows.filter(r=>r.selected),querySelector:selector=>rows.find(r=>selector===`[data-id="${r.id}"]`)};
const ctx=vm.createContext({selectedId:1,dirty:false,inspectorCollapsed:false,confirm:()=>{confirmed++;return false;},t:s=>s,$:()=>list,applyPanels:()=>panels++,renderInspector:()=>inspectors++,persistView:()=>persisted++,render:()=>{throw Error('Selection must preserve existing list nodes');}});
vm.runInContext(source.slice(node.start,node.end),ctx);
ctx.selectGame(2);assert.equal(ctx.selectedId,2);assert.deepEqual(rows.map(r=>r.selected),[false,true]);assert.equal(inspectors,1);
ctx.dirty=true;ctx.selectGame(1);assert.equal(ctx.selectedId,2);assert.equal(ctx.dirty,true);assert.equal(inspectors,1);assert.equal(confirmed,1);
ctx.inspectorCollapsed=true;ctx.selectGame(1,true);assert.equal(ctx.selectedId,1);assert.equal(ctx.dirty,false);assert.equal(ctx.inspectorCollapsed,false);assert.equal(persisted,1);assert.equal(panels,2);
ctx.selectGame(null);assert.deepEqual(rows.map(r=>r.selected),[false,false]);assert.equal(ctx.selectedId,null);
const titles=['DOOM 10','DOOM 2','Дум','doom 1','Alan Wake','Алан','DOOM 02'];
assert.deepEqual([...titles].sort(new Intl.Collator('ru',{numeric:true,sensitivity:'base'}).compare),[...titles].sort((a,b)=>a.localeCompare(b,'ru',{numeric:true,sensitivity:'base'})));
console.log('Selection preserves list nodes, edit guard, panel state and sorting: OK');

vm.runInContext(source.match(/const libraryTitleCollator = .*;/)[0],ctx);
assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(['DOOM 10','DOOM 2','Alan Wake','"+String.fromCodePoint(1040,1083,1072,1085)+"','"+String.fromCodePoint(1071,1088,1086,1089,1090,1100)+"'].sort(libraryTitleCollator.compare))",ctx)),['Alan Wake','DOOM 2','DOOM 10',String.fromCodePoint(1040,1083,1072,1085),String.fromCodePoint(1071,1088,1086,1089,1090,1100)]);
