const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const info=JSON.parse(fs.readFileSync('local-test-output/cover-integration-20261026/current.json','utf8'));
const out=path.resolve('local-test-output/cover-version-entry-20261026');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1200,height:1000},acceptDownloads:true}),page=await context.newPage();
 const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await require('./test_helpers.cjs').acceptConfirmations(page);
 const api=async(url,body)=>{const r=await context.request[body===undefined?'get':'post'](info.url+url,body===undefined?{}:{data:body});assert.ok(r.ok(),await r.text());return r.json();};
 const endpoint='/api/v2/cover-editor/dramas/'+info.drama_id;
 const snap=()=>api(endpoint),url=info.url+'/cover-editor.html?dramaId='+info.drama_id;
 const ready=()=>page.waitForFunction(()=>window.coverPreview?.ready);
 const saveReady=()=>page.locator('#save-use:not(:disabled)').waitFor();
 try{
  await page.goto(url);await ready();assert.equal(await page.locator('#upload').isVisible(),true);assert.equal(await page.locator('#text-editor').isVisible(),false);assert.equal(await page.locator('#export').isVisible(),false);checks.push('no-source-only-useful-actions');
  const fixture='D:/短剧推广运营系统/剧集资料/一口铁锅走天下/封面/一口铁锅走天下-封面.jpeg';
  await page.locator('#file').setInputFiles(fixture);await page.waitForFunction(()=>window.coverPreview.getProject().drama.versions.length===1&&document.querySelector('#copy').value==='主页看全集');await saveReady();
  let data=await snap();const original=data.project.drama.original,versionId=data.project.drama.versions[0].id;
  assert.equal(data.project.drama.activeId,'original');assert.equal(data.project.drama.versions[0].layers[0].text,'主页看全集');assert.equal(data.project.sheep.versions.length,0);checks.push('upload-auto-creates-and-opens-modification-one-with-default-text');
  assert.equal(await page.locator('#upload').isVisible(),false);assert.equal(await page.locator('#copy-original').isVisible(),false);assert.equal(await page.locator('#export-text').count(),0);checks.push('modified-view-hides-source-buttons-and-removes-transparent-export');
  await page.screenshot({path:path.join(out,'自动生成修改版1.png'),fullPage:true});
  await page.reload();await ready();data=await snap();assert.equal(data.project.drama.versions.length,1);assert.equal(await page.locator('.version.selected').getAttribute('data-version'),versionId);checks.push('reopen-reuses-existing-edit-without-duplicates');
  await page.locator('[data-version="original"]').click();await page.waitForFunction(()=>document.querySelector('#editing-label').textContent.includes('原图'));
  for(const id of ['text-editor','flower-section','template-actions','preview-hint','center-x','center-y','delete-version','save-use'])assert.equal(await page.locator('#'+id).isVisible(),false,id);
  assert.equal(await page.locator('#upload').isVisible(),true);assert.equal(await page.locator('#copy-original').isVisible(),false);assert.equal((await page.evaluate(()=>window.coverPreview.getLayers())).length,0);checks.push('original-is-readonly-with-useful-actions-only');
  await page.screenshot({path:path.join(out,'原始封面精简操作.png'),fullPage:true});
  const download=page.waitForEvent('download');await page.locator('#export').click();await(await download).saveAs(path.join(out,'原始封面导出.png'));assert.equal((await snap()).project.drama.versions.length,1);checks.push('original-export-does-not-create-another-version');
  await page.locator(`[data-version="${versionId}"]`).click();await page.locator('#copy').fill('保留已有编辑');await page.locator('#save-use').click();await saveReady();data=await snap();assert.equal(data.project.drama.versions.length,1);assert.equal(data.project.drama.activeId,versionId);assert.equal(data.project.drama.original,original);checks.push('save-use-updates-one-version-and-preserves-source');
  await page.locator('[data-version="original"]').click();await page.waitForFunction(()=>document.querySelector('#save-use').textContent==='设为使用');assert.equal(await page.locator('#save-use').textContent(),'设为使用');await page.locator('#save-use').click();await page.waitForFunction(()=>window.coverPreview.getProject().drama.activeId==='original');checks.push('original-can-be-selected-as-active-again');
  await page.locator('#upload:not(:disabled)').waitFor();await page.locator(`#versions [data-version="${versionId}"]`).click();await page.locator('#add-text').click();assert.equal(await page.locator('#copy').inputValue(),'主页看全集');await page.locator('#save-use').click();await saveReady();checks.push('new-text-also-uses-new-default');
  await page.reload();await ready();assert.equal(await page.locator('#copy').inputValue(),'保留已有编辑');assert.equal((await snap()).project.drama.versions.length,1);checks.push('existing-edits-are-not-overwritten-by-default');
  await page.locator('#tab-sheep').click();await page.waitForFunction(()=>window.coverPreview.getProject().sheep.versions.length===1);await saveReady();data=await snap();assert.equal(data.project.sheep.activeId,'original');assert.equal(await page.locator('#copy').inputValue(),'主页看全集');
  await page.locator('[data-version="original"]').click();await page.locator('#copy-original').waitFor();assert.equal(await page.locator('#upload').isVisible(),true);checks.push('sheep-independent-auto-version-and-original-copy-control');
  await page.locator('#versions [data-version]:not([data-version="original"])').click();await page.locator('#delete-version').click();await page.waitForFunction(()=>window.coverPreview.getProject().sheep.versions.length===0);assert.equal((await snap()).project.sheep.versions.length,0);checks.push('delete-does-not-immediately-recreate-version');
  await page.reload();await ready();assert.equal((await snap()).project.sheep.versions.length,0);checks.push('opening-drama-does-not-create-sheep-edits');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({checks,errors,realBusinessWrites:0},null,2));console.log(JSON.stringify({checks:checks.length,errors,realBusinessWrites:0}));
 }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
