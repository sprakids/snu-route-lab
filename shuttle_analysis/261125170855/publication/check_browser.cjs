const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function run(origin, phase, cookiePath) {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.SNU_CHROME_PATH ? {executablePath: process.env.SNU_CHROME_PATH} : {}),
  });
  const findings = {phase, origin, pages: [], errors: []};
  try {
    for (const width of [1440,390]) {
      const context = await browser.newContext({viewport: {width,height:900}});
      if (cookiePath) {
        const row = fs.readFileSync(cookiePath,'utf8').split(/\r?\n/)
          .map(l=>l.split('\t')).find(parts=>parts[5]==='_vercel_jwt');
        assert(row && row[0].replace('#HttpOnly_','')===new URL(origin).hostname);
        await context.addCookies([{name:row[5],value:row[6],url:origin,httpOnly:true,secure:true}]);
      }
      const page = await context.newPage();
      page.on('pageerror',e=>findings.errors.push(e.message));
      page.on('response',r=>{if(r.url().startsWith(origin+'/') && r.status()>=400) findings.errors.push(r.status()+' '+r.url());});
      const ready=()=>page.waitForFunction(()=>document.querySelector('#play-button')?.disabled===false,{},{timeout:90000});
      await page.goto(origin+'/?day=tue&scenario=peak&minute=923');
      await ready();
      assert.match(await page.title(),/V12/);
      assert.match(await page.locator('.intro .eyebrow').textContent(),/V12.*V261125170855/);
      assert.equal(await page.locator('#clock').textContent(),'15:23:00');
      assert.equal(await page.locator('#stop-select').inputValue(),'admin_snu');
      assert.match(await page.locator('#parked-load').textContent(),/승차 위치 2대/);
      assert(Math.abs(Number(await page.locator('#stop-queue').textContent())-64.5)<0.1);
      const mobile = width<700;
      if (mobile) {
        assert(await page.locator('#lab-sheet-toggle').isVisible());
      } else {
        await page.locator('#charts-tab').click();
        const cell=page.locator('#current-heatmap [data-day="tue"][data-start="55800"]').first();
        await cell.click();
        await page.waitForFunction(()=>document.querySelector('#clock').textContent==='15:30:00');
        await page.locator('#map-tab').click();
        await page.locator('#stop-select').selectOption('admin_daehak');
        await page.locator('#time-input').fill('15:18:00');
        await page.locator('#time-input').dispatchEvent('change');
        await page.waitForFunction(()=>document.querySelector('#parked-load').textContent.includes('차내 출발 대기 5.2명'));
        await page.selectOption('#scenario','regular');
        await page.selectOption('#weekday','thu');
        await ready();
        await page.selectOption('#destination','gwanaksan_4411');
        await page.waitForFunction(()=>document.querySelector('#destination-count').textContent.includes('320'));
        const link=await page.locator('.methodology-link').getAttribute('href');
        const guide=await context.request.get(new URL(link,origin).href);
        assert(guide.ok() && (await guide.text()).includes('경로 추천 서비스'));
        await page.goto(origin+'/');
        await ready();
        assert.equal(await page.locator('#speed').inputValue(),'1');
        const expectedDay=await page.evaluate(()=>{
          const day=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Seoul',weekday:'short'}).format(new Date()).slice(0,3).toLowerCase();
          return ['sat','sun'].includes(day)?'fri':day;
        });
        assert.equal(await page.locator('#weekday').inputValue(),expectedDay);
        assert.equal(await page.locator('#play-button').getAttribute('aria-label'),'일시정지');
      }
      findings.pages.push({width, initialQueue:64.5, explicitTimePaused:true});
      await context.close();
    }
  } finally {
    await browser.close();
  }
  assert.deepEqual(findings.errors,[]);
  fs.writeFileSync(path.join(__dirname,phase+'_browser.json'),JSON.stringify(findings,null,2));
  console.log(JSON.stringify(findings));
}

run(...process.argv.slice(2)).catch(e=>{console.error(e.message);process.exitCode=1;});
