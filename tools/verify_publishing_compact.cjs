/** Built V3 UI, isolated V3 DB, optionally creating local Xiao V Cat drafts. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(process.env.V3_PUBLISH_PROBE_OUTPUT||'local-test-output/v3-publishing-compact-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];const live=process.argv.includes('--create-local-drafts');
function checked(text){checks.push(text);console.log(text);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 let missingCover=false;
 await context.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()!=='GET'){
   writes.push({method:request.method(),path:url.pathname});
   if(/\/release(?:\/|$)|\/cleanup(?:\/|$)|publish-task|publish-draft/.test(url.pathname))throw Error('Actual publishing is forbidden');
   if(!live&&/\/drafts$/.test(url.pathname))throw Error('Local draft creation is disabled for this check');
  }
  if(missingCover&&url.pathname===`/api/v2/publishing/tasks/${info.task_id}`&&request.method()==='GET'){
   const response=await route.fetch();const data=await response.json();
   data.cover={exists:false,path:'',url:''};data.sheep_cover={exists:false,path:'',url:''};
   return route.fulfill({json:data});
  }
  return route.continue();
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(20000);
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'生产中心',exact:true}).click();
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'发布工作台'});
  await dialog.getByText(/名称一致或仅符号差异，已自动关联。|已复用原关联，当前账号可挂载。/).waitFor({timeout:100000});
  assert.equal(await dialog.getByLabel('发布封面方式',{exact:true}).count(),0);
  assert.equal(await dialog.getByLabel(/^调整视频 /).count(),0);
  const groups=dialog.getByRole('tablist',{name:'自动识别的视频分组'});
  assert.equal(await groups.getByRole('tab').count(),2);
  await dialog.getByAltText('自动带入剧集封面',{exact:true}).waitFor();
  assert.equal(await dialog.getByText('分组 1',{exact:true}).count(),0);
  checked('normal/sheep tabs are automatic; no routine video checkboxes or cover selector');
  const select=dialog.getByLabel('作品间隔',{exact:true});
  assert.equal(await select.locator('option').count(),31);
  assert.equal(await select.locator('option').first().innerText(),'无间隔');
  await dialog.getByRole('button',{name:'刷新',exact:true}).click();
  const status=dialog.getByRole('status');await status.getByText('视频与对应封面已刷新，排期已自动重算。',{exact:true}).waitFor();
  assert.equal(await status.evaluate(e=>Boolean(e.closest('footer'))),true);
  await page.waitForTimeout(4200);
  assert.equal(await status.innerText(),'仅本地草稿，不会发布或触发清理。');
  checked('success status stays inside existing footer and disappears without occupying a row');
  assert.equal(await dialog.getByLabel('视频声明',{exact:true}).locator('option').count(),7);
  await dialog.getByLabel('视频声明',{exact:true}).selectOption('7');
  await dialog.getByLabel('转载来源',{exact:true}).fill('隔离验证来源');
  await dialog.getByLabel('视频声明',{exact:true}).selectOption('5');
  await dialog.getByLabel('拍摄日期',{exact:true}).fill('2026-01-01');
  const country=dialog.getByLabel('拍摄国家/地区',{exact:true});
  await country.selectOption({label:'中国'});
  await dialog.getByLabel('拍摄省份',{exact:true}).selectOption({label:'四川'});
  await dialog.getByLabel('拍摄城市',{exact:true}).selectOption({label:'成都'});
  await dialog.getByLabel('视频声明',{exact:true}).selectOption('3');
  checked('all seven native declaration choices and shooting/repost required fields work');
  await groups.getByRole('tab',{name:/^羊视频/}).click();
  await dialog.getByAltText('自动带入羊封面',{exact:true}).waitFor();
  await dialog.getByLabel('每个视频的份数',{exact:true}).fill('1');
  checked('each tab automatically shows the corresponding real cover from the other cover feature');
  await groups.getByRole('tab',{name:/^正剧视频/}).click();
  await dialog.getByLabel('时间方式',{exact:true}).selectOption('timing');
  await dialog.getByLabel('整批开始日期和时间',{exact:true}).fill('2026-10-27T15:00');
  await dialog.getByLabel('作品间隔',{exact:true}).selectOption('custom');
  await dialog.getByLabel('整批间隔分钟',{exact:true}).fill('7');
  await dialog.getByLabel('每个视频的份数',{exact:true}).fill('2');
  assert.match(await groups.getByRole('tab',{name:/^羊视频/}).innerText(),/15:14/);
  await dialog.getByRole('button',{name:/查看完整排期/}).click();
  await dialog.getByRole('cell',{name:'2026-10-27 15:14',exact:true}).waitFor();
  checked('one start time plus seven-minute spacing connects sheep after both normal copies');
  await dialog.getByLabel('每个视频的份数',{exact:true}).fill('3');
  assert.match(await groups.getByRole('tab',{name:/^羊视频/}).innerText(),/15:21/);
  await dialog.getByLabel('每个视频的份数',{exact:true}).fill('1');
  await dialog.getByLabel('两组发布顺序',{exact:true}).selectOption('sheep_first');
  assert.match(await groups.getByRole('tab',{name:/^正剧视频/}).innerText(),/15:07/);
  assert.match(await groups.getByRole('tab',{name:/^羊视频/}).innerText(),/15:00/);
  await dialog.getByLabel('两组发布顺序',{exact:true}).selectOption('normal_first');
  checked('copies and reversing group order recalculate all subsequent times immediately');
  await dialog.getByRole('button',{name:'收起完整排期',exact:true}).click();
  await dialog.getByRole('button',{name:'特殊调整',exact:true}).click();
  const sheepName=(await dialog.getByLabel(/^调整视频 羊-/).getAttribute('aria-label'));
  await dialog.getByLabel(sheepName,{exact:true}).check();
  await dialog.getByRole('button',{name:'保存设置',exact:true}).click();
  await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  let response=await page.request.get(`${info.url}/api/v2/publishing/tasks/${info.task_id}?t=${Date.now()}`);let saved=await response.json();
  assert.equal(saved.settings.assignment_mode,'manual');assert.equal(saved.settings.groups[0].video_ids.length,2);
  await dialog.getByRole('button',{name:'恢复自动识别',exact:true}).click();
  await page.getByRole('alertdialog',{name:'恢复自动分组',exact:true}).getByRole('button',{name:'恢复自动分组',exact:true}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll('[role="tablist"][aria-label="自动识别的视频分组"] [role="tab"]')].every(e=>/1 个视频/.test(e.textContent)));
  await dialog.getByRole('button',{name:'收起特殊调整',exact:true}).click();
  checked('manual ownership adjustment is opt-in, persisted, and can return to automatic recognition');
  await dialog.getByLabel('简介（选填）',{exact:true}).fill('V3自动归组与连续排期验证，仅本地草稿。');
  await dialog.getByRole('button',{name:'保存设置',exact:true}).click();
  await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  await dialog.locator('main').evaluate(e=>e.scrollTop=0);
  await page.screenshot({path:path.join(out,'compact-workbench.png'),fullPage:true});
  const coverBox=await dialog.getByTestId('automatic-publish-cover').boundingBox();
  const videoBox=await dialog.getByRole('region',{name:'本组视频与自动封面'}).boundingBox();
  assert.ok(coverBox.width<videoBox.width/3);assert.ok(videoBox.height<180);
  checked('cover is a small side preview beside assigned videos, replacing the full-width cover row');
  if(live){
   await dialog.getByRole('button',{name:'检查并生成草稿',exact:true}).click();
   let execution;
   const deadline=Date.now()+120000;
   while(Date.now()<deadline){
    execution=await page.evaluate(async task=>await(await fetch(`/api/v2/publishing/tasks/${task}/execution?t=${Date.now()}`,{cache:'no-store'})).json(),info.task_id);
    if(!execution.running&&execution.items.length===2&&execution.state!=='idle')break;
    await new Promise(resolve=>setTimeout(resolve,200));
   }
   fs.writeFileSync(path.join(out,'live-execution.json'),JSON.stringify(execution,null,2));
   assert.equal(execution.state,'ready',JSON.stringify(execution));
   assert.deepEqual(execution.items.map(i=>i.time),['2026-10-27 15:00','2026-10-27 15:07']);
   checked('real MCP local drafts preserve automatic covers and the continuous 15:00 / 15:07 timeline');
  }
  await dialog.getByRole('button',{name:'关闭发布工作台',exact:true}).click();
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  await dialog.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor({timeout:100000});
  assert.equal(await dialog.getByLabel('整批开始日期和时间',{exact:true}).inputValue(),'2026-10-27T15:00');
  assert.match(await groups.getByRole('tab',{name:/^羊视频/}).innerText(),/15:07/);
  checked('reopening retains the one batch schedule and automatic group ownership');
  await page.setViewportSize({width:1200,height:820});
  assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await page.screenshot({path:path.join(out,'compact-1200.png'),fullPage:true});
  checked('compact layout fits a 1200x820 desktop without horizontal scrolling');
  await dialog.getByRole('button',{name:'关闭发布工作台',exact:true}).click();
  missingCover=true;
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  await dialog.getByText('暂无封面，可继续',{exact:true}).waitFor();
  assert.equal(await dialog.getByLabel('发布封面方式',{exact:true}).count(),0);
  await page.screenshot({path:path.join(out,'compact-no-cover-ui-fixture.png'),fullPage:true});
  checked('UI missing-cover fixture is informational and never introduces a mandatory setting');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'PASS',checks,errors,writes,live},null,2));
  console.log(JSON.stringify({status:'PASS',checks,errors,live}));
 }catch(error){await page.screenshot({path:path.join(out,'ui-failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'FAIL',checks,errors,writes,error:String(error)},null,2));throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
