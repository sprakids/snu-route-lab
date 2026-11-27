"""Adapt the existing replay integration checks; keep reports outside the repo."""
from pathlib import Path

OUT=Path('C:/Users/김예준/AppData/Local/Temp/snu-walk-choice-20261110')
SOURCE=OUT.parent/'snu-weekday-operations-20261110/qa-rollback.cjs'

def main():
    OUT.mkdir(exist_ok=True)
    script=SOURCE.read_text(encoding='utf8')
    script=script.replace('capacity_v7','capacity_v9').replace("includes('정문 도보')","includes('경로 변경')")
    script=script.replace("includes('같은 공식 평일 간격')","includes('변경 횟수에 상한은 없고')")
    before="    const docs=await browser.newPage({viewport:{width:390,height:844}});"
    after="    const legacy=await browser.newPage({viewport:{width:1440,height:1000}});"
    start=script.index(before);end=script.index(after,start)
    script=script[:start]+'''    const docs=await browser.newPage({viewport:{width:390,height:844}}),docErrors=[];
    docs.on('pageerror',e=>docErrors.push(String(e)));
    await docs.goto(new URL('walk-choice-methodology.html',base).toString());
    await docs.waitForFunction(()=>document.querySelectorAll('#review-body tr').length===99,{timeout:60000});
    assert((await docs.locator('h1').innerText()).includes('경로'));
    for(const day of ['mon','tue','wed','thu','fri']){
      await docs.selectOption('#review-day',day);
      for(const scenario of ['peak','regular']){
        await docs.selectOption('#review-scenario',scenario);
        assert.equal(await docs.locator('#review-body tr').count(),99);
        assert((await docs.locator('#review-status').innerText()).includes('20분 초과 0명'));
        const max=await docs.locator('#review-body tr:first-child td:nth-child(4)').innerText();assert(Number(max)<=20);
      }
    }
    await docs.fill('#review-search','서울대정문');assert.equal(await docs.locator('#review-body tr').count(),2);
    for(const [distance,expectedText] of [[0,'100 / 100'],[500,'100 / 100'],[1000,'30 / 100'],[1500,'1.0702 / 100']]){
      await docs.locator('#distance').fill(String(distance));
      assert((await docs.locator('#distance-value').innerText()).includes(expectedText));
    }
    const csv=await docs.request.get(new URL('walk-choice-waits.csv',base).toString());assert(csv.ok());assert.equal((await csv.text()).trim().split(/\\r?\\n/).length,991);
    assert(await docs.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await docs.screenshot({path:path.join(out,'methodology-mobile.png')});
    assert.equal(docErrors.length,0,JSON.stringify(docErrors));await docs.close();
'''+script[end:]
    (OUT/'qa-walk-choice.cjs').write_text(script,encoding='utf8')
    print(OUT/'qa-walk-choice.cjs')

if __name__=='__main__':main()
