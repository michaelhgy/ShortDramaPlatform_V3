/** Built production UI with intercepted APIs and a synthetic video; never contacts the business service. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const out = path.resolve(process.argv[2] || 'local-test-output/material-manager-20261105');
const fixture = JSON.parse(fs.readFileSync('local-test-output/insertions/ui-fixture.json', 'utf8'));
const task = structuredClone(fixture.task);
task.id = 'a'.repeat(32); task.created_date = '2026-11-05'; task.planned_publish_at = '2026-11-05';
task.account_name = '素材管理验收账号'; task.drama_name = '隔离演示剧集';
task.paths = { root: 'D:/isolated/task', materials: 'D:/isolated/task/素材', template: 'D:/isolated/task/模板', finals: 'D:/isolated/task/成片' };
task.materials = Array.from({ length: 25 }, (_, index) => ({ id: (index + 1).toString(16).padStart(32, '0'), name: `隔离演示剧集-${index + 1}.mp4`, path: `D:/isolated/task/素材/隔离演示剧集-${index + 1}.mp4`, sequence_no: index + 1, size_bytes: 39845888, duration_seconds: 620, thumbnail_path: 'isolated-preview.svg', resolution: '720x1280', scanned_at: '2026-11-05T12:00:00', status: 'available', insertion_strategy: null }));
task.materials_count = 25;
const videoId = 'b'.repeat(32);
task.videos = [{ id: videoId, source_material_id: task.materials[0].id, engine: 'ffmpeg', status: 'ffmpeg_done', sequence_no: 1, name: task.materials[0].name, size_bytes: 10000, source_duration_seconds: 620, draft_path: '', output_path: 'D:/isolated/task/成片/隔离演示剧集-1.mp4', output_exists: true }];
fixture.parameters.midroll_endroll.configured = true;
const root = path.join(out, 'dist');
const media = fs.readFileSync(path.join(out, 'preview-test.mp4'));
const poster = '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="640"><rect width="360" height="640" fill="#26364a"/><circle cx="180" cy="240" r="75" fill="#dde5ed"/><path d="M65 560 Q65 340 180 340 Q295 340 295 560" fill="#a5b4c6"/><text x="180" y="610" fill="white" font-size="24" text-anchor="middle">视频预览测试素材</text></svg>';
const requests = [], errors = [], checks = [];
let blocked = false, stale = false;
const server = http.createServer((req, res) => {
  const name = decodeURIComponent(new URL(req.url, 'http://local').pathname);
  const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name));
  if (!file.startsWith(root + path.sep)) return res.writeHead(403).end();
  fs.readFile(file, (error, body) => { if (error) return res.writeHead(404).end(); res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' })[path.extname(file)] || 'application/octet-stream'); res.end(body); });
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname !== '127.0.0.1') return route.abort();
      return route.fallback();
    });
    await context.route('**/api/**', route => {
      const req = route.request(), p = new URL(req.url()).pathname;
      const json = value => route.fulfill({ json: value });
      if (p.endsWith('/media')) return route.fulfill({ contentType: 'video/mp4', body: media, headers: { 'Accept-Ranges': 'bytes' } });
      if (p.endsWith('/thumbnail') || p.endsWith('/cover')) return route.fulfill({ contentType: 'image/svg+xml', body: poster });
      if (req.method() === 'POST') {
        const body = req.postDataJSON(); requests.push({ path: p, body });
        const match = p.match(/\/production-files\/([a-f0-9]+)\/(.+)$/);
        if (match) {
          const clip = task.materials.find(m => m.id === match[1]);
          if (!clip) return route.fulfill({ status: 404, json: { error: '素材不存在' } });
          if (match[2] === 'insertion-strategy') { clip.insertion_strategy = body.strategy; return json(task); }
          if (match[2] === 'delete-preview') return json({ material_id: clip.id, file_name: clip.name, source_path: clip.path, can_delete: !blocked, blocked_reason: blocked ? '本素材正在合成，请等待当前任务结束后再删除' : '', files: [{ path: clip.path, exists: true }, ...(task.videos.some(v => v.source_material_id === clip.id) ? [{ path: task.videos[0].output_path, exists: true }] : [])], cache_directories: [], video_count: task.videos.filter(v => v.source_material_id === clip.id).length, job_count: task.videos.filter(v => v.source_material_id === clip.id).length, confirmation_token: 'confirmed-' + clip.id });
          if (match[2] === 'delete') {
            if (stale) return route.fulfill({ status: 400, json: { error: '素材或合成任务在确认期间发生变化，请重新打开删除确认' } });
            assert.equal(body.confirmation_token, 'confirmed-' + clip.id);
            task.materials = task.materials.filter(m => m.id !== clip.id); task.materials_count = task.materials.length;
            task.videos = task.videos.filter(v => v.source_material_id !== clip.id);
            return json({ task, deleted_paths: [clip.path], audit_path: 'isolated-deletion-audit.json' });
          }
        }
        if (p !== '/api/v3/operations-dashboard') throw Error('Unexpected write ' + p);
      }
      if (p === '/api/v3/operations-dashboard') return json({ schema: 'isolated', today: '2026-11-05', latest_date: '2026-11-04', accounts: [], theaters: [], video_accounts: [], video_account_daily: [], video_posts: [], video_post_punishments: [], revenue_account_periods: [], coverage: {} });
      if (p === '/api/v2/engine-parameters') return json(fixture.parameters);
      if (p === '/api/v3/template-generation/config') return json(fixture.templateConfig);
      if (p === '/api/v2/production-task-summaries' || p === '/api/v2/production-tasks') return json({ items: [task] });
      if (p === `/api/v2/production-tasks/${task.id}/details`) return json(task);
      if (p === '/api/v2/template-library') return json({ items: [], directory: '隔离测试', selected_template_id: null, selection_locked: false });
      if (p === '/api/v2/task-center') return json({ tasks: [], executors: [], dramaPriorities: [], isQueuePaused: false, finalComposition: { jobs: [], paused: false, counts: {} } });
      if (p === '/api/v2/settings') return json({ publish_presets: ['12:00'], publish_date_offset_days: 0 });
      if (p === '/api/v2/revenue/source-data') return json({ rows: [], accounts: [], theaters: [] });
      return json({ items: [], tasks: [], accounts: [], theaters: [], dramas: [], jobs: [], runs: [] });
    });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message)); page.setDefaultTimeout(15000);
    await page.goto(`http://127.0.0.1:${server.address().port}`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '生产中心', exact: true }).click();
    const region = page.getByTestId('material-region');
    await region.getByText('25', { exact: true }).waitFor();
    const color = await region.locator('strong').evaluate(element => ({ color: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor }));
    assert.deepEqual(color, { color: 'rgb(221, 253, 0)', background: 'rgb(26, 29, 46)' }); checks.push('count-theme');
    await page.getByRole('button', { name: '素材区域', exact: true }).click();
    let dialog = page.getByRole('dialog', { name: '素材管理', exact: true });
    await dialog.getByLabel('本素材中插规则').selectOption('off');
    await dialog.getByLabel('本素材尾插规则').selectOption('on');
    await dialog.getByRole('button', { name: '保存本片设置', exact: true }).click();
    await dialog.getByText('已保存，后续新提交的成片使用此设置。', { exact: true }).waitFor();
    assert.deepEqual(task.materials[0].insertion_strategy, { midroll: { enabled: false }, endroll: { enabled: true } });
    assert.equal(await dialog.count(), 1); checks.push('save-without-closing');
    const loaded = await dialog.locator('video').evaluate(video => video.readyState >= 1);
    assert.equal(loaded, true); checks.push('synthetic-video-loaded');
    await dialog.screenshot({ path: path.join(out, 'manager-1440.png') });
    await dialog.getByLabel('本素材中插规则').selectOption('on');
    await dialog.getByRole('button', { name: '选择素材 隔离演示剧集-2.mp4', exact: true }).click();
    const unsaved = page.getByRole('alertdialog', { name: '未保存的素材设置' });
    await unsaved.getByRole('button', { name: '继续编辑' }).click();
    assert.equal(await dialog.getByLabel('本素材中插规则').inputValue(), 'on');
    await dialog.getByRole('button', { name: '选择素材 隔离演示剧集-2.mp4', exact: true }).click();
    await unsaved.getByRole('button', { name: '放弃修改并继续' }).click();
    assert.equal(await dialog.getByLabel('本素材中插规则').inputValue(), 'inherit'); checks.push('unsaved-change-guard');
    await dialog.getByLabel('搜索素材').fill('不存在的文件'); await dialog.getByText('没有匹配的素材').waitFor();
    await dialog.getByLabel('搜索素材').fill(''); checks.push('search');
    for (const [width, height] of [[1920,1080],[1280,720],[900,700]]) {
      await page.setViewportSize({ width, height });
      assert.equal(await dialog.evaluate(e => e.scrollWidth > e.clientWidth), false);
      const close = await dialog.getByRole('button', { name: '关闭', exact: true }).boundingBox();
      assert.ok(close.y + close.height <= height);
      await dialog.screenshot({ path: path.join(out, `manager-${width}.png`) });
    }
    checks.push('three-window-sizes');
    blocked = true;
    await dialog.getByRole('button', { name: '删除素材', exact: true }).click();
    let deletion = page.getByRole('alertdialog', { name: '删除素材及对应成片' });
    await deletion.getByText('本素材正在合成，请等待当前任务结束后再删除', { exact: true }).waitFor();
    assert.equal(await deletion.getByRole('button', { name: '确认删除原文件及成片' }).isDisabled(), true);
    await deletion.getByRole('button', { name: '取消', exact: true }).click(); blocked = false; checks.push('running-deletion-blocked');
    await dialog.getByRole('button', { name: '删除素材', exact: true }).click();
    await deletion.getByRole('button', { name: '确认删除原文件及成片' }).waitFor();
    await deletion.getByRole('button', { name: '取消', exact: true }).click();
    assert.equal(requests.filter(r => r.path.endsWith('/delete')).length, 0); checks.push('cancel-does-not-delete');
    stale = true;
    await dialog.getByRole('button', { name: '删除素材', exact: true }).click();
    await deletion.getByRole('button', { name: '确认删除原文件及成片' }).click();
    await deletion.getByText('素材或合成任务在确认期间发生变化，请重新打开删除确认', { exact: true }).waitFor();
    stale = false; await deletion.getByRole('button', { name: '重新读取' }).click();
    await deletion.getByRole('button', { name: '确认删除原文件及成片' }).click();
    await deletion.waitFor({ state: 'hidden' });
    assert.equal(task.materials.length, 24); assert.equal(await dialog.count(), 1); checks.push('deletion-reload-and-next-material');
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await page.setViewportSize({ width: 1440, height: 1000 });
    const insertionButton = region.getByRole('button', { name: `${task.materials[0].name}插片设置`, exact: true });
    await insertionButton.click();
    let legacyInsertion = page.getByRole('dialog', { name: '本素材插片设置', exact: true });
    await legacyInsertion.getByLabel('本素材尾插规则').selectOption('off');
    await legacyInsertion.getByRole('button', { name: '保存', exact: true }).click();
    await legacyInsertion.waitFor({ state: 'hidden' });
    assert.equal(task.materials[0].insertion_strategy.endroll.enabled, false);
    await insertionButton.click();
    await legacyInsertion.getByRole('button', { name: '恢复跟随剧集', exact: true }).click();
    await legacyInsertion.waitFor({ state: 'hidden' });
    assert.equal(task.materials[0].insertion_strategy, null); checks.push('existing-insertion-dialog');
    await region.locator('.w-32').first().dblclick();
    const preview = page.locator('div.fixed').filter({ has: page.getByText('原始素材', { exact: true }) }).last();
    const deleteButton = preview.getByRole('button', { name: '删除素材', exact: true });
    const closeButton = preview.getByRole('button', { name: '关闭', exact: true });
    await deleteButton.waitFor();
    const deleteBox = await deleteButton.boundingBox(), closeBox = await closeButton.boundingBox();
    assert.ok(deleteBox.x < closeBox.x); checks.push('legacy-preview-delete-left-of-close');
    await preview.screenshot({ path: path.join(out, 'legacy-preview.png') });
    await deleteButton.click();
    deletion = page.getByRole('alertdialog', { name: '删除素材及对应成片' });
    await deletion.getByText('对应成片 1 条 · 合成任务 1 条', { exact: true }).waitFor();
    await deletion.screenshot({ path: path.join(out, 'deletion-confirmation.png') });
    await deletion.getByRole('button', { name: '确认删除原文件及成片' }).click();
    await deletion.waitFor({ state: 'hidden' });
    await preview.waitFor({ state: 'hidden' });
    assert.equal(task.materials.length, 23); assert.equal(task.videos.length, 0);
    await region.getByText('23', { exact: true }).waitFor(); checks.push('legacy-preview-cascade-and-refresh');
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, 'ui-verification.json'), JSON.stringify({ status: 'PASS', checks, requests, errors }, null, 2));
    console.log(JSON.stringify({ status: 'PASS', checks, errors }));
  } finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
