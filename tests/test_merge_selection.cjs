const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const ctx=vm.createContext({document:{createElement:()=>({}),body:{append:()=>{}}},$:()=>({after:()=>{}}),updateBatchBar:()=>{},t:text=>text,markedGames:new Set()});
vm.runInContext(fs.readFileSync('static/merge-games.js','utf8').split('mergeButton.onclick=')[0],ctx);
for(const [count,disabled] of [[0,true],[1,true],[2,false],[3,false],[100,false],[101,true]]){
 ctx.markedGames=new Set(Array.from({length:count},(_,i)=>i));
 vm.runInContext('updateBatchBar()',ctx);
 assert.equal(vm.runInContext('mergeButton.disabled',ctx),disabled,'Selection size '+count);
}
console.log('Merge selection: 2 through 100 cards enabled, other counts disabled: OK');
