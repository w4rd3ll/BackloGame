const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const acorn=require('internal/deps/acorn/acorn/dist/acorn');
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync('static/i18n.js','utf8'),ctx);
const missing=[];
function walk(n){if(!n||typeof n!=='object')return;if(n.type==='CallExpression'&&n.callee.name==='t'&&n.arguments[0]?.type==='Literal'){const key=n.arguments[0].value;if(!vm.runInContext('Object.hasOwn(translations,'+JSON.stringify(key)+')',ctx))missing.push(key);}
 for(const v of Object.values(n))if(Array.isArray(v))v.forEach(walk);else if(v&&typeof v==='object')walk(v);
}
for(const file of ['app.js','enhancements.js','thumbnail.js','desktop.js','library-features.js','themes.js','updates.js','statistics.js','merge-games.js','catalog-tools.js','steamgriddb.js','sharing.js','library-navigation.js'])walk(acorn.parse(fs.readFileSync('static/'+file,'utf8'),{ecmaVersion:'latest'}));
assert.deepEqual(missing,[]);console.log('All interface translation keys are present: OK');
