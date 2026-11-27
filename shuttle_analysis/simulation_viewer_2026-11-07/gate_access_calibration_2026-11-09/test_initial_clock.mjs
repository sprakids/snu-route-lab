import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=new URL('../public/initial-clock.js',import.meta.url);
const {initialReplayClock}=await import('data:text/javascript;base64,'+fs.readFileSync(source).toString('base64'));
const cases=[
  ['KST weekday and second','2026-11-11T08:15:42Z','', 'wed',17*3600+15*60+42],
  ['KST date rollover','2026-11-08T15:05:00Z','', 'mon',40800],
  ['before simulation hours','2026-11-09T01:00:00Z','', 'mon',40800],
  ['after simulation hours','2026-11-09T14:55:00Z','', 'mon',83400],
  ['Saturday is explicitly labelled','2026-11-14T08:00:00Z','', 'fri',17*3600],
  ['Sunday is explicitly labelled','2026-11-15T08:00:00Z','', 'fri',17*3600],
  ['explicit deep link retained','2026-11-11T08:15:42Z','?day=thu&second=61380', 'thu',61380],
  ['minute deep link retained','2026-11-11T08:15:42Z','?day=tue&minute=1023', 'tue',61380],
  ['invalid values use current clock','2026-11-11T08:15:42Z','?day=bad&second=no', 'wed',62142],
  ['empty values are not midnight','2026-11-11T08:15:42Z','?second=', 'wed',62142],
  ['endpoint remains selectable','2026-11-09T14:10:00Z','', 'mon',83400],
  ['link range is constrained','2026-11-11T08:15:42Z','?second=90000', 'wed',83400],
];
const results=[];
for(const [name,iso,search,day,second] of cases){
  const r=initialReplayClock(new Date(iso),search);assert.equal(r.day,day,name);assert.equal(r.second,second,name);
  if(name.includes('explicitly labelled'))assert(r.notice.includes('주말 자료가 없어 금요일 참고 모형'),name);
  results.push({name,status:'PASS',day:r.day,second:r.second});
}
fs.writeFileSync(new URL('./initial_clock_verification.json',import.meta.url),JSON.stringify({status:'PASS',checks:results},null,2));
console.log(JSON.stringify({status:'PASS',cases:results.length}));
