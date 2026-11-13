/**
 * Browser regression for task-center and revenue navigation white screens.
 * Serve dist/ locally, then pass --url. Every API request is intercepted:
 * this check never reads or writes the business database or starts jobs.
 * PLAYWRIGHT_MODULE and PLAYWRIGHT_CHROMIUM_PATH can point to local tooling.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const option = (name) => process.argv[process.argv.indexOf(name) + 1];
const baseUrl = process.argv.includes('--url') ? option('--url') : null;
if (!baseUrl) throw new Error('Usage: node tools/verify_ui_navigation.cjs --url http://127.0.0.1:5194');
const output = path.resolve(process.argv.includes('--output') ? option('--output') : `local-test-output/ui-navigation-${Date.now()}`);
fs.mkdirSync(output, { recursive: true });

const date = (offset) => {
  const value = new Date();
  value.setDate(value.getDate() + offset);
  return value.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
};
const factDate = date(-3);
const updatedAt = `${factDate}T12:00:00`;
const source = {
  rows: [{ id: 'revenue-test', revenue_date: factDate, account_id: 'account-test', account_nickname: '白屏回归账号', theater_id: 'theater-test', theater_name: '青柠剧场', amount: '12.34', quality: 'direct', updated_at: updatedAt }],
  accounts: [{ id: 'account-test', nickname: '白屏回归账号', status: '正常', theater_id: 'theater-test' }],
  theaters: [{ id: 'theater-test', name: '青柠剧场', status: '启用' }],
};
const video = {
  id: 'detail-test', revenue_date: factDate, account_id: 'account-test', account_name: '白屏回归账号',
  theater_id: 'theater-test', theater_name: '青柠剧场', source_video_id: 'video-test', source_drama_name: '白屏回归剧',
  video_views: 100, drama_views: 200, gross_revenue: '12.34', source_rank: 1,
  matched_drama_id: null, matched_drama_name: '', match_status: 'unmatched', updated_at: updatedAt,
};

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {}),
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, timezoneId: 'Asia/Shanghai' });
  const errors = [], writes = [], checks = [];
  let releaseDetails;
  let detailRequests = 0;
  let failDetails = false;
  const detailsGate = new Promise((resolve) => { releaseDetails = resolve; });
  let page;
  context.on('page', (opened) => opened.on('pageerror', (error) => errors.push(error.message)));
  await context.route('**/api/**', async (route) => {
    const request = route.request(), url = new URL(request.url());
    if (!['GET', 'HEAD'].includes(request.method())) {
      writes.push(`${request.method()} ${url.pathname}`);
      return route.abort();
    }
    const reply = (json) => route.fulfill({ json });
    if (url.pathname === '/api/v2/task-center') return reply({ tasks: [], executors: [], dramaPriorities: [], isQueuePaused: false });
    if (url.pathname === '/api/v2/task-center/orphan-records') return reply({ total: 0, items: [] });
    if (url.pathname === '/api/v2/settings') return reply({ publish_presets: ['12:00'], publish_date_offset_days: 0 });
    if (url.pathname === '/api/v2/revenue/source-data') return reply(source);
    if (url.pathname === '/api/v2/revenue/video-details') {
      detailRequests++;
      await detailsGate;
      if (failDetails) return route.fulfill({ status: 500, json: { error: '回归检查：收益明细读取失败' } });
      const start = url.searchParams.get('start_date'), end = url.searchParams.get('end_date');
      return reply({ items: start <= factDate && end >= factDate ? [video] : [], truncated: false, limit: 12000, start_date: start, end_date: end });
    }
    // All other API responses are empty fixtures, including resource scans.
    return reply({ items: [] });
  });
  const tab = (label) => page.locator('main').first().getByRole('button', { name: new RegExp(`^${label}(?:\\s|$)`) }).first();
  async function count(label, value) {
    await page.waitForFunction(({ label, value }) => [...document.querySelectorAll('main button')].some((button) => button.textContent.replace(/\s/g, '') === `${label}${value}`), { label, value });
    assert.equal((await tab(label).innerText()).replace(/\s/g, ''), `${label}${value}`);
  }
  async function healthy(label) {
    assert.deepEqual(errors, [], label);
    assert.ok(await page.locator('#root').evaluate((root) => root.childElementCount > 0), label);
    checks.push(label);
  }
  try {
    page = await context.newPage();
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    for (let index = 0; index < 3; index++) {
      await page.getByRole('button', { name: /执行.*等待.*完成/ }).first().click();
      await page.getByRole('heading', { name: /全局任务中心/ }).waitFor();
      await healthy(`task center open ${index + 1}`);
      await page.getByRole('button', { name: '全屏展开', exact: true }).click();
      await page.getByRole('button', { name: '还原窗口', exact: true }).click();
      await page.getByRole('button', { name: '关闭', exact: true }).last().click();
      await healthy(`task center close ${index + 1}`);
    }
    await page.locator('#nav-analytics').click();
    await count('剧集', '…');
    await tab('剧集').click();
    await page.getByRole('status').filter({ hasText: '正在读取当前筛选范围' }).waitFor();
    await healthy('click dramas while first data request is pending');
    await tab('账号').click();
    await count('剧集', '…');
    releaseDetails();
    await count('剧集', 1);
    await count('账号', 1);
    await healthy('first snapshot includes account and drama counts');
    for (let index = 0; index < 3; index++) {
      for (const label of ['收益', '剧集', '账号', '视频', '收益']) {
        await tab(label).click();
        await count('剧集', 1);
        await count('账号', 1);
        await healthy(`${label} keeps consistent counts, cycle ${index + 1}`);
      }
    }
    assert.equal(detailRequests, 1, 'tab changes must reuse the current snapshot');
    await page.screenshot({ path: path.join(output, 'revenue-counts.png'), fullPage: true });
    await tab('剧集').click();
    await page.getByRole('heading', { name: '白屏回归剧', exact: true }).waitFor();
    await page.getByPlaceholder('搜索剧集名称...').fill('没有这部剧');
    await page.getByRole('heading', { name: '当前筛选下暂无剧集收益数据' }).waitFor();
    await page.getByPlaceholder('搜索剧集名称...').fill('');
    await page.getByRole('heading', { name: '白屏回归剧', exact: true }).waitFor();
    await healthy('drama search empty and restored');
    await page.getByRole('button', { name: '昨日', exact: true }).click();
    await count('剧集', 0);
    await count('账号', 0);
    await page.getByRole('heading', { name: '当前筛选下暂无剧集收益数据' }).waitFor();
    for (const label of ['收益', '账号', '剧集', '视频', '剧集']) {
      await tab(label).click();
      await count('剧集', 0);
      await healthy(`confirmed empty period: ${label}`);
    }
    await page.screenshot({ path: path.join(output, 'dramas-empty.png'), fullPage: true });
    await page.getByRole('button', { name: '近7日', exact: true }).click();
    await count('剧集', 1);
    await page.getByRole('heading', { name: '白屏回归剧', exact: true }).waitFor();
    await healthy('empty period returns to populated period');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#nav-analytics').click();
    await count('剧集', 1);
    await tab('视频').click();
    await page.locator('#video-analytics-page').waitFor();
    await healthy('persistent cache reload and video navigation');
    // Simulate first-load failure in a fresh context with no previous cache.
    await page.evaluate(() => localStorage.clear());
    await page.close();
    failDetails = true;
    page = await context.newPage();
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.locator('#nav-analytics').click();
    await tab('剧集').click();
    await page.getByRole('status').filter({ hasText: '收益明细读取失败' }).waitFor();
    await count('剧集', '…');
    await healthy('failed initial request stays usable and does not claim zero');
    assert.deepEqual(writes, [], 'no business mutation is allowed');
    console.log(JSON.stringify({ passed: checks.length, errors, writes, detailRequests, output }));
  } catch (error) {
    if (page && !page.isClosed()) await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
    throw error;
  } finally {
    releaseDetails();
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ checks, errors, writes, detailRequests }, null, 2));
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
