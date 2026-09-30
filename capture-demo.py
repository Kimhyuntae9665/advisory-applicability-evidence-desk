import asyncio,os,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parent
async def main():
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'private/browser-runtime')
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu'])
        c=await b.new_context(viewport={'width':1440,'height':1080},record_video_dir=str(ROOT/'private/paced-video'),record_video_size={'width':1440,'height':1080});page=await c.new_page();await page.goto('http://127.0.0.1:5088');await page.locator('#reset').click();await expect(page.locator('#coverage')).to_have_text('EXACT_MATCH')
        async def hold(seconds):await page.wait_for_timeout(seconds*1000)
        async def select(cid):
            await page.locator('#inventory button').filter(has_text=cid+' · '+cid+'-INV').click();await expect(page.locator('#case-title')).to_contain_text(cid+'-INV');await page.locator('.toolbar').scroll_into_view_if_needed()
        await hold(1.8);await select('D2');await hold(1.8);await page.locator('#source-cards').scroll_into_view_if_needed();await hold(3)
        await page.locator('#review-check').check();await hold(.8);await page.locator('#review').click();await expect(page.locator('#receipt')).to_have_text('Download current inspection receipt');await hold(1.8)
        await page.locator('.source-card').filter(has_text='U-USN ·').get_by_role('button',name='Simulate snapshot revision').click();await page.locator('#receipt').scroll_into_view_if_needed();await expect(page.locator('#receipt')).to_contain_text('historical');await hold(2.2)
        await select('E4');await expect(page.locator('#coverage')).to_have_text('EXACT_INSTALLED_MATCH_RUNNING_UNRESOLVED');await hold(2);await page.locator('.note-fact').filter(has_text='is compatible').scroll_into_view_if_needed();await hold(2.5)
        await select('E5');await expect(page.locator('#coverage')).to_have_text('CONFLICTING_INVENTORY_IDENTITY');await hold(2.4)
        await select('E6');await expect(page.locator('#coverage')).to_have_text('CONFLICTING_SOURCES');await page.locator('#source-cards').scroll_into_view_if_needed();await hold(3)
        await page.locator('#method').select_option('model');await expect(page.locator('#note-status')).to_contain_text('MODEL_NOT_RUN');await hold(2);assert await page.locator('#review').is_disabled()
        await page.locator('#method').select_option('template');await select('E2');await expect(page.locator('#coverage')).to_have_text('NO_EXACT_MATCH');await hold(2)
        video=page.video;await c.close();await video.save_as(str(ROOT/'artifacts/media/evidence-review.webm'));await b.close()
    (ROOT/'artifacts/video-provenance.json').write_text(json.dumps({'capture':'actual installed Chrome via Playwright, paced browser demonstration','fictional_inventory':True,'browser_automation':True,'model_calls':0,'human_security_adjudication':False,'review_clicks':'automated synthetic inspection only; not authenticated approval','cases':['D1','D2','E4','E5','E6','E2'],'source_files_modified':False,'local_snapshot_simulation':True},indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
