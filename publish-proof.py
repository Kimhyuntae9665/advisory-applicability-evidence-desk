"""Verify exact-commit CI and published README images with actual Chrome; no service writes."""
import asyncio,json,re,subprocess
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
async def main():
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    gh=str(Path.home()/'.local/bin/gh')
    runs=json.loads(subprocess.check_output([gh,'run','list','--commit',sha,'--json','databaseId,headSha,status,conclusion,url','--limit','5'],cwd=ROOT,text=True))
    if not runs or runs[0]['status']!='completed':print(json.dumps({'commit':sha,'ci':runs,'ready':False}));return
    ci=runs[0];assert ci['headSha']==sha and ci['conclusion']=='success'
    log=subprocess.check_output([gh,'run','view',str(ci['databaseId']),'--log'],cwd=ROOT,text=True)
    assert '# tests 39' in log and '# pass 39' in log and re.search(r'Ran 6 tests? in ',log)
    url='https://github.com/Kimhyuntae9665/advisory-applicability-evidence-desk/tree/'+sha
    evidence={'commit':sha,'ci':ci,'node_tests':39,'linux_cpu_transport_mocks':6,'exact_commit_ci_verified':True,'local_browser_checks_separate_from_ci':True,'additional_model_calls':0,'readme_url':url,'published_images':[]}
    async with async_playwright() as p:
      browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu'])
      page=await browser.new_page(viewport={'width':1440,'height':1100});response=await page.goto(url,wait_until='domcontentloaded');assert response.status==200
      await page.wait_for_selector('article img',timeout=30000)
      imgs=page.locator('article img');n=await imgs.count()
      for i in range(n):
        img=imgs.nth(i);src=await img.get_attribute('src')
        if not src or not ('ui-refit' in src or 'architecture.png' in src):continue
        await img.scroll_into_view_if_needed();await page.wait_for_function('(e)=>e.complete && e.naturalWidth>0',arg=await img.element_handle(),timeout=30000)
        facts=await img.evaluate('(e)=>({src:e.src,width:e.naturalWidth,height:e.naturalHeight,complete:e.complete})')
        evidence['published_images'].append(facts)
      assert len(evidence['published_images'])==11
      evidence['diagram_first']= 'architecture.png' in evidence['published_images'][0]['src'];assert evidence['diagram_first']
      await page.set_viewport_size({'width':390,'height':844})
      for img in await page.locator('article img').all():
        src=await img.get_attribute('src')
        if src and ('ui-refit' in src or 'architecture.png' in src):await img.scroll_into_view_if_needed();assert await img.evaluate('(e)=>e.complete&&e.naturalWidth>0')
      evidence['mobile_390_images_loaded']=True
      await browser.close()
    (ROOT/'private/ui-refit-publication-proof.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
if __name__=='__main__':asyncio.run(main())
