const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const ctx=vm.createContext({document:{createElement:()=>({}),body:{append:()=>{}}}});
vm.runInContext(fs.readFileSync('static/catalog-tools.js','utf8').split('const inspectorBeforeCatalog=')[0],ctx);
const run=code=>JSON.parse(vm.runInContext('JSON.stringify('+code+')',ctx));
assert.deepEqual(run("catalogChosenFields({title:'',description:'wikipedia',genre:'steam',release_date:'metacritic'},{wikipedia:{source:'wiki:Portal',game:{}},steam:{source:'steam:400',game:{}},metacritic:{source:'metacritic:portal',game:{}}})"),{description:'wiki:Portal',genre:'steam:400',release_date:'metacritic:portal'});
assert.deepEqual(run("catalogChosenFields({description:'wikipedia'},{wikipedia:{source:'wiki:Portal',game:null}})"),{});
assert.equal(run("catalogFieldValue({release_label:'2007'},'release_date')"),'2007');
assert.equal(run("catalogFieldValue({image:'old',custom_covers:{portrait:{url:'chosen'}}},'image')"),'chosen');
assert.equal(run("catalogComparisonProviderLabel('steam')"),'Steam');
console.log('Catalog comparison: mixed field choices, unavailable sources, date labels and selected portrait artwork: OK');

assert.deepEqual(run("catalogEnabledProviders(['igdb'])"),['igdb']);
assert.deepEqual(run("catalogEnabledProviders(['steam','wikipedia','unknown'])"),['steam','wikipedia']);
assert.equal(run("catalogEnabledProviders([])").length,4);
