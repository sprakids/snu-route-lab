// Run the actual fragment's control script with a small DOM/host adapter.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const file = 'C:/Users/김예준/.codex/visualizations/2026/10/21/01a15f4b-516c-79b1-9b9a-c31680e1acd7/shuttle-destination-sensitivity.html';
const html = fs.readFileSync(file, 'utf8');
const payloads = [...html.matchAll(/<script type="application\/json" data-viz-chart data-state="([^"]+)">([\s\S]*?)<\/script>/g)]
  .map(m => ({dataset:{state:m[1]},textContent:m[2]}));
assert.equal(payloads.length, 20);
const code = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]
  .replace(/import \{ mountChart \} from "[^"]+";/, '');
function start(saved) {
  const handlers = {};
  let saves=0, chart;
  const control = label => ({disabled:true,value:'',addEventListener:(event,fn)=>{handlers[label+event]=fn;}});
  const scenario=control('scenario'), scope=control('scope'), context={textContent:''};
  const root={querySelectorAll:()=>payloads,querySelector:selector=>({
    '[data-scenario]':scenario,'[data-window]':scope,'[data-context]':context,'[data-viz-container]':{}
  })[selector]};
  const sandbox={document:{getElementById:id=>{assert.equal(id,'shuttle-destination-sensitivity');return root;}},
    window:{openai:{widgetState:{modelContent:saved},setWidgetState:()=>{saves++;return Promise.resolve();}},
      addEventListener:(name,fn)=>{handlers[name]=fn;}},
    mountChart:(container,config)=>{chart={config};return chart;}};
  vm.runInNewContext(code,sandbox);
  assert.equal(saves,0,'Initial/restored state must not be saved again');
  assert.equal(scenario.disabled,false);assert.equal(scope.disabled,false);
  return {handlers,scenario,scope,context,get chart(){return chart;},get saves(){return saves;}};
}
const live=start(undefined);
assert.equal(live.scenario.value,'daehak_plus10pp');assert.equal(live.scope.value,'afternoon');
for(const el of payloads) {
  const [name,scope]=el.dataset.state.split('|');
  live.scenario.value=name;live.scope.value=scope;live.handlers.scenariochange();
  const expected=JSON.parse(el.textContent);
  assert.equal(JSON.stringify(live.chart.config),JSON.stringify(expected));
  assert.equal(live.context.textContent,expected.summary);
}
const before=live.chart.config;
live.handlers['openai:set_globals']({detail:{globals:{widgetState:{modelContent:{scenario:'invalid',window:'all'}}}}});
assert.equal(live.chart.config,before);
const restored=start({scenario:'historical_dorm30',window:'all'});
assert.equal(restored.scenario.value,'historical_dorm30');assert.equal(restored.scope.value,'all');
const result={status:'PASS',fixed_chart_configurations:payloads.length,actual_control_changes_checked:payloads.length,
  default_and_saved_state_checked:true,invalid_state_ignored:true,rendering:'not checked; script and values only'};
fs.writeFileSync(path.join(__dirname,'inline_chart_control_check.json'),JSON.stringify(result,null,2),'utf8');
console.log(JSON.stringify(result));
