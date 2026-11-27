import test from 'node:test';import assert from 'node:assert/strict';
import {updatePacked,crowdSummary,headwaySummary} from './packed_stats.mjs';
const day='2026-11-09',at=Date.parse(day+'T16:00:00+09:00')/1000;
const stops=[{seq:1,lat:37.46,lon:126.95},{seq:2,lat:37.461,lon:126.951}];
const vehicle=(time,extra={})=>({id:'v',section_order:'1',provided_at:time,lat:37.46,lon:126.95,crowd_code:'5',full:false,full_known:true,...extra});
test('grade and full labels count once per passage, including repeated stop polls',()=>{
 let p;for(let i=0;i<20;i++)p=updatePacked(p,[vehicle(at+i*15)],stops,day).value;
 assert.equal(Object.values(p.grades).reduce((a,b)=>a+b,0),1);
 assert.deepEqual(Object.values(p.availability),[[0,1]]);
 p=updatePacked(p,[vehicle(at+400,{section_order:'2',full:true})],stops,day).value;
 assert.equal(Object.values(p.grades).reduce((a,b)=>a+b,0),2);
 assert.equal(Object.values(p.availability).reduce((n,p)=>n+p[0],0),1);
});
test('an unknown full flag is not a negative training label',()=>{
 let p=updatePacked(null,[vehicle(at,{full_known:false,crowd_code:'0'})],stops,day).value;
 assert.deepEqual(p.availability,{});assert.deepEqual(p.grades,{});
 p=updatePacked(p,[vehicle(at+15,{full_known:true,full:true,crowd_code:'0'})],stops,day).value;
 assert.deepEqual(Object.values(p.availability),[[1,1]]);assert.deepEqual(p.grades,{});
});
test('unidentified vehicles and source dates outside the aggregate day are not counted',()=>{
 const p=updatePacked(null,[vehicle(at,{id:''}),vehicle(at-86400)],stops,day).value;
 assert.deepEqual(p.grades,{});assert.deepEqual(p.availability,{});
});
test('upgrading existing packed rows does not recount already seen grades',()=>{
 const p={schema:2,day,grades:{'1:64:5':1},travel:{},progress:{v:{seq:1,at:at-15,stops:[]}}};
 const result=updatePacked(p,[vehicle(at)],stops,day).value;
 assert.equal(Object.values(result.grades).reduce((a,b)=>a+b,0),1);
 assert.equal(Object.values(result.availability).reduce((n,p)=>n+p[1],0),1);
});
test('headways require distinct vehicles at a nearby confirmed stop',()=>{
 let p;
 for(const [id,time] of [['a',at],['b',at+60],['b',at+90],['c',at+120]]){
  p=updatePacked(p,[vehicle(time,{id,at_stop:true,previous_observation:{provided_at:time-15}})],stops,day).value;
 }
 const h=headwaySummary([{day,value:p}],'r',16)['1'];assert.equal(h.n,2);assert.equal(h.median_seconds,60);
 assert.equal(h.hour,16);
 const grades=crowdSummary([{day,value:p}],'r',16);assert.equal(grades.counts[2],3);
 assert.equal(grades.sections['1'].availability['5'][1],3);
});
