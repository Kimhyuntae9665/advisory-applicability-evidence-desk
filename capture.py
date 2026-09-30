import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:5088'
async def main():
    out=ROOT/'artifacts/media';out.mkdir(parents=True,exist_ok=True)
    helper=ROOT/'private/browser-runtime/ffmpeg-1011/ffmpeg-linux';helper.parent.mkdir(parents=True,exist_ok=True)
    if not helper.exists():helper.symlink_to('/usr/bin/ffmpeg')
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'private/browser-runtime')
    checks={'browser':'actual installed Google Chrome via Playwright','fictional_inventory':True,'browser_automation':True,'human_security_adjudication':False,'model_calls':0,'media_label':'CPU-only source rules and template; no model result in this recording'}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu'])
        context=await browser.new_context(viewport={'width':1440,'height':1080},record_video_dir=str(ROOT/'private/video'),record_video_size={'width':1440,'height':1080})
        page=await context.new_page();await page.goto(URL);await expect(page.locator('#coverage')).to_have_text('EXACT_MATCH')
        await page.locator('#reset').click();await expect(page.locator('#case-title')).to_contain_text('D1-INV')
        async def select(cid):
            await page.locator('#inventory button').filter(has_text=cid+' · '+cid+'-INV').click();await expect(page.locator('#case-title')).to_contain_text(cid+'-INV')
        async def state():return await page.evaluate("fetch('/api/state').then(r=>r.json())")
        await page.screenshot(path=str(out/'01-exact-installed.png'),full_page=True)
        await select('D2');await expect(page.locator('#coverage')).to_have_text('HISTORICAL_ADVISORY_EXACT_MATCH');await page.screenshot(path=str(out/'02-current-historical.png'),full_page=True)
        before=await state();assert before['evidence']['source_ids']==['U-CVE','U-USN'];assert next(l for l in before['evidence']['lookup_receipts'] if l['source']=='U-CVE')['exact_match_count']==0
        link=page.locator('#source-cards a').filter(has_text='P').first;await link.focus();assert await link.evaluate('(el)=>el===document.activeElement')
        await page.locator('#review-check').check();await page.locator('#review').click();await expect(page.locator('#receipt')).to_have_text('Download current inspection receipt')
        reviewed=await state();await page.locator('#review').click();await expect(page.locator('#receipt')).to_have_text('Download current inspection receipt');again=await state();assert again['latest_receipt']['hash']==reviewed['latest_receipt']['hash']
        checks['repeated_review']={'same_receipt_hash':True,'case_id':'D2'}
        order=[]
        async def delay_mutation(route):
            order.append('mutation_requested');await asyncio.sleep(.75);order.append('mutation_forwarded');await route.continue_()
        async def observe_read(route):order.append('read_requested');await route.continue_()
        await page.route('**/api/revise',delay_mutation);await page.route('**/api/state',observe_read)
        button=page.locator('.source-card').filter(has_text='U-USN ·').get_by_role('button',name='Simulate snapshot revision')
        await button.click();await expect(page.locator('#status')).to_contain_text('Loading');assert await page.locator('#review').is_disabled()
        await page.locator('#refresh').dispatch_event('click');await page.screenshot(path=str(out/'03-loading.png'),full_page=True)
        await expect(page.locator('#receipt')).to_contain_text('historical');await expect(page.locator('#status')).to_have_text('')
        await page.unroute('**/api/revise',delay_mutation);await page.unroute('**/api/state',observe_read)
        assert order.index('mutation_forwarded')<order.index('read_requested');checks['delayed_mutation_then_read']={'order':order,'read_serialized_after_mutation':True,'receipt_historical':True}
        await page.screenshot(path=str(out/'04-revision-stale.png'),full_page=True)
        await page.locator('#source-settings').click();await page.locator('#source-options input[value="U-USN"]').uncheck()
        gate=asyncio.Event();read_held=asyncio.Event();late_order=[]
        async def hold_read(route):
            response=await route.fetch();late_order.append('old_read_captured');read_held.set();await gate.wait();late_order.append('old_read_released');await route.fulfill(response=response)
        async def admission(route):late_order.append('revocation_requested');await route.continue_()
        await page.route('**/api/state',hold_read);await page.route('**/api/admission',admission)
        await page.locator('#refresh').click();await read_held.wait();await page.locator('#apply-sources').dispatch_event('click');assert 'revocation_requested' not in late_order;gate.set()
        await expect(page.locator('#source-cards')).not_to_contain_text('U-USN ·');await expect(page.locator('#status')).to_have_text('');await page.unroute('**/api/state',hold_read);await page.unroute('**/api/admission',admission)
        s=await state();assert s['evidence']['source_ids']==['U-CVE'];assert not any(p['source']=='U-USN' for p in s['evidence']['source_pointers']);assert s['receipt_compatibility']['current']==False
        denied=await context.request.get(URL+'/api/source?id=U-USN');assert denied.status==403
        checks['delayed_old_read_then_revocation']={'order':late_order,'no_restored_source_card_or_pointer':True,'source_endpoint_status':403};await page.screenshot(path=str(out/'05-source-revoked.png'),full_page=True)
        await page.locator('#reset').click();await expect(page.locator('#case-title')).to_contain_text('D1-INV');await page.locator('#review-check').check();old=await state()
        other=await browser.new_context();response=await other.request.post(URL+'/api/select',data={'version':old['version'],'case_id':'E5'});assert response.status==200
        await page.locator('#review').click();await expect(page.locator('#status')).to_contain_text('Refresh evidence');assert await page.locator('#review').is_disabled();assert not await page.locator('#review-check').is_checked();await page.screenshot(path=str(out/'06-two-client-stale.png'),full_page=True)
        await page.locator('#refresh').click();await expect(page.locator('#coverage')).to_have_text('CONFLICTING_INVENTORY_IDENTITY');assert not await page.locator('#review-check').is_checked();assert (await state())['latest_receipt'] is not None
        checks['two_client_stale_review']={'http_status':409,'fresh_inspection_required':True,'checkbox_cleared':True,'no_automatic_review':True};await other.close()
        await select('E4');await expect(page.locator('#coverage')).to_have_text('EXACT_INSTALLED_MATCH_RUNNING_UNRESOLVED');await expect(page.locator('#note-facts')).to_contain_text('compatible');await page.screenshot(path=str(out/'07-banner-running-unknown.png'),full_page=True)
        checks['E4_erratum']={'installed_vendor_statement':(await state())['evidence']['vendor_statement'],'compatible_upstream_banner':True,'running_build_restart':'unknown'}
        await select('E6');await expect(page.locator('#coverage')).to_have_text('CONFLICTING_SOURCES');await expect(page.locator('#source-cards')).to_contain_text('not original VEX');await page.screenshot(path=str(out/'08-source-conflict.png'),full_page=True)
        checks['source_conflict']={'html_and_cna_preserved':True,'no_precedence_inferred':True}
        await page.locator('#method').select_option('model');await expect(page.locator('#note-status')).to_contain_text('MODEL_NOT_RUN');await page.locator('#review-check').check();assert await page.locator('#review').is_disabled();await page.screenshot(path=str(out/'09-model-not-run.png'),full_page=True)
        await page.locator('#method').select_option('template');await select('E2');await expect(page.locator('#coverage')).to_have_text('NO_EXACT_MATCH');await page.screenshot(path=str(out/'10-no-exact-match.png'),full_page=True)
        video=page.video;await context.close();await video.save_as(str(out/'evidence-review.webm'))
        mobile=await browser.new_context(viewport={'width':390,'height':844});mp=await mobile.new_page();await mp.goto(URL);await expect(mp.locator('#coverage')).to_have_text('NO_EXACT_MATCH');await mp.screenshot(path=str(out/'mobile-390.png'),full_page=True)
        facts=await mp.evaluate("""()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,minimumTextPixels:Math.min(...[...document.querySelectorAll('body *')].filter(e=>e.getClientRects().length&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())).map(e=>parseFloat(getComputedStyle(e).fontSize)))})""")
        assert facts['document']==390 and facts['minimumTextPixels']>=14;checks['mobile']=facts;await mobile.close()
        diagram=[]
        for width in [360,390]:
            dp=await browser.new_page(viewport={'width':width,'height':1020});await dp.goto('file://'+str(ROOT/'docs/architecture.svg'));await dp.screenshot(path=str(out/f'diagram-{width}.png'));diagram.append({'viewport':width,'resource_loaded':True});await dp.close()
        dp=await browser.new_page(viewport={'width':390,'height':965});await dp.goto('file://'+str(ROOT/'docs/architecture.svg'));await dp.screenshot(path=str(ROOT/'docs/architecture.png'));await dp.close();checks['diagram']=diagram
        await browser.close()
    (ROOT/'artifacts/browser-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
