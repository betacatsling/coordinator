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
        jobs[jid] = {'id': jid, 'status': state, 'task': {'issue_id': 'fixture-task-' + str(i), 'title': title, 'url': 'https://github.com/fixture/test-only/issues/' + str(i + 1)},
                     'created_at': time.time(), 'owned_paths': ['src/' + str(i)]}
        (runtime / (jid + '.receipt.json')).write_text(json.dumps({'status': state, 'thread_id': 'synthetic-session-' + str(i),
            'workspace': str(workspace), 'checks': [{'returncode': 0}]}), encoding='utf-8')
    if populated:
        jobs['fixture-job-0']['report'] = {'local_path': str(workspace / 'reports' / 'SYNTHETIC-TEST.html')}
    for filename, body in [('binding.json', dict(scope=scope, binding={'provider_thread_id': 'synthetic-coordinator'})),
                           ('jobs.json', dict(scope=scope, jobs=jobs)), ('notifier.json', dict(scope=scope, outbox=[]))]:
        (runtime / filename).write_text(json.dumps(body), encoding='utf-8')
    if populated:
        (workspace / 'reports').mkdir()
        (workspace / 'reports' / 'SYNTHETIC-TEST.html').write_text('''<!doctype html><html><head><style>
            body { margin: 0; padding: 48px; color: #26332e; font: 15px/1.8 system-ui, sans-serif; }
            main { max-width: 820px; margin: auto; } h1 { font-size: 30px; letter-spacing: -1px; }
            .label { color: #227d69; font-size: 11px; letter-spacing: 2px; } h2 { font-size: 19px; margin-top: 35px; }
            .callout { padding: 20px 24px; background: #eef6f1; border-left: 3px solid #227d69; border-radius: 6px; }
            table { width: 100%; border-collapse: collapse; } td, th { text-align: left; border-bottom: 1px solid #e5eae6; padding: 13px 0; }
            @media(max-width:600px) { body { padding: 22px; } h1 { font-size: 24px; } }
            </style></head><body><main><div class="label">SYNTHETIC TEST · VERIFICATION REPORT</div>
            <h1>Synthetic QA artifact</h1><p>This fixture tests the local report reader. It contains no live project data.</p>
            <div class="callout"><strong>Ready for review</strong><br>Parser behavior and input handling are verified against synthetic examples.</div>
            <h2>Checks at a glance</h2><table><tr><th>Check</th><th>Result</th></tr><tr><td>Input validation</td><td>Passed</td></tr><tr><td>Output contract</td><td>Passed</td></tr><tr><td>Error recovery</td><td>Passed</td></tr></table>
            <h2>Implementation notes</h2><p>Reports stay alongside the project so reviewers can read the result, return to the task, and inspect its GitHub source.</p>
            <h2>Review boundary</h2><p>This example verifies presentation only. It does not establish live execution or acceptance.</p>
            <script>parent.__reportScriptRan = true</script><img src="https://report-test.invalid/leak">
            <a href="https://report-test.invalid/navigation">Unsafe external report link</a>
            </main></body></html>''', encoding='utf-8')
        (workspace / 'reports' / 'SYNTHETIC-OLDER.html').write_text('<h1>Older synthetic report</h1><p>Separate saved file</p>', encoding='utf-8')
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
                expect(page.locator('#connection')).to_have_text('本地读取成功')
                expect(page.locator('#service-health')).to_be_visible()
                expect(page.locator('#notification-status')).not_to_contain_text('检查正常')
                expect(page.locator('#notification-last-check')).to_contain_text('尚无成功读取记录')
                expect(page.locator('#notification-detail')).not_to_be_visible()
                page.locator('#service-health summary').click()
                expect(page.locator('#notification-detail')).to_contain_text('不代表处理或验收完成')
                page.locator('#refresh').click()
                expect(page.locator('#refresh')).to_be_enabled()
                expect(page.locator('#notification-detail')).to_be_visible()
                page.locator('#service-health summary').click()
                results['passed'].append('local read evidence, absent notification checks, collapsed service details and stable expansion on refresh')
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
                report_path = runtime.parent.parent / 'reports' / 'SYNTHETIC-TEST.html'
                report_button = page.locator('.reports-section .report-open', has_text='SYNTHETIC-TEST.html')
                report_button.focus()
                report_button.press('Enter')
                expect(page.locator('#report-reader')).to_be_visible()
                expect(page.locator('#overview')).not_to_be_visible()
                expect(page.locator('#reader-title')).to_have_text('SYNTHETIC-TEST.html')
                expect(page.locator('#reader-title')).to_be_focused()
                expect(page.locator('.report-frame')).to_have_attribute('sandbox', '')
                expect(page.locator('.report-frame')).to_have_attribute('referrerpolicy', 'no-referrer')
                assert not page.locator('.report-frame').get_attribute('srcdoc'), 'report must retain its independent response CSP'
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                assert page.frame_locator('.report-frame').locator('.callout').evaluate('(el) => getComputedStyle(el).backgroundColor') == 'rgb(238, 246, 241)', 'report inline CSS blocked by CSP'
                expect(page.locator('#reader-actions a', has_text='GitHub 任务')).to_have_attribute('href', 'https://github.com/fixture/test-only/issues/1')
                assert not page.evaluate('window.__reportScriptRan'), 'report script escaped sandbox'
                assert page.frame_locator('.report-frame').locator('a[href]').count() == 0
                assert page.frame_locator('.report-frame').locator('img[src^="https:"]').count() == 0
                reader_url = page.url
                page.screenshot(path=str(args.output / 'report-reader-desktop.png'), full_page=True)
                page.frame_locator('.report-frame').locator('body').evaluate('(el) => el.dataset.preserved = "yes"')
                page.locator('#refresh').click()
                expect(page.locator('#refresh')).to_be_enabled()
                expect(page.frame_locator('.report-frame').locator('body')).to_have_attribute('data-preserved', 'yes')
                original_report = report_path.read_text(encoding='utf-8')
                report_path.write_text(original_report + '<p>Updated synthetic content</p>', encoding='utf-8')
                page.locator('#refresh').click()
                expect(page.locator('#reader-update')).to_be_visible()
                expect(page.frame_locator('.report-frame').locator('body')).to_have_attribute('data-preserved', 'yes')
                page.locator('#reload-report').click()
                expect(page.frame_locator('.report-frame').locator('body')).to_contain_text('Updated synthetic content')
                expect(page.locator('#reader-update')).not_to_be_visible()
                with page.expect_download() as download:
                    page.locator('#reader-actions a[download]').click()
                artifact = download.value
                artifact.save_as(str(args.output / 'synthetic-report.html'))
                assert 'Synthetic QA artifact' in (args.output / 'synthetic-report.html').read_text()
                assert 'parent.__reportScriptRan' in (args.output / 'synthetic-report.html').read_text(), 'download changed original bytes'
                results['passed'].append('inline report, associated GitHub link, inert sandbox, original download, stable reading across refresh, explicit reload on change')
                page.go_back()
                expect(page.locator('#report-reader')).not_to_be_visible()
                expect(report_button).to_be_focused()
                page.go_forward()
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                page.locator('.report-history summary').click()
                page.locator('.report-history .report-open', has_text='SYNTHETIC-OLDER.html').click()
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Older synthetic report')
                expect(page.locator('#reader-actions a', has_text='GitHub 仓库')).to_have_attribute('href', 'https://github.com/fixture/test-only')
                page.locator('#close-reader').click()
                expect(page.locator('#report-reader')).not_to_be_visible()
                card.click()
                page.locator('#drawer-content [data-report]').first.click()
                expect(page.locator('#executor-dialog')).not_to_be_visible()
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                page.locator('#close-reader').click()
                expect(card).to_be_focused()
                page.goto(reader_url)
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                page.locator('#close-reader').click()
                expect(page.locator('#report-reader')).not_to_be_visible()
                results['passed'].append('keyboard entry, reader back/forward, actual-file history, drawer-to-reader without stacked dialogs, deep link and focus restoration')
                page.route('**/preview/**', lambda route: route.fulfill(status=500, body='fixture failure'))
                report_button.click()
                expect(page.locator('#reader-status')).to_contain_text('HTTP 500')
                expect(page.locator('.report-frame')).to_have_count(0)
                page.unroute('**/preview/**')
                page.locator('#retry-report').click()
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                report_path.unlink()
                page.locator('#refresh').click()
                expect(page.locator('#reader-status')).to_contain_text('找不到这份报告')
                expect(page.locator('.report-frame')).to_have_count(0)
                report_path.write_text(original_report, encoding='utf-8')
                page.locator('#refresh').click()
                expect(page.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                page.locator('[data-project]').nth(1).click()
                expect(page.locator('#report-reader')).not_to_be_visible()
                expect(page.locator('.report-frame')).to_have_count(0)
                page.locator('[data-project]').first.click()
                expect(page.locator('.executor-card')).to_have_count(5)
                results['passed'].append('preview HTTP error/retry, removed and restored artifact, project navigation disposes report')
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
                last_successful_read = page.locator('#last-update').inner_text()
                page.locator('#refresh').click()
                expect(page.locator('#notice')).to_contain_text('HTTP 500')
                expect(page.locator('#connection')).to_have_text('读取失败 · 保留记录')
                expect(page.locator('#last-update')).to_have_text(last_successful_read)
                expect(page.locator('#notification-status')).to_contain_text('状态待刷新')
                expect(page.locator('.executor-card')).to_have_count(5)
                page.unroute('**/api/projects')
                results['passed'].append('stale snapshot and HTTP error retain last successful data')
                mobile_context = browser.new_context(viewport={'width': 390, 'height': 844}, color_scheme='dark')
                mobile = mobile_context.new_page()
                mobile.goto(url)
                expect(mobile.locator('#content')).to_have_attribute('aria-busy', 'false')
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile horizontal overflow'
                mobile.screenshot(path=str(args.output / 'mobile-dark.png'), full_page=True)
                mobile.locator('.reports-section .report-open', has_text='SYNTHETIC-TEST.html').click()
                expect(mobile.frame_locator('.report-frame').locator('h1')).to_have_text('Synthetic QA artifact')
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile reader horizontal overflow'
                mobile.screenshot(path=str(args.output / 'report-reader-mobile.png'), full_page=True)
                mobile.locator('.report-history summary').click()
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile report history horizontal overflow'
                mobile.locator('.report-history .report-open', has_text='SYNTHETIC-OLDER.html').click()
                expect(mobile.frame_locator('.report-frame').locator('h1')).to_have_text('Older synthetic report')
                mobile.locator('#close-reader').click()
                expect(mobile.locator('#report-reader')).not_to_be_visible()
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
