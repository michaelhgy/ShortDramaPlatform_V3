const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve('local-test-output/flower-library-20261026'),info=JSON.parse(fs.readFileSync('local-test-output/cover-integration-20261026/current.json','utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1200,height:1000},acceptDownloads:true});
 const page=await context.newPage(),errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const api=async(action='',body)=>{const r=await context.request[body===undefined?'get':'post'](info.url+'/api/v2/cover-editor/flowers'+action,body===undefined?{}:{data:body});const v=await r.json();assert.ok(r.ok(),JSON.stringify(v));return v;};
 const row=async(id)=>(await api()).styles.find(s=>s.id===id);
 try{
  await context.request.post(info.url+'/api/v2/dramas/'+info.drama_id+'/cover',{data:{filename:'cover.jpeg',content_base64:fs.readFileSync('D:/短剧推广运营系统/剧集资料/一口铁锅走天下/封面/一口铁锅走天下-封面.jpeg').toString('base64')}});
  await page.goto(info.url+'/cover-editor.html?dramaId='+info.drama_id);await page.waitForFunction(()=>window.coverPreview?.ready);
  assert.equal(await page.locator('.style-card').count(),12);
  await page.locator('#manage-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor();
  const scan=await api('/scan',{remember:false}),chosen=scan.items.find(s=>s.status==='ready'&&!s.imported);
  assert.ok(chosen);assert.ok(scan.items.some(s=>s.status!=='ready'));checks.push('actual-cache-autodiscovery-and-statuses');
  await page.screenshot({path:path.join(out,'剪映缓存管理.png'),fullPage:true});
  const unsupported=scan.items.find(s=>s.status!=='ready');await page.locator('#cache-query').fill(unsupported.id);
  assert.equal(await page.locator('#cache-results input[type=checkbox]').isDisabled(),true);checks.push('unsupported-cannot-import');
  await page.locator('#cache-query').fill(chosen.id);await page.locator('#cache-results input[type=checkbox]').check();await page.locator('#import-flowers').click();
  await page.waitForFunction(async(id)=>(await(await fetch('/api/v2/cover-editor/flowers')).json()).styles.some(s=>s.id===id),chosen.id);
  await page.locator('#scan-flowers:not(:disabled)').waitFor();assert.equal((await api()).styles.length,16);assert.equal(await page.locator('#cache-results input[type=checkbox]').isDisabled(),true);checks.push('selective-import-no-duplicates');
  await page.locator('#close-flowers').click();await page.locator('#flower-query').fill(chosen.id);
  await page.locator('.flower-star').click();await page.waitForFunction(async(id)=>(await(await fetch('/api/v2/cover-editor/flowers')).json()).styles.find(s=>s.id===id).favorite,chosen.id);
  await page.locator('.flower-star.starred').waitFor();
  await page.locator('#flower-filter').selectOption('favorite');assert.equal(await page.locator('.style-card').count(),1);checks.push('favorite-and-filter');
  await page.locator('.style-card').click();assert.equal((await row(chosen.id)).usageCount,0);checks.push('preview-does-not-count');
  await page.locator('#copy').fill('新增花字真实效果');await page.locator('#save-use').click();await page.locator('#save-use:not(:disabled)').waitFor();
  assert.equal((await row(chosen.id)).usageCount,1);checks.push('successful-cover-save-counts-once');
  const downloading=page.waitForEvent('download');await page.locator('#export').click();await(await downloading).saveAs(path.join(out,'新导入花字封面.png'));
  await page.waitForFunction(async(id)=>(await(await fetch('/api/v2/cover-editor/flowers')).json()).styles.find(s=>s.id===id).usageCount===2,chosen.id);checks.push('export-counts-once');
  await page.locator('#flower-filter').selectOption('recent');assert.equal(await page.locator('.style-card').count(),1);
  await page.locator('#flower-filter').selectOption('frequent');await page.locator('#flower-query').fill('');assert.equal(await page.locator('.style-card').first().getAttribute('data-id'),chosen.id);checks.push('recent-and-most-used');
  await page.reload();await page.waitForFunction(()=>window.coverPreview?.ready&&document.querySelector('#copy')?.value==='新增花字真实效果');
  assert.equal((await row(chosen.id)).usageCount,2);assert.equal((await row(chosen.id)).favorite,true);checks.push('library-preferences-and-edit-reopen');
  await page.locator('#manage-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor();await page.locator('#flower-library-tab').click();await page.locator('#cache-query').fill(chosen.id);await page.locator('#cache-results button').click();
  await page.waitForFunction(async(id)=>(await(await fetch('/api/v2/cover-editor/flowers')).json()).styles.find(s=>s.id===id).enabled===false,chosen.id);await page.locator('#close-flowers').click();
  await page.reload();await page.waitForFunction(()=>window.coverPreview?.ready&&document.querySelector('#copy')?.value==='新增花字真实效果');assert.equal(await page.locator(`.style-card[data-id="${chosen.id}"]`).count(),0);
  assert.ok(await page.locator('#cover').evaluate(c=>c.width>0));checks.push('remove-from-list-preserves-existing-edits');
  await page.screenshot({path:path.join(out,'花字收藏和使用记录.png'),fullPage:true});
  // Every current compatible cache style is rendered as a real image using the same renderer.
  const compatible=scan.items.filter(s=>s.status==='ready');await api('/import',{ids:compatible.map(s=>s.id)});await page.reload();await page.waitForFunction(()=>window.coverPreview?.ready);
  const rendered=await page.evaluate(async()=>{const p=window.coverPreview;await p.prepareFlowerStyles(p.getStyles());return p.getStyles().map(s=>{const output=p.renderText({...p.getLayers()[0],text:'花字效果',width:600,height:150,fontSize:80},s),data=output.canvas.getContext('2d').getImageData(0,0,output.canvas.width,output.canvas.height).data;let pixels=0;for(let i=3;i<data.length;i+=4)if(data[i]>5)pixels++;return {id:s.id,name:s.name,width:output.canvas.width,height:output.canvas.height,pixels};});});
  assert.ok(rendered.every(s=>s.width>0&&s.height>0&&s.pixels>100));checks.push('all-compatible-cache-styles-render');
  await page.locator('#manage-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor();
  // Custom folder UI saves only the fixture machine configuration, not user settings.
  await page.locator('#cache-directory').fill(scan.roots[0]);await page.locator('#scan-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor();checks.push('custom-cache-path-scan');
  await page.setViewportSize({width:720,height:950});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:path.join(out,'窄窗口花字管理.png'),fullPage:true});checks.push('narrow-window-no-overflow');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({checks,errors,cached:scan.items.length,compatible:compatible.length,rendered,realBusinessWrites:0},null,2));console.log(JSON.stringify({checks:checks.length,errors,cached:scan.items.length,compatible:compatible.length,rendered:rendered.length}));
 }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
