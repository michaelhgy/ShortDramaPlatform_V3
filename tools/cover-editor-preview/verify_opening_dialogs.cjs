const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const info=JSON.parse(fs.readFileSync('local-test-output/cover-integration-20261026/current.json','utf8'));
const out=path.resolve('local-test-output/cover-opening-20261026'),before=fs.readFileSync(path.join(out,'before-cover-editor.html'),'utf8');
const endpoint=info.url+'/api/v2/cover-editor/dramas/'+info.second_drama_id,url=info.url+'/cover-editor.html?dramaId='+info.second_drama_id;
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),checks=[],errors=[],nativeDialogs=[];
 const setup=await browser.newContext({viewport:{width:1200,height:1000}}),prepared=await setup.newPage();
 const json=async(u,body)=>{const r=await setup.request[body===undefined?'get':'post'](u,body===undefined?{}:{data:body});assert.ok(r.ok(),await r.text());return r.json();};
 const ready=page=>page.waitForFunction(()=>window.coverPreview?.ready);
 const snap=()=>json(endpoint);
 let context,page;
 try{
  await json(info.url+'/api/v2/dramas/'+info.second_drama_id+'/cover',{filename:'cover.jpeg',content_base64:fs.readFileSync('D:/短剧推广运营系统/剧集资料/一口铁锅走天下/封面/一口铁锅走天下-封面.jpeg').toString('base64')});
  await prepared.goto(url);await ready(prepared);
  const library=await json(info.url+'/api/v2/cover-editor/flowers?compact=1');
  const textured=library.styles.find(s=>s.id==='7328988266768764194')||library.styles.find(s=>JSON.stringify(s.style).includes('/textures/'));
  assert.ok(textured);await prepared.locator('#flower-query').fill(textured.id);await prepared.locator('.style-card').click();
  await prepared.waitForFunction(id=>window.coverPreview.getLayers()[0]?.styleId===id,textured.id);await prepared.locator('#save-use').click();await prepared.locator('#save-use:not(:disabled)').waitFor();await prepared.close();
  const snapshot=await snap(),metrics=[];
  for(const mode of ['before','after']){
   context=await browser.newContext({viewport:{width:1200,height:1000},acceptDownloads:true});page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{nativeDialogs.push(d.type());await d.dismiss();});
   await page.addInitScript(()=>{window.closedCoverMessages=0;window.addEventListener('message',e=>{if(e.data?.type==='v3-cover-close-allowed')window.closedCoverMessages++;});});
   if(mode==='before')await page.route('**/cover-editor-before.html?*',route=>route.fulfill({contentType:'text/html',body:before}));
   for(let run=0;run<3;run++){
    const requests=[],bodies=[];const listen=r=>{if(r.url().includes('/flowers'))requests.push(r.url());};
    const response=r=>{if(new URL(r.url()).pathname==='/api/v2/cover-editor/flowers')bodies.push(Number(r.headers()['content-length']));};
    page.on('request',listen);page.on('response',response);
    const start=Date.now();await page.goto(mode==='before'?url.replace('cover-editor.html','cover-editor-before.html'):url);await ready(page);
    const milliseconds=Date.now()-start,png=await page.locator('#cover').evaluate(c=>c.toDataURL());
    const bodyBytes=(await Promise.all(bodies)).reduce((a,b)=>a+b,0);
    const textureWireBytes=await page.evaluate(()=>performance.getEntriesByType('resource').filter(r=>r.name.includes('/textures/')).reduce((sum,r)=>sum+r.transferSize,0));
    metrics.push({mode,run,milliseconds,bodyBytes,textureRequests:requests.filter(u=>u.includes('/textures/')).length,textureWireBytes,png});page.off('request',listen);page.off('response',response);
   }
   if(mode==='before'){await context.close();context=null;}
  }
  assert.ok(metrics.filter(m=>m.mode==='after').every(m=>m.bodyBytes<2_000_000));
  assert.ok(metrics.filter(m=>m.mode==='after').every(m=>m.textureRequests<10));checks.push('compact-library-and-only-active-textures');
  assert.ok(metrics.filter(m=>m.mode==='after'&&m.run>0).every(m=>m.textureWireBytes===0));checks.push('reopened-textures-reuse-browser-cache');
  assert.ok(metrics.every(m=>m.png===metrics[0].png));checks.push('existing-cover-pixels-unchanged');
  const reopened=await snap();assert.equal(reopened.revision,snapshot.revision);assert.equal(reopened.project.drama.versions.length,1);checks.push('reopening-does-not-create-save-or-copy');
  const full=metrics.find(m=>m.mode==='before').bodyBytes,compact=metrics.find(m=>m.mode==='after').bodyBytes;assert.ok(compact<full*.1);checks.push('library-response-reduced-over-90-percent');
  // Hold the library response so incomplete UI exposure can be checked deterministically.
  let release,blocked;const gate=new Promise(resolve=>release=resolve),pending=new Promise(resolve=>blocked=resolve);
  await page.route('**/flowers?compact=1',async route=>{blocked();await gate;await route.continue();});
  const navigating=page.goto(url);await pending;assert.equal(await page.locator('#editor-workspace').isVisible(),false);assert.equal(await page.locator('#startup').isVisible(),true);
  await page.screenshot({path:path.join(out,'加载中不显示空白编辑器.png'),fullPage:true});release();await navigating;await ready(page);await page.unroute('**/flowers?compact=1');checks.push('incomplete-editor-hidden-until-ready');
  await page.screenshot({path:path.join(out,'完整封面编辑界面.png'),fullPage:true});
  // All confirmations below are handled through application UI; native dialogs are rejected.
  const countBefore=(await snap()).project.drama.versions.length;
  await page.locator('#delete-version').click();await page.locator('#confirm-modal').waitFor();assert.equal(await page.evaluate(()=>document.activeElement.id),'confirm-cancel');
  await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'confirm-close');await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'confirm-accept');checks.push('confirmation-focus-and-tab-trap');
  await page.screenshot({path:path.join(out,'软件风格删除确认.png'),fullPage:true});
  await page.keyboard.press('Escape');assert.equal(await page.locator('#confirm-modal').isVisible(),false);assert.equal((await snap()).project.drama.versions.length,countBefore);assert.equal(await page.evaluate(()=>window.closedCoverMessages),0);checks.push('escape-cancels-top-confirmation-without-closing-editor');
  await page.locator('#copy').fill('未保存的编辑');await page.keyboard.press('Escape');await page.locator('#confirm-modal').waitFor();assert.equal(await page.locator('#confirm-title').textContent(),'放弃未保存的修改');
  await page.keyboard.press('Escape');assert.equal(await page.locator('#copy').inputValue(),'未保存的编辑');assert.equal(await page.evaluate(()=>window.closedCoverMessages),0);checks.push('dirty-escape-keeps-unsaved-edits-on-cancel');
  await page.locator('#save-use').click();await page.locator('#save-use:not(:disabled)').waitFor();
  await page.locator('#template-name').fill('弹窗检查模板');await page.locator('#save-template').click();await page.waitForFunction(()=>window.coverPreview.getTemplates().length===1);
  await page.locator('#apply-template').click();await page.locator('#confirm-modal').waitFor();assert.equal(await page.locator('#confirm-title').textContent(),'套用通用模板');await page.locator('#confirm-close').click();checks.push('apply-template-uses-styled-confirmation');
  await page.locator('#delete-template').click();await page.locator('#confirm-modal').waitFor();await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>window.coverPreview.getTemplates().length),1);
  await page.locator('#delete-template').click();await page.locator('#confirm-accept').click();await page.waitForFunction(()=>window.coverPreview.getTemplates().length===0);checks.push('template-delete-confirm-and-cancel');
  await page.locator('#tab-sheep').click();await page.waitForFunction(()=>window.coverPreview.getProject().sheep.versions.length===1);await page.locator('#save-use:not(:disabled)').waitFor();
  await page.locator('[data-version="original"]').click();await page.locator('#copy-original').waitFor();await page.locator('#copy-original').click();await page.locator('#confirm-modal').waitFor();assert.equal(await page.locator('#confirm-title').textContent(),'复制剧集原图');await page.keyboard.press('Escape');checks.push('copy-original-uses-styled-confirmation');
  await page.locator('#versions [data-version]:not([data-version="original"])').click();await page.locator('#manage-flowers').click();await page.locator('#flower-manager').waitFor();
  await page.keyboard.press('Escape');assert.equal(await page.locator('#flower-manager').isVisible(),false);assert.equal(await page.evaluate(()=>window.closedCoverMessages),0);checks.push('escape-closes-flower-manager-only-even-while-scanning');
  await page.keyboard.press('Escape');await page.waitForFunction(()=>window.closedCoverMessages===1);checks.push('escape-closes-clean-editor');
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();
  await page.getByTestId('task-drama-cover').first().click({button:'right'});
  const modal=page.getByRole('dialog',{name:'封面编辑',exact:true});await modal.waitFor();
  await page.frameLocator('iframe[title="封面文字编辑器"]').locator('#editor-workspace').waitFor();
  await page.getByRole('button',{name:'关闭封面编辑',exact:true}).focus();await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});checks.push('escape-closes-real-modal-with-focus-outside-iframe');
  assert.deepEqual(nativeDialogs,[]);assert.deepEqual(errors,[]);
  const median=mode=>metrics.filter(m=>m.mode===mode).map(m=>m.milliseconds).sort((a,b)=>a-b)[1];
  const report={checks,styles:library.styles.length,metrics:metrics.map(({png,...m})=>m),beforeMedianMs:median('before'),afterMedianMs:median('after'),fullLibraryBytes:full,compactLibraryBytes:compact,nativeDialogs,errors,realBusinessWrites:0};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,metrics:undefined,checks:checks.length}));
 }finally{if(context)await context.close();await setup.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
