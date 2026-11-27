const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {JSDOM} = require(path.join(__dirname,'../app/node_modules/jsdom'));
const visualPath = 'C:/Users/김예준/.codex/visualizations/2026/11/03/01a1a1e8-54cf-7243-9ad9-0a31e6f31a06/course-stop-inflow.html';
const html = fs.readFileSync(visualPath,'utf8');
const dom = new JSDOM(html,{runScripts:'outside-only'});
const window = dom.window;
let current, saves=0;
window.openai = {widgetState:null,setWidgetState:async()=>{saves++;}};
// The real DOM and event handlers run; renderer is stubbed to isolate state wiring.
window.mountChart = (_container,config)=>{
  current=config;
  return {set config(value){current=value;}};
};
const source=window.document.querySelector('script[type="module"]').textContent.replace(/^\s*import\s+\{ mountChart \}[^\n]+\n/m,'');
window.eval(source);
const day=window.document.getElementById('snu-inflow-day');
const scenario=window.document.getElementById('snu-inflow-scenario');
assert.equal(saves,0);
assert.equal(current.id,'stop-inflow-reference_dorm19p49_depart50-월');
let selections=0;
for(const d of day.options){
  for(const s of scenario.options){
    day.value=d.value;scenario.value=s.value;
    scenario.dispatchEvent(new window.Event('change'));
    assert.equal(current.id,`stop-inflow-${s.value}-${d.value}`);
    assert.equal(current.rows.length,8);
    assert(current.rows.every(r=>typeof r[1]==='number'&&Number.isFinite(r[1])));
    selections++;
  }
}
const before=saves;
window.dispatchEvent(new window.CustomEvent('openai:set_globals',{detail:{globals:{widgetState:{modelContent:{version:1,day:'금',scenario:'nak_dominant'}}}}}));
assert.equal(current.id,'stop-inflow-nak_dominant-금');
assert.equal(day.value,'금');assert.equal(scenario.value,'nak_dominant');assert.equal(saves,before);
window.dispatchEvent(new window.CustomEvent('openai:set_globals',{detail:{globals:{widgetState:{modelContent:{version:1,day:'invalid',scenario:'invalid'}}}}}));
assert.equal(current.id,'stop-inflow-nak_dominant-금');
const result={status:'PASS',control_combinations:selections,state_restore:true,invalid_state_retained:true,save_echo_loop:false,renderer:'stubbed; visual layout not inspected'};
fs.writeFileSync(path.join(__dirname,'outputs/chart_interaction_validation.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
