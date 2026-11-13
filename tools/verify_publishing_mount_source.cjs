/** Built UI + real isolated publishing/catalogue metadata; fixture MCP only. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-publishing-mount-source-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1540,height:1050}}),page=await context.newPage(),checks=[],errors=[],writes=[];
 const root=`${info.url}/api/v2/publishing/tasks/${info.task_id}`;
 const get=async suffix=>(await context.request.get(root+(suffix?'/'+suffix:'')+'?probe='+Date.now())).json();
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET'){writes.push(new URL(r.url()).pathname);if(/\/release(?:\/|$)|\/cleanup(?:\/|$)|\/batches$/.test(new URL(r.url()).pathname))throw Error('Forbidden production write');}});
 const work=page.getByRole('dialog',{name:'发布工作台',exact:true});
 const picker=work.getByLabel('挂载方式',{exact:true});
 async function opened(){await page.getByRole('button',{name:'自动发布',exact:true}).click();await picker.waitFor();await page.waitForFunction(()=>!document.querySelector('[aria-label="挂载方式"]')?.disabled&&!document.querySelector('[aria-label="挂载方式"]')?.closest('fieldset')?.disabled);}
 async function mode(value){await picker.selectOption(value);await work.getByText('挂载方式已保存到当前任务的发布设置。',{exact:true}).waitFor();assert.equal((await get()).settings.mount_source,value);}
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByTestId('production-task-header').getByText('小程序挂载',{exact:true}).waitFor();await opened();
  await work.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor();assert.equal(await picker.inputValue(),'mini_drama');await work.getByText('测试短剧小程序',{exact:true}).waitFor();
  let data=await get();assert.equal(data.task_mount_source,'mini_drama');assert.equal(data.binding.drama.id,'fixture-mini-selected');assert.equal(data.binding.from_task,true);checks.push('publishing picker inherits task source and explicit catalogue selection instead of guessing by title');
  await page.screenshot({path:path.join(out,'miniapp-inherited.png')});
  await work.getByLabel('视频标题（选填）',{exact:true}).fill('切换方式保留的标题');await mode('channels_drama');data=await get();assert.equal(data.settings.groups[0].video_title,'切换方式保留的标题');assert.equal(data.binding.drama.id,'fixture-channel-selected');assert.equal(data.task_mount_source,'mini_drama');
  checks.push('switching to video source saves current edits, resolves correct typed binding and preserves original creation snapshot');
  await page.keyboard.press('Escape');await work.waitFor({state:'hidden'});await opened();assert.equal(await picker.inputValue(),'channels_drama');await work.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor();
  await mode('mini_drama');assert.equal((await get()).binding.drama.id,'fixture-mini-selected');await work.getByText('测试短剧小程序',{exact:true}).waitFor();checks.push('publishing override survives reopening and switching back restores the original miniapp ID');
  await work.getByRole('button',{name:'仅检查',exact:true}).click();await work.getByText('参数检查通过，可以生成本地草稿。',{exact:true}).waitFor();
  await mode('channels_drama');await work.getByRole('button',{name:'仅检查',exact:true}).click();await work.getByText('参数检查通过，可以生成本地草稿。',{exact:true}).waitFor();checks.push('both native mount modes pass actual server-side parameter checks');
  await mode('plugin');assert.equal(await work.getByLabel('本组挂载方式',{exact:true}).count(),0);assert.equal(await work.getByLabel('搜索挂载剧集',{exact:true}).count(),0);await work.getByText('插件方式：仅生成小V猫本地草稿，不附加原生短剧挂载；后续由插件处理。',{exact:true}).waitFor();assert.equal((await get()).binding,null);
  await page.keyboard.press('Escape');await work.waitFor({state:'hidden'});await opened();assert.equal(await picker.inputValue(),'plugin');checks.push('plugin choice persists and hides native matching without discarding normal/sheep group settings');
  await work.getByRole('button',{name:'检查并生成草稿',exact:true}).click();
  let execution;
  for(let i=0;i<100;i++){execution=await get('execution');if(!execution.running&&execution.state==='ready'&&execution.items.length===2)break;await page.waitForTimeout(100);}
  assert.equal(execution.items.length,2);assert.ok(execution.items.every(i=>i.draft_id&&i.status==='ready'&&!('CAT_extReading' in i.payload.platformOptions)));assert.ok(execution.items.every(i=>Object.values(i.checks).every(Boolean)));checks.push('catalogue handoff guard allows integrated plugin path and fixture drafts omit all native drama components');
  await page.setViewportSize({width:1200,height:820});assert.ok(await work.evaluate(e=>e.scrollWidth<=e.clientWidth));await page.screenshot({path:path.join(out,'plugin-1200.png')});assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({checks,errors,writes,execution,mcp:'fixture account/worker/draft client; all HTTP routing and SQLite persistence real isolated V3',realPublish:false},null,2));console.log(JSON.stringify({checks,errors}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png')});fs.writeFileSync(path.join(out,'browser-failure.json'),JSON.stringify({error:e.stack,checks,errors,writes},null,2));throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
