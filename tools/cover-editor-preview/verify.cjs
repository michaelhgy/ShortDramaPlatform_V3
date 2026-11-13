/** Isolated static-file browser checks; no application API or database is opened. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out = path.resolve(process.argv[2] || 'local-test-output/cover-editor-preview-20261026');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1150 }, acceptDownloads: true });
  const page = await context.newPage(), errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (/^https?:/.test(r.url())) requests.push(r.url()); });
  page.on('dialog', d => d.accept());
  await require('./test_helpers.cjs').acceptConfirmations(page);
  try {
    await page.goto(pathToFileURL(path.join(out, 'index.html')).href);
    await page.waitForFunction(() => window.coverPreview?.ready === true);
    assert.equal(await page.locator('.style-card').count(), 12);
    await page.screenshot({ path: path.join(out, '编辑器预览.png'), fullPage: true });
    const evidence = await page.evaluate(async () => {
      const { styles, renderText, renderCover, getSource, getLayers } = window.coverPreview;
      const rows = [], digests = [];
      for (const style of styles) {
        const layer = { ...getLayers()[0], text: '她一出手', x: 15, y: 15, width: 600, fontSize: 110, rotation: 0 };
        const { canvas } = renderText(layer, style), data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
        let nonzero = 0, minX = canvas.width, minY = canvas.height, maxX = 0, maxY = 0;
        for (let i = 3; i < data.length; i += 4) if (data[i] > 5) { nonzero++; const p = (i - 3) / 4, x = p % canvas.width, y = Math.floor(p / canvas.width); minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
        const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(v => v.toString(16).padStart(2, '0')).join(''); digests.push(digest);
        rows.push({ id: style.id, name: style.name, nonzero, width: canvas.width, height: canvas.height, minX, minY, maxX, maxY, digest });
      }
      const sheet = document.createElement('canvas'); sheet.width = 1440; sheet.height = 1700; const ctx = sheet.getContext('2d');
      ctx.fillStyle = '#eef1f5'; ctx.fillRect(0, 0, sheet.width, sheet.height); ctx.fillStyle = '#202638'; ctx.font = 'bold 30px "Microsoft YaHei"'; ctx.fillText('剪映简单花字 · V3 实际绘制', 30, 50);
      ctx.fillStyle = '#7d8796'; ctx.font = '15px "Microsoft YaHei"'; ctx.fillText('小图为剪映资源自带预览；大字为 V3 使用同款参数绘制。尚未逐像素对照。', 30, 83);
      for (let i = 0; i < styles.length; i++) {
        const style = styles[i], x = 24 + i % 3 * 474, y = 110 + Math.floor(i / 3) * 314;
        ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.roundRect(x, y, 450, 294, 14); ctx.fill();
        ctx.fillStyle = '#5b6374'; ctx.font = '16px "Microsoft YaHei"'; ctx.fillText(style.name, x + 18, y + 29);
        const icon = new Image(); icon.src = style.icon; await icon.decode(); const scale = Math.min(160 / icon.width, 57 / icon.height); ctx.drawImage(icon, x + 18, y + 44, icon.width * scale, icon.height * scale);
        ctx.fillStyle = '#242d42'; ctx.beginPath(); ctx.roundRect(x + 12, y + 112, 426, 169, 8); ctx.fill();
        const { canvas: text } = renderText({ ...getLayers()[0], text: '她一出手\n全场都服了', width: 530, fontSize: 78, rotation: 0 }, style);
        const sc = Math.min(400 / text.width, 155 / text.height); ctx.drawImage(text, x + 225 - text.width * sc / 2, y + 195 - text.height * sc / 2, text.width * sc, text.height * sc);
      }
      const coverSamples = [];
      for (const name of ['复古淡黄花字', '描边字', '白字红光花字', '紫色立体渐变']) {
        const s = styles.find(s => s.name === name); const l = { ...getLayers()[0], styleId: s.id };
        coverSamples.push({ name, image: renderCover(getSource(), [l], styles).toDataURL('image/png') });
      }
      return { rows, distinct: new Set(digests).size, sheet: sheet.toDataURL('image/png'), coverSamples };
    });
    assert.equal(evidence.distinct, 15);
    for (const row of evidence.rows) { assert.ok(row.nonzero > 500, row.name); assert.ok(row.minX > 0 && row.minY > 0 && row.maxX < row.width - 1 && row.maxY < row.height - 1, '文字效果被裁切：' + row.name); }
    fs.writeFileSync(path.join(out, '15款花字实际效果.png'), Buffer.from(evidence.sheet.split(',')[1], 'base64'));
    for (const sample of evidence.coverSamples) fs.writeFileSync(path.join(out, `封面-${sample.name}.png`), Buffer.from(sample.image.split(',')[1], 'base64'));
    // Edit, move and resize actual on-screen text.
    await page.locator('#copy').fill('她一出手\n全场都服了');
    const before = await page.evaluate(() => window.coverPreview.getLayers()[0]);
    const box = await page.locator('#selection').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); await page.mouse.move(box.x + box.width / 2 + 20, box.y + box.height / 2 - 10, { steps: 4 }); await page.mouse.up();
    const after = await page.evaluate(() => window.coverPreview.getLayers()[0]); assert.ok(after.x > before.x); assert.ok(after.y < before.y);
    for (const direction of ['n', 's', 'w', 'e', 'nw', 'ne', 'se', 'sw']) {
      const handle = await page.locator(`[data-handle="${direction}"]`).boundingBox();
      const start = await page.evaluate(() => window.coverPreview.getLayers()[0]);
      const dx = direction.includes('w') ? -3 : direction.includes('e') ? 3 : 0, dy = direction.includes('n') ? -3 : direction.includes('s') ? 3 : 0;
      await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2); await page.mouse.down(); await page.mouse.move(handle.x + handle.width / 2 + dx, handle.y + handle.height / 2 + dy, { steps: 3 }); await page.mouse.up();
      const resized = await page.evaluate(() => window.coverPreview.getLayers()[0]);
      if (dx) assert.ok(resized.width > start.width, direction);
      if (dy) assert.ok(resized.height > start.height, direction);
      assert.equal(resized.fontSize, start.fontSize);
    }
    await page.locator('#toggle-selection').click(); assert.equal(await page.locator('#selection').isVisible(), false);
    await page.screenshot({ path: path.join(out, '无选框预览.png'), fullPage: true });
    await page.locator('footer').screenshot({ path: path.join(out, '保存操作.png') });
    await page.locator('#toggle-selection').click(); assert.equal(await page.locator('#selection').isVisible(), true);
    const cleanPixels = await page.evaluate(() => {
      const api = window.coverPreview, base = { ...api.getLayers()[0], text: '上下居中', width: 600, height: 300, fontSize: 80, verticalAlign: 'middle' };
      const plain = { id: 'plain', name: 'plain', icon: '', style: { fill: { alpha: 1, content: { render_type: 'solid', solid: { color: [1, 1, 1], alpha: 1 } } }, strokes: [], shadows: [], inner_shadows: [] } };
      const { canvas, padding } = api.renderText(base, plain), data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let minY = canvas.height, maxY = 0;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 20) { const y = Math.floor((i - 3) / 4 / canvas.width); minY = Math.min(minY, y); maxY = Math.max(maxY, y); }
      return Math.abs((minY + maxY + 1) / 2 - padding - 150);
    });
    assert.ok(cleanPixels <= 1.5, '文字没有按实际字形上下居中');
    assert.deepEqual(await page.locator('footer>div:last-child button').allTextContents(), ['导出封面', '另存新版', '保存使用']);
    // Export equals the visible canvas pixels; selection handles are DOM overlays.
    const expectedExport = await page.locator('#cover').evaluate(c => c.toDataURL('image/png'));
    const coverDownload = page.waitForEvent('download'); await page.locator('#export').click(); const downloadedCover = await coverDownload;
    await downloadedCover.saveAs(path.join(out, '预览一致性导出.png'));
    assert.deepEqual(fs.readFileSync(path.join(out, '预览一致性导出.png')), Buffer.from(expectedExport.split(',')[1], 'base64'));
    // Three saved versions per set, fourth rejected, with independent active selection.
    for (let i = 0; i < 3; i++) { await page.locator('#copy').fill(`剧集修改版 ${i}`); await page.locator(i === 0 ? '#save-use' : '#save').click(); await page.waitForFunction(n => window.coverPreview.getProject().drama.versions.length === n, i + 1); }
    const selected = await page.evaluate(() => window.coverPreview.getProject().drama.activeId);
    const lastSaved = await page.evaluate(() => window.coverPreview.getProject().drama.versions.at(-1).id);
    await page.locator('#copy').fill('保存使用只更新当前版本'); await page.locator('#save-use').click();
    await page.waitForFunction(id => window.coverPreview.getProject().drama.activeId === id, lastSaved);
    assert.equal(await page.evaluate(() => window.coverPreview.getProject().drama.versions.length), 3);
    const activeAfterUpdate = await page.evaluate(() => window.coverPreview.getProject().drama.activeId);
    await page.locator('#save').click(); await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => window.coverPreview.getProject().drama.versions.length), 3);
    await page.locator('#tab-sheep').click(); await page.locator('#add-text').click();
    for (let i = 0; i < 3; i++) { await page.locator('#copy').fill(`羊头修改版 ${i}`); await page.locator(i === 0 ? '#save-use' : '#save').click(); await page.waitForFunction(n => window.coverPreview.getProject().sheep.versions.length === n, i + 1); }
    await page.locator('#save-use').click(); await page.waitForFunction(() => window.coverPreview.getProject().sheep.activeId === window.coverPreview.getProject().sheep.versions.at(-1).id);
    assert.equal(await page.evaluate(() => window.coverPreview.getProject().drama.activeId), activeAfterUpdate);
    // Deleting in-use falls back to this set's original.
    await page.locator('#delete-version').click(); await page.waitForFunction(() => window.coverPreview.getProject().sheep.activeId === 'original');
    // Original view exposes source management only; removed export has no DOM entry.
    assert.equal(await page.locator('#text-editor').isVisible(),false);
    assert.equal(await page.locator('#export-text').count(),0);
    // Save state survives reload without writing to a real application API.
    await page.locator('#save').click(); await page.waitForFunction(() => window.coverPreview.getProject().sheep.versions.length === 3);
    for (let i = 0; i < 5; i++) { await page.locator('#template-name').fill(`跨剧模板 ${i}`); await page.locator('#save-template').click(); await page.waitForFunction(n => window.coverPreview.getTemplates().length === n, i + 1); }
    await page.locator('#save-template').click(); await page.waitForTimeout(100); assert.equal(await page.evaluate(() => window.coverPreview.getTemplates().length), 5);
    assert.equal(await page.evaluate(() => window.coverPreview.getTemplates().some(t => 'image' in t || 'sourceImage' in t)), false);
    const templateId = await page.evaluate(() => window.coverPreview.getTemplates()[0].id);
    await page.locator('#template-select').selectOption(templateId); await page.locator('#apply-template').click();
    const appliedText = await page.evaluate(() => window.coverPreview.getLayers()[0].text);
    assert.equal(appliedText, await page.evaluate(() => window.coverPreview.getTemplates()[0].layers[0].text));
    await page.locator('#delete-template').click(); await page.waitForFunction(() => window.coverPreview.getTemplates().length === 4);
    // Applying to another source with a different aspect ratio keeps its own background.
    await page.locator('#delete-version').click();
    await page.waitForFunction(()=>window.coverPreview.getProject().sheep.versions.length===2);
    const fixture = await page.evaluate(() => { const c = document.createElement('canvas'); c.width = 1080; c.height = 1920; const x = c.getContext('2d'); x.fillStyle = '#284158'; x.fillRect(0, 0, c.width, c.height); return c.toDataURL('image/png'); });
    await page.locator('#file').setInputFiles({ name: 'different-drama-fixture.png', mimeType: 'image/png', buffer: Buffer.from(fixture.split(',')[1], 'base64') });
    await page.waitForFunction(() => window.coverPreview.getSource()?.naturalHeight === 1920);
    await page.locator('#save').click();await page.waitForFunction(()=>window.coverPreview.getProject().sheep.versions.length===3&&document.querySelector('#text-editor').hidden===false);
    const otherTemplate = await page.evaluate(() => window.coverPreview.getTemplates()[0]);
    await page.locator('#template-select').selectOption(otherTemplate.id); await page.locator('#apply-template').click();
    const adapted = await page.evaluate(() => ({ layer: window.coverPreview.getLayers()[0], background: window.coverPreview.getProject().sheep.original, templates: window.coverPreview.getTemplates() }));
    assert.ok(Math.abs(adapted.layer.x - otherTemplate.layers[0].x * 1080 / otherTemplate.width) < .001);
    assert.ok(Math.abs(adapted.layer.y - otherTemplate.layers[0].y * 1920 / otherTemplate.height) < .001);
    assert.equal(adapted.background, fixture);
    await page.locator('#toggle-selection').click();
    await page.screenshot({ path: path.join(out, '跨封面模板套用.png'), fullPage: true });
    await page.waitForTimeout(200); await page.reload(); await page.waitForFunction(() => window.coverPreview?.ready);
    assert.equal(await page.evaluate(() => window.coverPreview.getProject().drama.versions.length), 3);
    assert.equal(await page.evaluate(() => window.coverPreview.getProject().sheep.versions.length), 3);
    assert.equal(await page.evaluate(() => window.coverPreview.getTemplates().length), 4);
    await page.setViewportSize({ width: 720, height: 1050 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(out, '窄窗口预览.png'), fullPage: true });
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    const result = { styles: evidence.rows, distinct: evidence.distinct, ui: ['text_edit', 'drag', 'eight_way_resize', 'hide_show_selection', 'glyph_vertical_center', 'three_action_footer', 'export_matches_preview', 'three_versions_each', 'save_use_updates_existing', 'fourth_rejected', 'independent_active', 'delete_fallback', 'original_controls_and_removed_text_export', 'five_templates_limit', 'template_apply_delete', 'template_without_cover', 'template_adapts_different_source', 'reload_persistence', 'narrow_no_horizontal_overflow'], browserErrors: errors, networkRequests: requests, businessWrites: 0 };
    fs.writeFileSync(path.join(out, '验证结果.json'), JSON.stringify(result, null, 2)); console.log(JSON.stringify({ styles: 15, uiChecks: result.ui.length, browserErrors: errors, businessWrites: 0, output: out }));
  } finally { await context.close(); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
