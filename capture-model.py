import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parent
async def main():
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'private/browser-runtime');out=ROOT/'artifacts/media'
    records=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu'])
        context=await browser.new_context(viewport={'width':1440,'height':1080},record_video_dir=str(ROOT/'private/model-video'),record_video_size={'width':1440,'height':1080});page=await context.new_page();await page.goto('http://127.0.0.1:5088');await page.locator('#reset').click();await expect(page.locator('#coverage')).to_have_text('EXACT_MATCH');await page.wait_for_timeout(1000)
        async def select(cid):
            await page.locator('#inventory button').filter(has_text=cid+' · '+cid+'-INV').click();await expect(page.locator('#case-title')).to_contain_text(cid+'-INV');await page.locator('#method').select_option('model');await expect(page.locator('#note-status')).to_contain_text('PROPOSED_EXPLANATION')
        for cid in ['E4','E5','E6']:
            await select(cid);await page.locator('.toolbar').scroll_into_view_if_needed();await page.wait_for_timeout(1400);await page.locator('.notes').scroll_into_view_if_needed();await page.wait_for_timeout(1500)
            assert await page.locator('#review').is_disabled();assert not await page.locator('#semantic').is_checked()
            s=await page.evaluate("fetch('/api/state').then(r=>r.json())");assert s['note']['validation']['valid'];assert s['latest_receipt'] is None
            records.append({'case_id':cid,'status':s['note']['status'],'citation_bound':True,'semantic_checkbox':False,'model_receipt':None,'source_state':s['evidence']['identity_or_coverage_state']});await page.screenshot(path=str(out/f'model-{cid}-proposed.png'),full_page=True)
        await select('E4');original=await page.evaluate("fetch('/api/state').then(r=>r.json())")
        await page.locator('.source-card').get_by_role('button',name='Simulate snapshot revision').click();await expect(page.locator('#note-status')).to_contain_text('ARCHIVE_REJECTED');assert await page.locator('#review').is_disabled();assert await page.locator('#note-facts a').count()==0
        details=page.locator('#note-facts details');await details.locator('summary').focus();await page.keyboard.press('Enter');await expect(details).to_have_attribute('open','');await page.locator('.notes').scroll_into_view_if_needed();await page.wait_for_timeout(1400);await page.screenshot(path=str(out/'model-source-stale.png'),full_page=True)
        stale=await page.evaluate("fetch('/api/state').then(r=>r.json())");assert stale['note']['note']['evidence_fingerprint']==original['note']['note']['evidence_fingerprint'];assert stale['evidence']['evidence_fingerprint']!=original['evidence']['evidence_fingerprint']
        await page.locator('#reset').click();await expect(page.locator('#case-title')).to_contain_text('D1-INV');await select('E4');await page.wait_for_timeout(1400)
        video=page.video;await context.close();await video.save_as(str(out/'recorded-explanation-review.webm'))
        mobile=await browser.new_context(viewport={'width':390,'height':844});mp=await mobile.new_page();await mp.goto('http://127.0.0.1:5088');await expect(mp.locator('#note-status')).to_contain_text('PROPOSED_EXPLANATION');await mp.screenshot(path=str(out/'model-mobile-390.png'),full_page=True);assert await mp.evaluate('document.documentElement.scrollWidth')==390;await mobile.close();await browser.close()
    (ROOT/'artifacts/model-browser-checks.json').write_text(json.dumps({'browser':'actual Chrome via Playwright','media':'stored six-case Qwen outputs; no live inference in capture','model_calls_in_capture':0,'human_accepted_model_notes':0,'browser_automation':True,'cases':records,'changed_source':{'status':'ARCHIVE_REJECTED','current_citation_links':0,'original_model_fingerprint_preserved':True,'confirmation_disabled':True,'raw_original_keyboard_focusable':True},'mobile_width':390,'document_width':390},indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
