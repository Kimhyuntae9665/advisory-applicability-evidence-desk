"""CPU-only keyboard regression; never changes frozen capture/evaluation files."""
import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent


async def focus(page):
    return await page.evaluate("""() => {
        const active = document.activeElement;
        const row = active.closest('#inventory button');
        return {tag: active.tagName, id: active.id || null,
                inventoryCase: row?.querySelector('strong')?.textContent.split(' · ')[0] || null};
    }""")


async def tab_to(page, selector):
    for _ in range(100):
        await page.keyboard.press('Tab')
        if await page.locator(selector).evaluate('(element) => element === document.activeElement'):
            return
    raise AssertionError('Keyboard target not reached: ' + selector)


async def run(expect):
    server = subprocess.Popen(['node', '--input-type=module', '-e',
        "import {createDesk} from './server.mjs';const s=createDesk();"
        "s.listen(0,'127.0.0.1',()=>console.log(s.address().port));"],
        cwd=ROOT, stdout=subprocess.PIPE, text=True)
    try:
        url = 'http://127.0.0.1:' + server.stdout.readline().strip()
        evidence = {'browser': 'Google Chrome via Playwright', 'gpuDisabled': True,
                    'expectation': expect, 'modelCalls': 0, 'normalSelections': []}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome',
                                            args=['--no-sandbox', '--disable-gpu'])
            page = await browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await page.wait_for_selector('#inventory button')
            await page.wait_for_function("() => !document.querySelector('#inventory button').disabled")
            for index in [1, 2, 3]:
                selector = f'#inventory button:nth-child({index + 1})'
                await tab_to(page, selector)
                before = await focus(page)
                async with page.expect_response('**/api/select') as pending:
                    await page.keyboard.press('Enter')
                response = await pending.value
                assert response.status == 200
                state = await response.json()
                await page.wait_for_function("() => !document.querySelector('#inventory button').disabled")
                after = await focus(page)
                assert state['selected'] == before['inventoryCase']
                assert (after['inventoryCase'] == before['inventoryCase']) == (expect == 'fixed')
                if expect == 'failure':
                    assert after['tag'] == 'BODY'
                evidence['normalSelections'].append({'selected': state['selected'], 'before': before, 'after': after})

            # A held successful response must respect a later explicit keyboard focus choice.
            captured, release = asyncio.Event(), asyncio.Event()
            async def hold_selection(route):
                response = await route.fetch()
                captured.set()
                await release.wait()
                await route.fulfill(response=response)
            await page.route('**/api/select', hold_selection)
            await tab_to(page, '#inventory button:nth-child(5)')
            async with page.expect_response('**/api/select') as pending:
                await page.keyboard.press('Enter')
                await asyncio.wait_for(captured.wait(), 10)
                await tab_to(page, '#review-check')
                later = await focus(page)
                assert later['id'] == 'review-check'
                release.set()
            assert (await pending.value).status == 200
            await page.wait_for_function("() => !document.querySelector('#inventory button').disabled")
            after_later = await focus(page)
            assert after_later == later
            evidence['delayedResponseLaterFocus'] = {'chosenWhilePending': later, 'afterResponse': after_later}
            await page.unroute('**/api/select', hold_selection)

            # Failure must re-enable the original row without silently selecting another case.
            async def reject_selection(route):
                await route.fulfill(status=409, content_type='application/json',
                                    body=json.dumps({'error': 'stale_inspection', 'message': 'Controlled stale evidence.'}))
            await page.route('**/api/select', reject_selection)
            await tab_to(page, '#inventory button:nth-child(6)')
            before_error = await focus(page)
            async with page.expect_response('**/api/select') as pending:
                await page.keyboard.press('Enter')
            assert (await pending.value).status == 409
            await page.wait_for_function("() => !document.querySelector('#inventory button').disabled")
            after_error = await focus(page)
            assert (after_error['inventoryCase'] == before_error['inventoryCase']) == (expect == 'fixed')
            assert 'Controlled stale evidence' in await page.locator('#status').inner_text()
            active_case = await page.locator('#inventory button[aria-current="true"] strong').inner_text()
            assert active_case.split(' · ')[0] != before_error['inventoryCase']
            evidence['controlledFailure'] = {'status': 409, 'before': before_error, 'after': after_error,
                                             'selectedCaseUnchanged': True}
            await page.unroute('**/api/select', reject_selection)

            # Real stale-version rejection after another client changes the selection.
            captured, release = asyncio.Event(), asyncio.Event()
            async def hold_before_commit(route):
                captured.set()
                await release.wait()
                response = await route.fetch()
                await route.fulfill(response=response)
            await page.route('**/api/select', hold_before_commit)
            await tab_to(page, '#inventory button:nth-child(7)')
            async with page.expect_response('**/api/select') as pending:
                await page.keyboard.press('Enter')
                await asyncio.wait_for(captured.wait(), 10)
                current = await (await page.request.get(url + '/api/state')).json()
                changed = await page.request.post(url + '/api/select',
                    data={'case_id': 'D1', 'version': current['version']})
                assert changed.status == 200
                await tab_to(page, '#review-check')
                later = await focus(page)
                await page.locator('h1').click()
                body_choice = await focus(page)
                assert body_choice['tag'] == 'BODY'
                release.set()
            stale_response = await pending.value
            assert stale_response.status == 409
            assert (await stale_response.json())['error'] == 'stale_inspection'
            await page.wait_for_function("() => !document.querySelector('#inventory button').disabled")
            after_stale = await focus(page)
            assert after_stale == body_choice
            evidence['staleResponseLaterFocus'] = {'status': 409, 'keyboardChoiceWhilePending': later,
                                                  'laterBodyChoice': body_choice, 'afterResponse': after_stale,
                                                  'supersededInventoryFocusNotRestored': True}
            assert errors == []
            evidence['pageErrors'] = errors
            await browser.close()
        out = ROOT / 'artifacts' / f'keyboard-focus-{expect}.json'
        assert expect != 'failure' or not out.exists(), 'Before-fix evidence already exists; preserve it.'
        out.write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect', choices=['failure', 'fixed'], default='fixed')
    asyncio.run(run(parser.parse_args().expect))
