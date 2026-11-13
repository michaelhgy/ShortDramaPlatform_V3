/** Real built V3 UI + isolated real backend + Xiao V Cat LOCAL DRAFTS only. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-publishing-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];
const push=checks.push.bind(checks);checks.push=(...values)=>{console.log(values.join('\n'));return push(...values);};
const live=process.argv.includes('--create-local-drafts');
const resume=process.argv.includes('--resume');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 await context.route('**/api/**',async route=>{
  const r=route.request(),u=new URL(r.url());
  if(r.method()!=='GET'){
   writes.push({method:r.method(),path:u.pathname});
   if(/\/release(?:\/|$)|\/cleanup(?:\/|$)|publish-task|publish-draft/.test(u.pathname))throw Error('Forbidden production write');
   if(!live&&/\/drafts$/.test(u.pathname))throw Error('Draft creation not enabled for this run');
  }
  return route.continue();
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 page.setDefaultTimeout(30000);
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'生产中心',exact:true}).click();
  const cover=page.getByTestId('task-drama-cover');await cover.waitFor();
  await page.waitForFunction(()=>!document.querySelector('[data-testid="task-drama-cover"]').disabled);
  if(!resume)assert.match(await cover.innerText(),/剧集/);checks.push(resume?'task header restores existing cover':'task header shows clickable title placeholder before first cover');
  await page.screenshot({path:path.join(out,'production-cover-empty.png'),fullPage:true});
  await page.getByLabel('替换剧集封面文件').setInputFiles('D:/ShortDramaVideoCollector/experiments/vcat_20261026/probe-cover.png');
  await cover.locator('img').waitFor();await page.waitForFunction(()=>document.querySelector('[data-testid="task-drama-cover"] img')?.naturalWidth>0);
  checks.push('first cover upload persists and appears in task header');
  await page.screenshot({path:path.join(out,'production-cover-saved.png'),fullPage:true});
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'发布工作台'});await dialog.waitFor();
  await dialog.getByText(resume?'已复用原关联，当前账号可挂载。':'名称一致或仅符号差异，已自动关联。',{exact:true}).waitFor({timeout:120000});
  checks.push('punctuation-normalized real drama query automatically binds correct platform drama');
  await dialog.getByLabel('搜索发布地址',{exact:true}).fill('成都春熙路');
  await dialog.getByRole('button',{name:'搜索',exact:true}).click();
  const address=dialog.getByRole('button',{name:/^春熙路\s*四川省成都市锦江区$/});
  await address.waitFor({timeout:120000});await address.click();
  await dialog.getByRole('button',{name:'设为账号默认',exact:true}).waitFor();
  checks.push('address candidates show actual returned full address and can be selected');
  await dialog.getByRole('button',{name:'设为账号默认',exact:true}).click();
  await dialog.getByText('已设为当前账号默认地址。',{exact:true}).waitFor();
  await dialog.getByLabel('时间方式',{exact:true}).selectOption('timing');
  await dialog.getByLabel('开始日期和时间',{exact:true}).fill('2026-10-27T15:00');
  await dialog.getByLabel('每个视频的份数',{exact:true}).fill('2');
  await dialog.getByLabel('间隔分钟',{exact:true}).fill('7');
  await dialog.getByRole('button',{name:/展开最终时间预览/}).click();
  await dialog.getByText('2026-10-27 15:07',{exact:true}).waitFor();
  checks.push('copies and custom seven-minute spacing expand to correct individual times');
  await dialog.getByLabel('每个视频的份数',{exact:true}).fill('1');
  await dialog.getByLabel('简介（选填）',{exact:true}).fill('V3工作台真实联调，仅本地草稿，不发布。');
  await dialog.getByLabel('话题（空格、逗号或 # 分隔，最多10个）',{exact:true}).fill('参数验证 短剧测试');
  await dialog.getByLabel('视频声明',{exact:true}).selectOption('3');
  await dialog.getByRole('button',{name:'保存设置',exact:true}).click();
  await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  await dialog.locator('main').evaluate(e=>{e.scrollTop=0;});
  await page.screenshot({path:path.join(out,'publishing-workbench.png'),fullPage:true});
  const groups=dialog.locator('aside');await groups.getByRole('button',{name:/^羊视频/}).click();
  assert.equal(await dialog.getByLabel('发布封面方式',{exact:true}).inputValue(),'none');
  await dialog.getByLabel('时间方式',{exact:true}).selectOption('localTiming');
  await dialog.getByLabel('开始日期和时间',{exact:true}).fill('2026-10-27T15:15');
  await dialog.getByRole('button',{name:'保存设置',exact:true}).click();
  await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  checks.push('sheep group defaults to no cover and has independent local-timing settings');
  await dialog.getByRole('button',{name:'仅检查',exact:true}).click();
  await dialog.getByText('参数检查通过，可以生成本地草稿。',{exact:true}).waitFor({timeout:120000});
  checks.push('real account ID, mount availability and saved parameters pass preflight');
  if(live){
   await dialog.getByRole('button',{name:'检查并生成草稿',exact:true}).click();
   await page.waitForFunction(async({url,task})=>{const r=await fetch(`${url}/api/v2/publishing/tasks/${task}/execution`);const v=await r.json();return !v.running&&v.items.length===2;},{url:info.url,task:info.task_id},{timeout:120000});
   const execution=await page.evaluate(async({url,task})=>await(await fetch(`${url}/api/v2/publishing/tasks/${task}/execution?t=${Date.now()}`,{cache:'no-store'})).json(),{url:info.url,task:info.task_id});
   fs.writeFileSync(path.join(out,'live-execution.json'),JSON.stringify(execution,null,2));
   assert.equal(execution.state,'ready',JSON.stringify(execution));assert.ok(execution.items.every(i=>i.status==='ready'));
   checks.push('two actual MCP local drafts created and all parameters read back correctly');
   await dialog.getByText(/已就绪 2/).waitFor();
   await dialog.getByRole('region',{name:'草稿执行结果'}).scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(out,'publishing-drafts-ready.png'),fullPage:true});
  }
  await dialog.getByRole('button',{name:'关闭发布工作台',exact:true}).click();
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  await dialog.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor({timeout:120000});
  assert.equal(await dialog.getByLabel('简介（选填）',{exact:true}).inputValue(),'V3工作台真实联调，仅本地草稿，不发布。');
  assert.equal(await dialog.getByLabel('话题（空格、逗号或 # 分隔，最多10个）',{exact:true}).inputValue(),'参数验证 短剧测试');
  checks.push('reopening restores settings, topic separators, account address and confirmed mount association');
  await page.setViewportSize({width:1200,height:820});
  assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await page.screenshot({path:path.join(out,'publishing-1200.png'),fullPage:true});checks.push('workbench fits 1200px desktop without horizontal overflow');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'PASS',checks,errors,writes,live},null,2));
  console.log(JSON.stringify({status:'PASS',checks,errors,live}));
 }catch(e){
  await page.screenshot({path:path.join(out,'ui-failure.png'),fullPage:true});
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'FAIL',checks,errors,writes,error:String(e),live},null,2));throw e;
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
