const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../public'),out=path.join(__dirname,'qa/public-final');
const before=JSON.parse(fs.readFileSync(path.join(root,'data/half_hour_v1/capacity_v5.json'))).scenarios.peak.mon['62']['61200'];
const after=JSON.parse(fs.readFileSync(path.join(root,'data/half_hour_v1/capacity_v7.json'))).scenarios.peak.mon['62']['61200'];
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});const results=[];
try{for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
 const page=await browser.newPage({viewport});await page.goto('https://snu-shuttle-simulation.vercel.app/');
 await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,{timeout:90000});
 await page.click('#charts-tab');await page.selectOption('#chart-stop-select','city_gate');await page.click('#charts-tab');
 const cell=page.locator('#current-heatmap button[data-day="mon"][data-start="61200"]');await cell.waitFor({state:'visible'});
 const text=await cell.evaluate(e=>e.childNodes[0].textContent.trim());const expected=new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(after.mean_wait_min);
 assert.equal(text,expected);assert((await page.locator('#heatmap-scenario').innerText()).includes('정문 도보 보정 모형'));
 await page.screenshot({path:path.join(out,'actual-current-graph-'+name+'.png')});
 results.push({viewport:name,stop:'21128',day:'mon',arrival_bin:'17:00~17:30',old_mean_wait_min:before.mean_wait_min,new_mean_wait_min:after.mean_wait_min,displayed:text,source_matches:true});await page.close();
}fs.writeFileSync(path.join(out,'current_graph_verification.json'),JSON.stringify({status:'PASS',results,graph_is_recomputed_from_capacity_v7:true},null,2));console.log(JSON.stringify({status:'PASS',results}));}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
