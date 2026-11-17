import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {baseline, indexed} from './lookup.mjs';
let checks=0;
function same(rows,ids) {
 const a=baseline(rows,ids), b=indexed(rows,ids);
 assert.deepEqual(b,a);checks++;
 for(let i=0;i<a.length;i++) assert.equal(b[i],a[i]);
}
const fixtures=[[],[{id:0}],[{id:1},{id:1},{id:'1'},{id:-1},{id:0}]];
for(const rows of fixtures) for(const ids of [[],[0,1,'1',-1,'missing'],[1,1]]) same(rows,ids);
for(let n=0;n<100;n++) {
 const rows=Array.from({length:n},(_,i)=>Object.freeze({id:i%13,value:i}));
 Object.freeze(rows);same(rows,[0,4,12,13,-1,'4']);
}
const rows=Array.from({length:12000},(_,i)=>({id:i,value:i}));
const ids=Array.from({length:1200},(_,i)=>(i*31)%13000);
same(rows,ids);
let sink=0;
function run(fn) {
 const start=performance.now();
 const result=fn(rows,ids); // Map construction remains INSIDE the candidate timer.
 const elapsed=performance.now()-start;
 for(const row of result) if(row) sink=(sink+row.value)%1000000007;
 return elapsed;
}
for(let i=0;i<5;i++){run(baseline);run(indexed)}
const before=[],after=[],order=[];
for(let i=0;i<12;i++) {
 if(i%2===0){before.push(run(baseline));after.push(run(indexed));order.push('AB')}
 else{after.push(run(indexed));before.push(run(baseline));order.push('BA')}
}
console.log(JSON.stringify({checks,node:process.version,unit:'ms/batch',before,after,order,sink,
 scope:'Node pure function including index construction, NOT React render/INP',
 limitations:['No retained-heap/RSS measurement','No browser or React runtime','One synthetic workload and one warm session'],
 decision:'CPU candidate only; unmeasured memory prevents full acceptance'},null,2));
