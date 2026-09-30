import asyncio,json,subprocess
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
URL='https://github.com/Kimhyuntae9665/advisory-applicability-evidence-desk'
async def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();published=URL+'/tree/'+commit;results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--disable-gpu'])
        for width in [360,390,1440]:
            page=await browser.new_page(viewport={'width':width,'height':1050});response=await page.goto(published,wait_until='domcontentloaded',timeout=60000);facts=[]
            for name,selector in [('diagram','article img[alt^="Fictional inventory"]'),('cpuScreenshot','article img[alt^="Actual CPU browser"]'),('modelScreenshot','article img[alt^="Actual browser: recorded E4"]')]:
                img=page.locator(selector);await img.wait_for();await img.scroll_into_view_if_needed();await img.evaluate('(el)=>el.decode()');data=await img.evaluate('(el)=>({loaded:el.complete&&el.naturalWidth>0,naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight,displayWidth:el.getBoundingClientRect().width})');assert response.status==200 and data['loaded'] and data['displayWidth']<=width;facts.append({'kind':name,**data})
            await page.screenshot(path=str(ROOT/f'artifacts/media/published-model-{width}.png'));results.append({'viewport':width,'status':response.status,'images':facts});await page.close()
        await browser.close()
    (ROOT/'artifacts/published-model-checks.json').write_text(json.dumps({'repository':URL,'published_commit':commit,'checked_url':published,'browser':'actual installed Google Chrome via Playwright','model_calls':0,'checks':results},indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
