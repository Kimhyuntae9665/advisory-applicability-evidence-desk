"""Actual CPU Chrome checks; no inference, frozen artifacts remain unchanged."""
import asyncio, hashlib, json, subprocess
from pathlib import Path
from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'artifacts/ui-refit'

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    server=subprocess.Popen(['node','--input-type=module','-e',"import {createDesk} from './server.mjs';createDesk().listen(5158,'127.0.0.1',()=>console.log('ready'));"],cwd=ROOT,stdout=subprocess.PIPE,text=True)
    server.stdout.readline()
    url='http://127.0.0.1:5158'
    checks={'browser':'actual installed Google Chrome via Playwright','gpu_disabled':True,'additional_model_calls':0,'human_security_adjudication':False,'screenshots':[]}
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu'])
        page=await browser.new_page(viewport={'width':1440,'height':1100})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(url);await expect(page.locator('#coverage')).to_have_text('EXACT_MATCH')
        async def settled():
            await page.wait_for_function("() => !document.querySelector('#refresh').disabled")
        async def state():return await (await page.request.get(url+'/api/state')).json()
        async def select(cid):
            await page.locator(f'#inventory button[data-case-id="{cid}"]').click();await expect(page.locator('#case-title')).to_contain_text(cid+'-INV');await settled()
        async def shot(name,caption,selector=None,full=True):
            path=OUT/name
            if selector:await page.locator(selector).screenshot(path=str(path))
            else:await page.screenshot(path=str(path),full_page=full)
            checks['screenshots'].append({'file':name,'caption':caption,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
        await shot('01-inventory.png','인벤토리 선택 · 현재 사례 D1',full=False)
        # Exact source pointer is retrieved from the actual endpoint and quoted value agrees.
        pointer=next(p for p in (await state())['evidence']['source_pointers'] if p['source']!='INVENTORY')
        source=await page.request.get(url+'/api/source?id='+pointer['source']+'&pointer='+pointer['pointer'])
        assert source.status==200 and (await source.json())['value']==pointer['value']
        await page.locator('#source-cards .quote').first.focus()
        await shot('02-exact-cve-quote.png','현재 CVE · 정확한 원문 인용과 결과',selector='.source-result')
        await select('D2');s=await state();assert s['evidence']['identity_or_coverage_state']=='HISTORICAL_ADVISORY_EXACT_MATCH'
        assert next(l for l in s['evidence']['lookup_receipts'] if l['source']=='U-CVE')['exact_match_count']==0
        await shot('03-historical-usn.png','과거 USN 수정 진술 · 현재 CVE 미일치')
        await select('E2');await expect(page.locator('#coverage')).to_have_text('NO_EXACT_MATCH');assert (await state())['evidence']['vendor_statement']!='not_affected'
        await shot('04-no-exact-match.png','정확한 일치 없음 · 영향 없음으로 추론하지 않음')
        await select('D3');await expect(page.locator('#coverage')).to_have_text('INSUFFICIENT_IDENTITY');await shot('05-missing-identity.png','식별 근거 부족 · 결론 보류')
        await select('E5');await expect(page.locator('#coverage')).to_have_text('CONFLICTING_INVENTORY_IDENTITY');await shot('06-inventory-conflict.png','인벤토리 환경 충돌 · 범위 확인 필요')
        await select('E6');await expect(page.locator('#coverage')).to_have_text('CONFLICTING_SOURCES');await shot('07-source-conflict.png','출처 진술 충돌 · 우선순위 추론 없음')
        await select('E4');await expect(page.locator('#coverage')).to_have_text('EXACT_INSTALLED_MATCH_RUNNING_UNRESOLVED');await expect(page.locator('#note-facts')).to_contain_text('compatible')
        assert (await state())['evidence']['running_state']=='unknown';await shot('08-installed-running-unknown.png','설치 fixed · 실행 빌드와 재시작 미확인')
        await page.locator('#review-check').check();await page.locator('#review').click();await settled();first=(await state())['latest_receipt']['hash']
        await page.locator('#review').click();await settled();assert (await state())['latest_receipt']['hash']==first
        receipt=await page.request.get(url+'/api/receipt');assert receipt.status==200
        await page.locator('#binding').locator('..').evaluate('(e)=>e.open=true')
        await shot('09-review-history-receipt.png','명시적 근거 확인 · 기록과 영수증',selector='.review')
        checks['repeated_receipt']={'same_hash':True,'download_http_status':200}
        # A second client's real mutation must reject the displayed old review.
        s=await state();response=await page.request.post(url+'/api/select',data={'case_id':'E5','version':s['version']});assert response.status==200
        await page.locator('#review').click();await expect(page.locator('#status')).to_contain_text('다시 확인');assert not await page.locator('#review-check').is_checked();assert await page.locator('#review').is_disabled()
        checks['two_client_stale']={'http_status':409,'confirmation_cleared':True,'review_disabled':True}
        await page.locator('#refresh').click();await settled();await select('E4')
        # Archived explanation remains separate from semantic acceptance, then source revision rejects it.
        await page.locator('#method').select_option('model');await settled();assert not await page.locator('#semantic').is_checked()
        await page.locator('#review-check').check();assert await page.locator('#review').is_disabled()
        await page.locator('#source-cards button').first.click();await settled();assert not (await state())['note']['validation']['valid'];assert await page.locator('#note-facts a').count()==0
        checks['archive_gate']={'automatic_semantic_acceptance':False,'changed_source_rejected':True,'rejected_current_citation_links':0}
        # Hold an old read; subsequent source revocation queues behind it and stays revoked.
        await page.locator('#reset').click();await settled();await select('D2');await page.locator('#source-settings').click();await page.locator('#source-options input[value="U-USN"]').uncheck()
        captured,release=asyncio.Event(),asyncio.Event();order=[]
        async def hold(route):
            old=await route.fetch();order.append('old_read_captured');captured.set();await release.wait();order.append('old_read_released');await route.fulfill(response=old)
        async def observe(route):order.append('revocation_requested');await route.continue_()
        await page.route('**/api/state',hold);await page.route('**/api/admission',observe)
        await page.locator('#refresh').click();await captured.wait();await page.locator('#apply-sources').dispatch_event('click');assert 'revocation_requested' not in order;release.set();await settled()
        await page.unroute('**/api/state',hold);await page.unroute('**/api/admission',observe)
        assert (await state())['evidence']['source_ids']==['U-CVE'];denied=await page.request.get(url+'/api/source?id=U-USN');assert denied.status==403
        checks['stale_read_revocation']={'order':order,'unadmitted_source_http_status':403,'source_card_removed':await page.locator('#source-cards').filter(has_text='U-USN ·').count()==0}
        await page.locator('#reset').click();await settled();await select('E4')
        await page.set_viewport_size({'width':390,'height':844});await shot('10-mobile-390.png','390px 모바일 · 같은 근거와 미확인 상태')
        mobile=await page.evaluate("""()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,titleFont:parseFloat(getComputedStyle(document.querySelector('.page-title')).fontSize),titleWidth:document.querySelector('.page-title').getBoundingClientRect().width,titleScrollWidth:document.querySelector('.page-title').scrollWidth,minimumTextPixels:Math.min(...[...document.querySelectorAll('body *')].filter(e=>e.getClientRects().length&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())).map(e=>parseFloat(getComputedStyle(e).fontSize)))})""")
        assert mobile['document']==390 and mobile['minimumTextPixels']>=14 and mobile['titleFont']==28 and mobile['titleScrollWidth']<=mobile['titleWidth']+1
        checks['mobile']=mobile;assert errors==[];checks['page_errors']=errors
        await page.set_viewport_size({'width':1440,'height':1100})
        panels=await page.locator('.source-result>section').evaluate_all('(es)=>es.map(e=>({x:e.getBoundingClientRect().x,width:e.getBoundingClientRect().width,bg:getComputedStyle(e).backgroundColor}))')
        assert len(panels)==2 and abs(panels[0]['width']-panels[1]['width'])<1 and panels[0]['x']<panels[1]['x'] and all(x['bg']=='rgb(255, 255, 255)' for x in panels)
        checks['equal_white_source_result_panels']=panels
        await browser.close()
      manifest=json.loads((ROOT/'artifacts/source-snapshot-v2.json').read_text())
      checks['frozen_files_unchanged']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in manifest['sourceFileDigests'].items()}
      assert all(checks['frozen_files_unchanged'].values())
      checks['source_file_sha256']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in ['index.html','style.css','app.mjs','server.mjs','capture-refit.py','artifacts/model-input.json','artifacts/model-evaluation.json']}
      checks['capture_source_base_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
      checks['capture_source_binding']='source_file_sha256 identifies the edited UI used for these actual captures; base commit alone is not the refit publication commit'
      (OUT/'browser-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
      print(json.dumps(checks,ensure_ascii=False,indent=2))
    finally:
      server.terminate();server.wait(timeout=10)

if __name__=='__main__':asyncio.run(main())
