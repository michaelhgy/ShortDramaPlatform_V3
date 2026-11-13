/** Built front end + isolated V3 data: navigation only, no generation or publishing. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-production-entries-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];
function checked(text){checks.push(text);console.log(text);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 await context.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()!=='GET'){
   writes.push(url.pathname);
   if(!/\/publishing\/tasks\/[a-f0-9]+\/(settings|connection|dramas)$/.test(url.pathname))throw Error('Mutation forbidden in navigation verification: '+url.pathname);
  }
  await route.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'生产中心',exact:true}).click();
  const publish=page.getByRole('button',{name:'自动发布',exact:true});await publish.waitFor();
  assert.equal(await page.getByRole('navigation',{name:'生产方式',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'成片制作',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'打开发布工作台',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'手工登记',exact:true}).count(),0);
  assert.equal(await page.getByText('发布准备',{exact:true}).count(),0);
  const remove=page.getByRole('button',{name:'删除剧集',exact:true});
  const a=await remove.boundingBox(),b=await publish.boundingBox();assert.ok(b.x>=a.x+a.width&&Math.abs(a.y-b.y)<2);
  const selected=await page.getByTestId('production-task-header').getByRole('heading',{level:3}).innerText();
  checked('removed bottom release strip/manual entry and top mode tabs; auto-publish sits right of delete');
  await page.getByTestId('production-task-header').screenshot({path:path.join(out,'task-header.png')});
  await publish.click();const publishing=page.getByRole('dialog',{name:'发布工作台',exact:true});
  await publishing.getByText(/名称一致或仅符号差异，已自动关联。|已复用原关联，当前账号可挂载。/).waitFor({timeout:100000});
  await page.keyboard.press('Escape');await publishing.waitFor({state:'detached'});
  checked('renamed button opens the same local-draft workbench and Escape closes it');
  await page.getByRole('button',{name:'制作模板',exact:true}).click();
  const modal=page.getByRole('dialog',{name:'模板制作',exact:true});await modal.waitFor();
  await modal.getByRole('button',{name:'生成模板',exact:true}).waitFor();
  await modal.getByRole('heading',{name:/已生成模板/}).waitFor();
  assert.equal(await page.getByTestId('production-task-header').getByRole('heading',{level:3}).innerText(),selected);
  assert.equal(await modal.evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await page.screenshot({path:path.join(out,'template-modal.png')});
  checked('make-template opens existing full generation/queue/result view as a dialog, retaining selected task');
  await modal.getByRole('button',{name:'生成模板',exact:true}).click();
  const generation=page.getByRole('dialog',{name:'生成模板',exact:true});await generation.waitFor();
  await generation.getByRole('spinbutton').fill('3');
  await page.keyboard.press('Escape');await generation.waitFor({state:'detached'});assert.equal(await modal.count(),1);
  await page.keyboard.press('Escape');await modal.waitFor({state:'detached'});
  assert.equal(await page.getByTestId('production-task-header').getByRole('heading',{level:3}).innerText(),selected);
  checked('nested generation dialog consumes first Escape; second closes template view without submitting');
  await page.getByRole('button',{name:'制作模板',exact:true}).click();
  await modal.getByRole('button',{name:'关闭模板制作',exact:true}).click();await modal.waitFor({state:'detached'});
  await page.getByRole('button',{name:'制作模板',exact:true}).click();
  await modal.getByRole('button',{name:'生成参数',exact:true}).click();await modal.waitFor({state:'detached'});
  await page.getByRole('button',{name:'生产中心',exact:true}).click();await publish.waitFor();
  checked('close button works; parameter entry closes modal before navigating and returns to same task');
  await page.setViewportSize({width:1200,height:820});await page.getByRole('button',{name:'制作模板',exact:true}).click();await modal.waitFor();
  assert.equal(await modal.evaluate(e=>e.scrollWidth>e.clientWidth),false);
  const rect=await modal.boundingBox();assert.ok(rect.width<=1200&&rect.height<=820);
  await page.screenshot({path:path.join(out,'template-modal-1200.png')});await page.keyboard.press('Escape');
  checked('template dialog stays inside a 1200x820 viewport with its own scrolling');
  // Empty-data response fixture protects the old ability to make templates without a task.
  await context.route('**/api/v2/production-tasks**',route=>route.request().method()==='GET'?route.fulfill({json:{items:[]}}):route.continue());
  await context.route('**/api/v2/production-task-summaries**',route=>route.fulfill({json:{items:[]}}));
  await page.evaluate(()=>localStorage.clear());
  await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();
  await page.getByText('选择制作任务查看成片；也可以先制作公共模板。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'制作模板',exact:true}).click();await modal.waitFor();await page.keyboard.press('Escape');
  checked('empty-task state retains make-template entry without restoring top mode tabs (response fixture)');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'navigation-result.json'),JSON.stringify({status:'PASS',checks,errors,writes},null,2));
 }catch(error){await page.screenshot({path:path.join(out,'navigation-failure.png')});fs.writeFileSync(path.join(out,'navigation-result.json'),JSON.stringify({status:'FAIL',checks,errors,writes,error:String(error)},null,2));throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
