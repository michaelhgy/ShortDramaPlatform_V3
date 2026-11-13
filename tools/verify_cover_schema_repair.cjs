/** Read-only acceptance on the already-running local service. No form is saved. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve('local-test-output/cover-schema-repair-20261026');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1600,height:1050}}),page=await context.newPage(),errors=[],blocked=[];
 page.on('pageerror',e=>errors.push(e.message));
 await context.route('**/*',route=>{const r=route.request(),u=new URL(r.url());
  if(u.protocol==='http:'&&u.hostname!=='127.0.0.1')return route.abort();
  if(r.method()!=='GET'){blocked.push(u.pathname);return route.fulfill({status:403,json:{error:'只读现场验收，不保存任何业务内容'}});}return route.continue();});
 try{
  await page.goto('http://127.0.0.1:8782');await page.getByRole('button',{name:'生产中心',exact:true}).click();
  await page.getByTestId('task-cover-pair').waitFor();
  await page.getByText('《一口铁锅走天下》',{exact:true}).filter({visible:true}).first().click();
  const cover=page.getByTestId('task-drama-cover');await cover.locator('img').waitFor();
  await page.waitForFunction(()=>document.querySelector('[data-testid=task-drama-cover] img')?.naturalWidth>0);
  await page.getByTestId('production-task-header').screenshot({path:path.join(out,'真实剧集封面恢复.png')});
  await cover.click({button:'right'});await page.getByRole('dialog',{name:'封面编辑',exact:true}).waitFor();
  const frame=page.frameLocator('iframe[title="封面文字编辑器"]');
  await frame.locator('#cover').waitFor();await page.waitForFunction(()=>Array.from(document.querySelectorAll('iframe')).some(f=>f.contentWindow?.coverPreview?.ready));
  assert.equal(await frame.locator('.style-card').count(),15);
  await page.screenshot({path:path.join(out,'真实原封面可打开编辑.png'),fullPage:true});
  await page.getByRole('button',{name:'关闭封面编辑',exact:true}).click();await page.getByRole('dialog',{name:'封面编辑',exact:true}).waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  const result={realService:'http://127.0.0.1:8782',coverVisible:true,editorOpened:true,styleCount:15,browserErrors:errors,businessWrites:0};
  fs.writeFileSync(path.join(out,'live-ui-after.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
