const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve('local-test-output/cover-integration-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'current.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}); const context=await browser.newContext({viewport:{width:1600,height:1100}});
 const page=await context.newPage(),errors=[],writes=[],checks=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await require('./test_helpers.cjs').acceptConfirmations(page);
 await context.route('**/api/**',route=>{const r=route.request(),u=new URL(r.url());if(r.method()!=='GET')writes.push(u.pathname);
  if(/\/publishing\/.*\/(dramas|connection)$/.test(u.pathname))return route.fulfill({json:u.pathname.endsWith('/dramas')?{items:[],binding:null,status:'not_found',queries:[]}:{connected:false,message:'隔离检查不连接外部软件'}});
  if(/\/drafts$|\/release$|\/cleanup/.test(u.pathname)&&r.method()!=='GET')throw Error('External or destructive operation blocked');return route.continue();});
 const req=async(url,body)=>{const r=await context.request[body===undefined?'get':'post'](info.url+url,body===undefined?{}:{data:body});const v=await r.json();assert.ok(r.ok(),JSON.stringify(v));return v;};
 const snap=()=>req('/api/v2/cover-editor/dramas/'+info.drama_id);
 const close=async()=>{await page.frameLocator('iframe[title="封面文字编辑器"]').locator('#upload:not(:disabled)').waitFor({state:'attached'});await page.getByRole('button',{name:'关闭封面编辑',exact:true}).click();await page.getByRole('dialog',{name:'封面编辑',exact:true}).waitFor({state:'hidden'});};
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();
  const normal=page.getByTestId('task-drama-cover');await normal.waitFor();
  await page.waitForFunction(()=>document.querySelector('[data-testid=task-drama-cover]')?.dataset.dramaId);
  await normal.click({button:'right'});await page.getByText('还没有剧集封面，请先左键点击上传图片。',{exact:true}).waitFor();checks.push('missing-cover-reason');
  const fixture='D:/短剧推广运营系统/剧集资料/一口铁锅走天下/封面/一口铁锅走天下-封面.jpeg';
  await page.getByLabel('替换剧集封面文件').setInputFiles(fixture);await normal.locator('img').waitFor();await page.waitForFunction(()=>document.querySelector('[data-testid=task-drama-cover] img')?.naturalWidth>0);
  assert.equal(await page.getByTestId('task-sheep-cover').count(),0);checks.push('left-upload-and-default-single-cover');
  const coverBox=await normal.boundingBox(),clockBox=await page.getByTestId('production-task-header').getByText('计划发布时间：',{exact:false}).first().boundingBox();assert.ok(clockBox.y+clockBox.height<coverBox.y+coverBox.height);checks.push('publish-time-inside-top-header');
  await page.screenshot({path:path.join(out,'默认仅一张封面.png'),fullPage:true});
  await normal.click({button:'right'});const modal=page.getByRole('dialog',{name:'封面编辑',exact:true});await modal.waitFor();
  const frame=page.frameLocator('iframe[title="封面文字编辑器"]');await frame.locator('#tab-drama').waitFor();
  await frame.locator('#add-text').click();await frame.locator('#copy').fill('正式接入测试');await frame.locator('#save-use').click();
  await page.waitForFunction(async({id})=>(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).project.drama.versions.length===1,{id:info.drama_id});
  await frame.locator('#template-name').fill('跨剧通用');await frame.locator('#save-template').click();await frame.locator('#template-count').getByText('1 / 5',{exact:true}).waitFor();
  await frame.locator('#tab-sheep').click();await frame.locator('#add-text').click();await frame.locator('#copy').fill('羊头独立封面');await frame.locator('#save-use').click();
  await page.waitForFunction(async({id})=>(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).sheep_visible,{id:info.drama_id});
  await frame.locator('#save-use:not(:disabled)').waitFor();
  await page.screenshot({path:path.join(out,'正式编辑弹窗.png'),fullPage:true});await close();
  await page.getByTestId('task-sheep-cover').waitFor();checks.push('right-editor-save-durable-and-sheep-reveals');
  let data=await req(`/api/v2/publishing/tasks/${info.task_id}/context`);assert.notEqual(data.cover.path,data.sheep_cover.path);assert.equal(data.sheep_cover_visible,true);
  await page.screenshot({path:path.join(out,'独立双封面与上方时间.png'),fullPage:true});
  // Left click replacement remains functional for both; existing edited versions survive.
  await page.getByTestId('task-sheep-cover').click();await page.getByLabel('替换羊头封面文件').setInputFiles(fixture);
  await page.waitForFunction(async({id})=>(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).project.sheep.activeId==='original',{id:info.drama_id});
  const retained=await snap();assert.equal(retained.project.sheep.versions.length,1);assert.equal(retained.sheep_visible,false);checks.push('sheep-left-replace-keeps-edits-and-hides-original-card');
  await page.getByRole('button',{name:'打开发布工作台',exact:true}).click();const work=page.getByRole('dialog',{name:'发布工作台',exact:true});await work.waitFor();
  await work.getByLabel('发布封面方式',{exact:true}).waitFor();assert.equal(await work.getByLabel('发布封面方式').inputValue(),'drama');
  await work.locator('aside').getByRole('button',{name:/^羊视频/}).click();assert.equal(await work.getByLabel('发布封面方式').inputValue(),'drama');
  await page.screenshot({path:path.join(out,'发布对应封面.png'),fullPage:true});await work.getByRole('button',{name:'关闭发布工作台',exact:true}).click();checks.push('publishing-default-corresponding-both-groups');
  // Second drama uses its own background but shares the five-template library.
  await req('/api/v2/dramas/'+info.second_drama_id+'/cover',{filename:'cover.png',content_base64:'data:image/png;base64,'+fs.readFileSync(path.join(out,'默认仅一张封面.png')).toString('base64')});
  const secondPage=await context.newPage();await secondPage.goto(info.url+`/cover-editor.html?dramaId=${info.second_drama_id}&kind=drama`);await secondPage.waitForFunction(()=>window.coverPreview?.ready);
  await secondPage.locator('#template-select').selectOption({label:'跨剧通用'});await secondPage.locator('#apply-template').click();await secondPage.locator('#save-use').click();
  await secondPage.waitForFunction(async(id)=>(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).project.drama.versions.length===1,info.second_drama_id);
  await secondPage.locator('#save-state').getByText('已保存到软件',{exact:true}).waitFor();
  await secondPage.reload();await secondPage.waitForFunction(()=>window.coverPreview?.ready&&document.querySelector('#copy')?.value==='正式接入测试');assert.equal(await secondPage.locator('#copy').inputValue(),'正式接入测试');await secondPage.close();checks.push('cross-drama-template-and-reopen');
  // Original selection hides sheep card, even if the original was independently uploaded.
  await page.getByTestId('task-drama-cover').click({button:'right'});await frame.locator('#tab-sheep').click();await frame.locator('#versions [data-version]:not([data-version="original"])').click();await frame.locator('#delete-version').click();await close();
  await page.getByTestId('task-sheep-cover').waitFor({state:'hidden'});checks.push('custom-sheep-original-hidden-after-delete');
  await page.reload();await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByTestId('task-drama-cover').waitFor();await page.getByTestId('task-sheep-cover').waitFor({state:'hidden'});checks.push('full-page-reload-persistence');
  await page.setViewportSize({width:1280,height:900});await page.screenshot({path:path.join(out,'较窄窗口标题.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);checks.push('narrow-no-document-overflow');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({checks,errors,writes,externalPublishing:false},null,2));console.log(JSON.stringify({checks:checks.length,errors,externalPublishing:false}));
 }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
