const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes={},node=()=>({value:'portrait',files:[],disabled:false,hidden:false,src:'',textContent:'',querySelectorAll:()=>[],querySelector:()=>null});
const get=id=>nodes[id]||(nodes[id]=node());const dialog=node();dialog.showModal=()=>dialog.open=true;dialog.close=()=>{dialog.open=false;dialog.onclose?.();};
let requests=[],reloads=0,revoked=0;
const ctx=vm.createContext({document:{createElement:()=>dialog,body:{append(){}},addEventListener(){}},$:get,dirty:false,catalogBatchRunning:false,coversUpdating:false,preferences:{cover_max_mb:12},games:[{id:1,title:'Portal',custom_covers:{}}],selectedId:1,renderInspector(){},wireDialogBackdrop(){},t:x=>x,e:x=>x,toast(){},token:'test-token',URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){revoked++;}},fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({game:{}})};},reload:async()=>reloads++,api:async(path,body)=>{requests.push({path,body});}});
vm.runInContext(fs.readFileSync('static/cover-upload.js','utf8'),ctx);
(async()=>{
 vm.runInContext('openCoverUpload(games[0])',ctx);assert(dialog.open);assert(get('applyCoverUpload').disabled);
 const file={size:100};get('coverUploadFile').files=[file];get('coverUploadFile').onchange();assert(!get('applyCoverUpload').disabled);
 get('coverUploadOrientation').value='landscape';await get('coverUploadForm').onsubmit({preventDefault(){}});
 assert.equal(requests[0].url,'/api/covers/upload?id=1&orientation=landscape');assert.equal(requests[0].options.body,file);assert.equal(requests[0].options.headers['X-Library-Token'],'test-token');assert.equal(reloads,1);
 get('coverUploadFile').files=[{size:13*1024*1024}];await get('coverUploadForm').onsubmit({preventDefault(){}});assert.equal(requests.length,1);assert.match(get('coverUploadStatus').textContent,/12/);
 dialog.close();assert.equal(revoked,1);ctx.dirty=true;vm.runInContext('openCoverUpload(games[0])',ctx);assert(!dialog.open);
 console.log('Cover upload UI: orientation, file body/token, preview cleanup, size limit and unsaved-edit guard: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
