const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../public'),base=process.argv[2]||'http://127.0.0.1:8791/';
const label=process.argv[3]||'local',output=path.join(__dirname,'qa',label);fs.mkdirSync(output,{recursive:true});
const cache=new Map(),halves=new Map();
const read=file=>JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));
const hot=read('data/capacity_v5/common.json').hot_nodes;
function expected(dataset,scenario,day,stop,time){
  const key=dataset+'/'+scenario+'-'+day;
  if(!cache.has(key))cache.set(key,read('data/'+key+'.json').queue_timeline);
  if(!halves.has(dataset))halves.set(dataset,read('data/half_hour_v1/'+dataset+'.json'));
  const node=hot[stop],row=cache.get(key)[node].findLast(x=>x[0]<=time);
  return {queue:row?.[1]||0,mean:halves.get(dataset).scenarios[scenario][day][node][Math.floor(time/1800)*1800]?.mean_wait_min??null};
}
const fmt=n=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(n);
const variants=[['original','baseline_v5','capacity_v5'],['promoted','','capacity_v7'],['speed','empirical_speed_v1','capacity_v6']];
(async()=>{
  const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  const results=[];
  try{
    for(const [variant,param,dataset] of variants){
      for(const [device,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
        if(variant==='speed'&&device==='mobile')continue;
        const page=await browser.newPage({viewport}),errors=[];let checks=0;
        page.on('pageerror',e=>errors.push(String(e)));
        page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('net::ERR'))errors.push(m.text())});
        await page.addInitScript(()=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:['2026-11-11T08:15:42Z']))}static now(){return new RealDate('2026-11-11T08:15:42Z').valueOf()}}});
        const target=new URL(base);if(param)target.searchParams.set('dataset',param);
        async function ready(){await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,{timeout:90000})}
        async function query(day,time,stop){
          await page.click('#snapshot-open');await page.selectOption('#snapshot-day',day);await page.fill('#snapshot-time',time);
          await page.selectOption('#snapshot-stop',stop);await page.click('#snapshot-submit');
          await page.waitForFunction(()=>!document.getElementById('snapshot-dialog').open,{timeout:90000});await ready();
          assert.equal(await page.locator('#weekday').inputValue(),day);assert.equal(await page.locator('#clock').innerText(),time);checks+=2;
        }
        async function check(scenario,day,stop,second){
          const e=expected(dataset,scenario,day,stop,second);
          assert.equal(await page.locator('#stop-queue').innerText(),fmt(e.queue));
          assert.equal(await page.locator('#snapshot-sidebar [data-snapshot-mean]').innerText(),e.mean===null?'—':fmt(e.mean)+'분');checks+=2;
        }
        await page.goto(target.toString());await ready();
        assert((await page.title()).includes('하교길 실험실'));assert(await page.locator('#error-panel').isHidden());
        assert.equal(await page.locator('#weekday').inputValue(),'wed');assert.equal(await page.locator('#clock').innerText(),'17:15:42');
        assert((await page.locator('.initial-clock-note').innerText()).includes('17:15'));checks+=5;
        if(variant==='promoted')assert((await page.locator('#policy option[value="city"]').innerText()).includes('보정 모형'));
        await query('mon','16:53:00','admin_snu');await check('peak','mon','admin_snu',60780);
        await query('mon','16:55:30','city_120000195');await check('peak','mon','city_120000195',60930);
        await query('mon','17:03:30','city_gate');await check('peak','mon','city_gate',61410);
        await page.waitForTimeout(1200);assert.equal(await page.locator('#clock').innerText(),'17:03:30');checks++;
        await page.screenshot({path:path.join(output,variant+'-'+device+'-gate.png')});
        await page.click('#play-button');await page.waitForTimeout(1400);assert.notEqual(await page.locator('#clock').innerText(),'17:03:30');await page.click('#play-button');checks++;
        await page.click('#charts-tab');await page.waitForSelector('#current-heatmap button[data-day="tue"][data-start="55800"]');
        await page.locator('#current-heatmap button[data-day="tue"][data-start="55800"]').click();await ready();
        assert.equal(await page.locator('#weekday').inputValue(),'tue');assert.equal(await page.locator('#clock').innerText(),'15:30:00');checks+=2;
        await page.screenshot({path:path.join(output,variant+'-'+device+'-charts.png')});
        await page.selectOption('#scenario','regular');await ready();await query('fri','18:00:00','city_gate');await check('regular','fri','city_gate',64800);
        await page.locator('[data-theme-toggle]').click();assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');checks++;
        await page.reload();await ready();assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');assert.equal(await page.locator('#clock').innerText(),'17:15:42');checks+=2;
        const deep=new URL(target);deep.searchParams.set('day','thu');deep.searchParams.set('second','61380');
        await page.goto(deep.toString());await ready();assert.equal(await page.locator('#weekday').inputValue(),'thu');assert.equal(await page.locator('#clock').innerText(),'17:03:00');checks+=2;
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.equal(errors.length,0,JSON.stringify(errors));checks+=2;
        results.push({variant,device,status:'PASS',checks,console_errors:errors,default_kst_verified:'wed 17:15:42',manual_selection_retained:true,deep_link_retained:true});
        await page.close();
      }
    }
    const doc=await browser.newPage({viewport:{width:390,height:844}});await doc.goto(new URL('gate-access-methodology.html',base).toString());
    assert((await doc.locator('h1').innerText()).includes('261109171256'));assert((await doc.locator('body').innerText()).includes('독립 정확도 검증'));
    assert(await doc.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await doc.screenshot({path:path.join(output,'methodology-mobile.png')});await doc.close();
    fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify({status:'PASS',target:base,browser:'Edge/Playwright; Browser plugin not available',results,methodology_mobile:'PASS'},null,2));
    console.log(JSON.stringify({status:'PASS',target:base,viewports:results.length,checks:results.reduce((s,r)=>s+r.checks,3),output}));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
