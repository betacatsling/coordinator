#!/usr/bin/env python3
"""Optional real Chromium smoke. Synthetic data only; not part of unittest discovery.

python tests/browser_dashboard_smoke.py --chromium /path/to/chromium --output /tmp/dashboard-qa
Requires Playwright installed separately. Never installs a browser or reads live projects.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from web_dashboard import make_server


def fixture(root, name, populated=True):
    root = Path(root).resolve()
    workspace = root / name
    runtime = workspace / '.project-delegation' / 'runtime'
    runtime.mkdir(parents=True)
    scope = {'workspace': str(workspace), 'repository': 'fixture/test-only',
             'project_node_id': 'SYNTHETIC_' + name, 'user_login': 'fixture-user'}
    config = root / (name + '.json')
    config.write_text(json.dumps(dict(scope, name='SYNTHETIC TEST · ' + name)), encoding='utf-8')
    jobs = {}
    for i, state in enumerate(['running', 'waiting_for_input', 'recovery_required', 'verified', 'accepted'] if populated else []):
        jid = 'fixture-job-' + str(i)
        title = ['Implement parser', 'Review approval', 'Recover receipt', 'Verify output', 'Accepted change'][i]
        jobs[jid] = {'id': jid, 'status': state, 'task': {'issue_id': 'fixture-task-' + str(i), 'title': title},
                     'created_at': time.time(), 'owned_paths': ['src/' + str(i)]}
        (runtime / (jid + '.receipt.json')).write_text(json.dumps({'status': state, 'thread_id': 'synthetic-session-' + str(i),
            'workspace': str(workspace), 'checks': [{'returncode': 0}]}), encoding='utf-8')
    for filename, body in [('binding.json', dict(scope=scope, binding={'provider_thread_id': 'synthetic-coordinator'})),
                           ('jobs.json', dict(scope=scope, jobs=jobs)), ('notifier.json', dict(scope=scope, outbox=[]))]:
        (runtime / filename).write_text(json.dumps(body), encoding='utf-8')
    if populated:
        (workspace / 'reports').mkdir()
        (workspace / 'reports' / 'SYNTHETIC-TEST.html').write_text('<h1>Synthetic QA artifact</h1>', encoding='utf-8')
    return config, runtime


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', help='Optional installed Chromium executable path')
    parser.add_argument('--output', type=Path, default=Path('/tmp/project-delegation-browser-qa'))
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    args.output.mkdir(parents=True, exist_ok=True)
    results = {'data': 'SYNTHETIC TEST FIXTURE; no live user projects', 'passed': []}
    with tempfile.TemporaryDirectory(prefix='delegation-browser-fixture-') as temp:
        first, runtime = fixture(Path(temp), 'Populated')
        second, _ = fixture(Path(temp), 'Empty', False)
        server = make_server([first, second], port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**({'executable_path': args.chromium} if args.chromium else {}))
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, color_scheme='light', accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.locator('.executor-card')).to_have_count(5)
                expect(page.locator('#content')).to_have_attribute('aria-busy', 'false')
                assert page.locator('.sidebar').evaluate('(el) => getComputedStyle(el).position') == 'fixed', 'CSS not applied'
                page.screenshot(path=str(args.output / 'desktop-light.png'), full_page=True)
                results['passed'].append('desktop render and backend integration')
                for category, count in [('active', 1), ('waiting', 1), ('blocked', 1), ('completed', 2), ('all', 5)]:
                    page.locator('[data-filter=' + category + ']').click()
                    expect(page.locator('.task-row')).to_have_count(count)
                page.locator('#task-search').fill('fixture-job-0')
                expect(page.locator('.task-row')).to_have_count(1)
                page.locator('#task-search').fill('no matching task')
                expect(page.locator('.task-row')).to_have_count(0)
                page.locator('#task-search').fill('')
                results['passed'].append('all status filters and search including executor ID')
                card = page.locator('[data-executor=fixture-job-0]')
                card.focus()
                card.press('Enter')
                expect(page.locator('#executor-dialog')).to_be_visible()
                expect(page.locator('#drawer-content')).to_contain_text('synthetic-session-0')
                expect(page.locator('#drawer-content')).to_contain_text('通过')
                page.screenshot(path=str(args.output / 'executor-details.png'), full_page=True)
                page.keyboard.press('Escape')
                expect(page.locator('#executor-dialog')).not_to_be_visible()
                expect(card).to_be_focused()
                card.click()
                page.locator('#close-drawer').click()
                expect(page.locator('#executor-dialog')).not_to_be_visible()
                card.click()
                page.mouse.click(10, 300)
                expect(page.locator('#executor-dialog')).not_to_be_visible()
                results['passed'].append('drawer keyboard, Escape, close, backdrop and focus restoration')
                page.locator('#refresh').click()
                expect(page.locator('#refresh')).to_be_enabled()
                page.locator('#task-search').fill('Implement')
                expect(page.locator('#task-search')).to_be_focused()
                page.wait_for_timeout(5500)  # Exercise actual automatic refresh interval.
                expect(page.locator('#task-search')).to_be_focused()
                expect(page.locator('#task-search')).to_have_value('Implement')
                page.locator('#task-search').fill('')
                results['passed'].append('manual refresh and search focus preservation over automatic refresh')
                with page.expect_download() as download:
                    page.locator('.report-link').first.click()
                artifact = download.value
                artifact.save_as(str(args.output / 'synthetic-report.html'))
                assert 'Synthetic QA artifact' in (args.output / 'synthetic-report.html').read_text()
                results['passed'].append('report download bytes')
                page.locator('#theme-toggle').click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                page.screenshot(path=str(args.output / 'desktop-dark.png'), full_page=True)
                page.locator('[data-project]').nth(1).click()
                expect(page.locator('.executor-card')).to_have_count(0)
                expect(page.locator('#project-title')).to_contain_text('Empty')
                page.locator('[data-project]').first.click()
                expect(page.locator('.executor-card')).to_have_count(5)
                results['passed'].append('theme and project switching including empty state')
                (runtime / 'jobs.json').write_text('{incomplete', encoding='utf-8')
                page.locator('#refresh').click()
                expect(page.locator('#notice')).to_contain_text('已过期')
                expect(page.locator('.executor-card')).to_have_count(5)
                page.screenshot(path=str(args.output / 'stale-state.png'), full_page=True)
                page.route('**/api/projects', lambda route: route.fulfill(status=500, body='fixture failure'))
                page.locator('#refresh').click()
                expect(page.locator('#notice')).to_contain_text('HTTP 500')
                expect(page.locator('.executor-card')).to_have_count(5)
                page.unroute('**/api/projects')
                results['passed'].append('stale snapshot and HTTP error retain last successful data')
                mobile_context = browser.new_context(viewport={'width': 390, 'height': 844}, color_scheme='dark')
                mobile = mobile_context.new_page()
                mobile.goto(url)
                expect(mobile.locator('#content')).to_have_attribute('aria-busy', 'false')
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile horizontal overflow'
                mobile.screenshot(path=str(args.output / 'mobile-dark.png'), full_page=True)
                results['passed'].append('mobile layout without horizontal overflow')
                assert not errors, errors
                results['passed'].append('no page JavaScript errors')
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    (args.output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    run()
