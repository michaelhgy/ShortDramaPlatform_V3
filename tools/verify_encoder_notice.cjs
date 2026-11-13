/** Isolated browser check; all API calls use fixtures, never the business server. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const arg = name => process.argv[process.argv.indexOf(name) + 1];
if (!process.argv.includes('--dist') || !process.argv.includes('--encoding') || !process.argv.includes('--output'))
  throw new Error('Usage: --dist build-directory --encoding encoder-status.json --output evidence-directory');
const root = path.resolve(arg('--dist')), output = path.resolve(arg('--output'));
const cpu = JSON.parse(fs.readFileSync(arg('--encoding'), 'utf8'));
assert.equal(cpu.encoder, 'libx264');
const gpu = { encoder: 'h264_nvenc', warning: null };
const job = (id, status, encoding) => ({
  id, name: id, status, encoding, task_id: 'test-task', material_id: id, template_id: 'test-template',
  account_name: '隔离检查账号', drama_name: '测试剧', stage: '复用已完成模板，编码成片',
  progress: status === 'done' ? 100 : 35, elapsed_seconds: 25, error: '', output_path: null,
});
let finalJobs = [
  job('正在使用 CPU', 'running', cpu), job('历史 CPU 成片', 'done', cpu),
  job('等待新检测', 'waiting', null), job('显卡编码成片', 'done', gpu), job('旧记录缺少日志', 'done', null),
];
const templateJobs = [{
  id: 'template-test', status: 'running', encoding: cpu, progress: 35,
  elapsed_seconds: 25, stage: '正在制作模板', error: '', output_path: null,
  display_name: '模板提示验证', ordinal: 1,
  batch_id: 'batch', batch_name: '测试批次', seconds: 180, family: '测试系列',
  preview_url: null, created_at: '2026-10-20T12:00:00', output_sha256: null,
}];
const queue = jobs => ({
  jobs, paused: false,
  counts: Object.fromEntries(['waiting', 'running', 'done', 'error', 'cancelled'].map(s => [s, jobs.filter(j => j.status === s).length])),
});
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
  if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
  fs.readFile(file, (error, body) => {
    if (error) { response.writeHead(404).end(); return; }
    const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
    response.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
    response.end(body);
  });
});
(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  const errors = [], writes = [], checks = [];
  try {
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
    await context.route('**/api/**', route => {
      const request = route.request(), url = new URL(request.url());
      if (!['GET', 'HEAD'].includes(request.method())) {
        writes.push(`${request.method()} ${url.pathname}`); return route.abort();
      }
      if (url.pathname === '/api/v2/task-center') return route.fulfill({ json: {
        tasks: [], executors: [], dramaPriorities: [], isQueuePaused: false,
        finalComposition: queue(finalJobs), templateGeneration: queue(templateJobs),
        sceneryProcessing: queue([]),
      } });
      if (url.pathname === '/api/v2/settings') return route.fulfill({ json: { publish_presets: ['12:00'], publish_date_offset_days: 0 } });
      if (url.pathname === '/api/v2/revenue/source-data') return route.fulfill({ json: { rows: [], accounts: [], theaters: [] } });
      return route.fulfill({ json: { items: [] } });
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const openFull = async () => {
      await page.getByRole('button', { name: /执行.*等待.*完成/ }).first().click();
      await page.getByRole('dialog', { name: '全局任务中心' }).waitFor();
    };
    const notes = scope => scope.getByRole('note', { name: '显卡编码提示' });
    await page.goto(`http://127.0.0.1:${server.address().port}`, { waitUntil: 'domcontentloaded' });
    await openFull();
    const full = page.getByRole('dialog', { name: '全局任务中心' });
    await full.getByText('正在使用 CPU', { exact: true }).waitFor();
    assert.equal(await notes(full).count(), 2);
    assert.ok((await notes(full).first().innerText()).includes('570.0'));
    await notes(full).first().screenshot({ path: path.join(output, 'notice.png') });
    await full.getByText('查看本次检测详情', { exact: true }).first().click();
    await full.locator('pre').first().waitFor({ state: 'visible' });
    assert.ok((await full.locator('pre').first().innerText()).includes('Required: 13.0 Found: 11.0'));
    await page.screenshot({ path: path.join(output, 'task-center.png') });
    checks.push('running and completed CPU warnings; GPU, waiting and missing-log records have no warning; raw evidence expands');
    await full.getByRole('button', { name: /^已完成 / }).click();
    assert.equal(await notes(full).count(), 1);
    await full.getByRole('tab', { name: /^模板制作/ }).click();
    await full.getByText('模板提示验证', { exact: true }).waitFor();
    assert.equal(await notes(full).count(), 1);
    checks.push('completed filter retains historical warning; template queue uses the same notice');
    await full.getByRole('button', { name: '关闭任务中心' }).click();
    await page.getByRole('button', { name: /任务监控/ }).first().click();
    const monitor = page.getByRole('dialog', { name: '任务监控', exact: true });
    await monitor.waitFor();
    assert.equal(await notes(monitor).count(), 2);
    assert.equal(await monitor.locator('details').count(), 0);
    assert.equal(await monitor.locator('article').first().evaluate(element => {
      const list = element.parentElement;
      return list.scrollHeight > list.clientHeight;
    }), false);
    await page.screenshot({ path: path.join(output, 'monitor.png') });
    finalJobs = finalJobs.map(j => j.status === 'running' ? { ...j, encoding: gpu } : j);
    await page.waitForFunction(() => document.querySelector('[aria-label="任务监控"] [aria-label="成片合成队列"] [aria-label="显卡编码提示"]') === null);
    assert.equal(await notes(monitor).count(), 1);
    checks.push('monitor shows current CPU jobs; polling removes recovered GPU warning');
    await monitor.getByRole('button', { name: '关闭任务监控' }).click();
    await openFull();
    await page.setViewportSize({ width: 720, height: 900 });
    assert.equal(await notes(full).count(), 1);
    assert.equal(await full.evaluate(element => element.scrollWidth > element.clientWidth), false);
    await page.screenshot({ path: path.join(output, 'narrow-task-center.png') });
    checks.push('history remains after recovery; narrow dialog does not overflow horizontally');
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({ status: 'PASS', checks, errors, writes }, null, 2));
    console.log(JSON.stringify({ status: 'PASS', checks, errors, writes }));
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
