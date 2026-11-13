/** Saved publishing profiles: built UI + real isolated API; MCP reads are fixtures, no draft creation. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(process.env.V3_PUBLISH_PROBE_OUTPUT||'local-test-output/v3-publishing-profiles-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];const checked=text=>{checks.push(text);console.log(text);};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 const api=(task,action='')=>`${info.url}/api/v2/publishing/tasks/${task}${action?'/'+action:''}`;
 async function post(task,action,data){const r=await context.request.post(api(task,action),{data});assert.ok(r.ok(),await r.text());return r.json();}
 async function get(task,action=''){const r=await context.request.get(api(task,action));assert.ok(r.ok(),await r.text());return r.json();}
 const addr=n=>({name:`测试公共地址${n}`,poiCheckSum:`profile-address-${n}`,fullAddress:`测试城市地点${n}`,city:'测试城市',_searchQuery:{query:`测试地点${n}`}});
 const a=addr('A'),b=addr('B');
 await post(info.task_id,'address-save',{address:a,default:true});await post(info.other_task_id,'address-save',{address:b,default:true});
 let original=await get(info.task_id);original.settings.schedule={schedule_type:'timing',interval:3,start_time:'2030-01-01 19:37'};
 original.settings.groups.forEach(g=>{g.desc='任务原简介';g.video_title='任务原视频标题';g.tags=['任务话题'];});
 await post(info.task_id,'settings',original.settings);original=await get(info.task_id);
 const beforeExecution=await get(info.task_id,'execution');
 await context.route('**/api/**',async route=>{
  const r=route.request(),url=new URL(r.url());
  if(r.method()!=='GET'){writes.push(url.pathname);if(/\/drafts$|\/release(?:\/|$)|\/cleanup(?:\/|$)|\/batches$/.test(url.pathname))throw Error('No generation/publication allowed');}
  if(url.pathname.endsWith('/connection'))return route.fulfill({json:{message:'测试账号已按ID匹配'}});
  if(url.pathname.endsWith('/dramas'))return route.fulfill({json:{items:[],binding:null,status:'not_found',queries:[],message:'测试：未执行外部剧集查询'}});
  if(r.method()==='GET'&&['/api/v2/production-tasks','/api/v2/production-task-summaries'].includes(url.pathname)){
   const response=await route.fetch(),body=await response.json();body.items=body.items.filter(t=>t.id===info.task_id);return route.fulfill({json:body});
  }
  return route.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByRole('button',{name:'自动发布',exact:true}).click();
  const work=page.getByRole('dialog',{name:'发布工作台',exact:true});await work.getByText('测试：未执行外部剧集查询',{exact:true}).waitFor();
  const connect=await work.getByRole('button',{name:'检查连接',exact:true}).boundingBox(),defaults=await work.getByRole('button',{name:'默认配置',exact:true}).boundingBox();assert.ok(defaults.x>connect.x+connect.width);
  await work.getByRole('button',{name:'默认配置',exact:true}).click();const manager=page.getByRole('dialog',{name:'自动发布默认配置',exact:true});
  await manager.getByRole('button',{name:'从当前设置另存',exact:true}).waitFor();await manager.getByRole('button',{name:'从当前设置另存',exact:true}).click();
  await manager.getByLabel('方案名称',{exact:true}).fill('通用发布测试');await manager.getByLabel('方案作品间隔',{exact:true}).selectOption('5');
  await manager.getByLabel('方案正剧份数',{exact:true}).fill('3');await manager.getByLabel('方案羊份数',{exact:true}).fill('2');
  await manager.getByLabel('视频标题',{exact:true}).fill('方案视频标题');await manager.getByLabel('简介',{exact:true}).fill('方案简介');
  await manager.getByLabel('话题',{exact:true}).fill('');await manager.getByLabel('话题',{exact:true}).pressSequentially('话题甲 话题乙');
  await manager.getByLabel('设为软件默认',{exact:true}).check();await manager.getByRole('button',{name:'保存方案',exact:true}).click();await manager.getByText('方案已保存；已有任务的设置保持原样。',{exact:true}).waitFor();
  let library=await get(info.task_id,'profiles'),profile=library.items.find(p=>p.name==='通用发布测试');assert.equal(library.software_default_id,profile.id);assert.deepEqual(profile.config.groups.normal.tags,['话题甲','话题乙']);assert.equal(profile.config.location.mode,'account');
  assert.equal(JSON.stringify(profile).includes('2030-01-01'),false);assert.deepEqual((await get(info.task_id)).settings,original.settings);
  checked('default button is right of connection; capture and save profile preserve task, separate sheep copies, multi-topic input and exclude exact clock');
  await page.screenshot({path:path.join(out,'profiles-manager.png')});await page.keyboard.press('Escape');await manager.waitFor({state:'hidden'});assert.ok(await work.isVisible());
  await work.getByLabel('当前发布方案',{exact:true}).selectOption(profile.id);const apply=page.getByRole('dialog',{name:'应用发布方案',exact:true});await apply.getByRole('button',{name:'应用并保存当前任务'}).waitFor();
  await page.keyboard.press('Escape');await apply.waitFor({state:'hidden'});assert.ok(await work.isVisible());assert.deepEqual((await get(info.task_id)).settings,original.settings);
  await work.getByLabel('当前发布方案',{exact:true}).selectOption(profile.id);await apply.getByRole('button',{name:'仅排期与份数',exact:true}).click();
  await apply.getByText('正剧 · 每视频份数',{exact:true}).waitFor();await page.screenshot({path:path.join(out,'profile-application-preview.png')});
  await apply.getByRole('button',{name:'应用并保存当前任务',exact:true}).click();await apply.waitFor({state:'hidden'});
  let task=await get(info.task_id);assert.equal(task.settings.groups[0].copies,3);assert.equal(task.settings.groups[1].copies,2);assert.equal(task.settings.groups[0].desc,'任务原简介');assert.equal(task.settings.schedule.start_time,'2030-01-01 19:37');assert.equal(task.settings.schedule.interval,5);assert.equal(task.settings.groups[1].start_time,'2030-01-01 19:52');
  checked('Escape closes only top dialog; cancel is read-only; timing-only apply preserves content and exact start while recalculating next group');
  await work.getByLabel('当前发布方案',{exact:true}).selectOption(profile.id);await apply.getByRole('button',{name:'自选范围',exact:true}).click();
  for(const label of ['排期规则','份数与排列','视频声明与原创','地址与挂载'])await apply.getByLabel(label,{exact:true}).uncheck();
  await apply.getByText('正剧 · 简介',{exact:true}).waitFor();assert.equal(await apply.getByText('正剧 · 每视频份数',{exact:true}).count(),0);
  await apply.getByLabel('文案与追评',{exact:true}).uncheck();assert.ok(await apply.getByRole('button',{name:'应用并保存当前任务',exact:true}).isDisabled());await page.keyboard.press('Escape');
  assert.deepEqual((await get(info.task_id)).settings,task.settings);checked('custom scope preview lists only selected content; empty selection cannot apply and cancellation does not save');
  await work.getByLabel('每个视频的份数',{exact:true}).fill('4');await work.getByText('与配置不一致',{exact:true}).waitFor();
  await work.getByRole('button',{name:'默认配置',exact:true}).click();await manager.getByRole('button',{name:'从当前设置另存',exact:true}).click();await manager.getByLabel('方案名称',{exact:true}).fill('捕获未保存修改');assert.equal(await manager.getByLabel('方案正剧份数',{exact:true}).inputValue(),'4');
  await page.keyboard.press('Escape');const confirm=page.getByRole('alertdialog',{name:'有未保存的方案修改',exact:true});await confirm.waitFor();await page.keyboard.press('Escape');await confirm.waitFor({state:'hidden'});assert.ok(await manager.isVisible());
  await manager.getByRole('button',{name:'保存方案',exact:true}).click();await manager.getByText('方案已保存；已有任务的设置保持原样。',{exact:true}).waitFor();assert.equal((await get(info.task_id)).settings.groups[0].copies,3);
  checked('unsaved task adjustments can be captured without saving task; styled confirmation and nested Escape preserve parent');
  await manager.getByRole('button',{name:'复制',exact:true}).click();await manager.getByLabel('方案名称',{exact:true}).fill('可删除副本');await manager.getByRole('button',{name:'保存方案',exact:true}).click();await manager.getByText('方案已保存；已有任务的设置保持原样。',{exact:true}).waitFor();
  await manager.getByRole('button',{name:'删除',exact:true}).click();await page.getByRole('alertdialog',{name:'删除发布方案',exact:true}).getByRole('button',{name:'删除方案',exact:true}).click();await manager.getByText('方案已删除，已有任务未改变。',{exact:true}).waitFor();assert.equal((await get(info.task_id,'profiles')).items.some(p=>p.name==='可删除副本'),false);
  await manager.getByRole('button',{name:/^通用发布测试/}).click();await manager.getByLabel('方案名称',{exact:true}).fill('通用发布新版');await manager.getByLabel('方案地址方式',{exact:true}).selectOption('public');await manager.getByLabel('方案公共地址',{exact:true}).selectOption(b.poiCheckSum);
  await manager.getByRole('button',{name:'保存并应用当前任务',exact:true}).click();await apply.getByText('正剧 · 地址',{exact:true}).waitFor();await apply.getByRole('button',{name:'应用并保存当前任务',exact:true}).click();await apply.waitFor({state:'hidden'});
  task=await get(info.task_id);assert.equal(task.settings.groups[0].desc,'方案简介');assert.equal(task.settings.groups[1].desc,'方案简介');assert.deepEqual(task.settings.groups[0].location,b);assert.deepEqual(task.default_address,a);assert.deepEqual((await get(info.other_task_id)).default_address,b);assert.equal(task.settings.groups[1].copies,2);
  checked('copy/delete/rename and save-then-apply work; inherited sheep content keeps independent copies; fixed shared address leaves account defaults unchanged');
  const applied=structuredClone(task.settings);profile=(await get(info.task_id,'profiles')).items.find(p=>p.id===profile.id);
  const updated=structuredClone(profile);updated.config.groups.normal.copies=8;await post(info.task_id,'profile-save',updated);assert.deepEqual((await get(info.task_id)).settings,applied);
  await work.getByRole('button',{name:'默认配置',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[data-publishing-profiles] fieldset')?.disabled);await manager.getByRole('button',{name:'关闭默认配置',exact:true}).click();await work.getByText(/与配置不一致/).waitFor();
  await work.getByLabel('当前发布方案',{exact:true}).selectOption(profile.id);await apply.getByText('正剧 · 每视频份数',{exact:true}).waitFor();await page.keyboard.press('Escape');
  const accountCfg=structuredClone(updated);delete accountCfg.id;accountCfg.name='账号优先方案';accountCfg.config.schedule.interval=10;const accountProfile=await post(info.task_id,'profile-save',{...accountCfg,account_default:true});
  const other=await get(info.other_task_id);assert.equal(other.settings.profile_ref.id,profile.id);assert.equal(other.settings.schedule.interval,5);
  const dramaResponse=await context.request.post(`${info.url}/api/v2/dramas`,{data:{current_name:'默认配置新任务测试剧',theater_id:original.drama.theater_id}});assert.ok(dramaResponse.ok(),await dramaResponse.text());
  const fresh=await context.request.post(`${info.url}/api/v2/production-tasks`,{data:{source_id:'profile-new-task',account_name:'一只羊13652',drama_name:'默认配置新任务测试剧',planned_publish_at:''}});assert.ok(fresh.ok(),await fresh.text());const created=await fresh.json();
  const newTask=await get(created.id);assert.equal(newTask.settings.profile_ref.id,accountProfile.profile.id);assert.equal(newTask.settings.schedule.interval,10);assert.equal(newTask.settings.schedule.start_time,'');assert.deepEqual((await get(info.task_id)).settings,applied);
  checked('profile updates do not overwrite saved task; same profile can be selected again; account default precedes software default on new tasks with start time pending');
  if(process.argv.includes('--refinements')){
   const connectBox=await work.getByRole('button',{name:'检查连接',exact:true}).boundingBox(),pickerBox=await work.getByLabel('当前发布方案',{exact:true}).boundingBox(),defaultBox=await work.getByRole('button',{name:'默认配置',exact:true}).boundingBox();
   assert.ok(connectBox.x+connectBox.width<pickerBox.x);assert.ok(pickerBox.x+pickerBox.width<defaultBox.x);assert.ok(Math.abs(pickerBox.y+pickerBox.height/2-defaultBox.y-defaultBox.height/2)<1);
   await page.screenshot({path:path.join(out,'aligned-profile-header.png')});checked('profile picker is between connection and defaults, with status on same line and vertically centered');
   await work.getByRole('button',{name:'默认配置',exact:true}).click();await manager.getByRole('button',{name:'新建方案',exact:true}).click();
   assert.equal(await manager.getByLabel('方案正剧挂载',{exact:true}).inputValue(),'true');assert.equal(await manager.getByLabel('方案羊挂载',{exact:true}).inputValue(),'false');
   await manager.getByLabel('方案名称',{exact:true}).fill('历史与独立挂载验证');await manager.getByLabel('视频标题',{exact:true}).fill('新历史视频标题');await manager.getByLabel('简介',{exact:true}).fill('新历史简介');await manager.getByLabel('话题',{exact:true}).fill('新话题甲 新话题乙');
   await manager.getByText('追评与更多设置',{exact:true}).click();await manager.getByLabel('短标题（选填，6–16字）',{exact:true}).fill('新历史短标题');await manager.getByLabel('追评',{exact:true}).fill('新历史追评');await manager.getByLabel('方案视频声明',{exact:true}).selectOption('7');await manager.getByLabel('转载来源',{exact:true}).fill('新历史转载来源');
   await manager.getByLabel('方案正剧挂载',{exact:true}).selectOption('false');await manager.getByLabel('方案羊挂载',{exact:true}).selectOption('true');
   await manager.getByRole('button',{name:'保存方案',exact:true}).click();await manager.getByText('方案已保存；已有任务的设置保持原样。',{exact:true}).waitFor();
   const savedProfile=(await get(info.task_id,'profiles')).items.find(p=>p.name==='历史与独立挂载验证');assert.equal(savedProfile.config.groups.normal.mount_required,false);assert.equal(savedProfile.config.groups.sheep.mount_required,true);assert.equal(savedProfile.config.sheep_inherit,true);assert.deepEqual((await get(info.task_id)).settings,applied);
   await manager.getByRole('button',{name:'视频标题历史',exact:true}).click();const history=page.getByRole('dialog',{name:'视频标题历史记录',exact:true});await history.getByLabel('搜索视频标题历史',{exact:true}).fill('任务原');await history.getByRole('button',{name:'任务原视频标题',exact:true}).click();assert.equal(await manager.getByLabel('视频标题',{exact:true}).inputValue(),'任务原视频标题');
   await manager.getByRole('button',{name:'视频标题历史',exact:true}).click();await history.getByRole('button',{name:'新历史视频标题',exact:true}).click();
   await manager.getByRole('button',{name:'简介历史',exact:true}).click();const descHistory=page.getByRole('dialog',{name:'简介历史记录',exact:true});await descHistory.getByRole('button',{name:'删除历史：任务原简介',exact:true}).click();await descHistory.getByRole('button',{name:'任务原简介',exact:true}).waitFor({state:'hidden'});await page.keyboard.press('Escape');assert.ok(await manager.isVisible());assert.ok(await work.isVisible());
   for(const label of ['话题历史','短标题（选填，6–16字）历史','追评历史','转载来源历史'])await manager.getByRole('button',{name:label,exact:true}).waitFor({state:'visible'});
   const records=await get(info.task_id,'history');assert.equal(records.desc.includes('任务原简介'),false);assert.ok(records.desc.includes('新历史简介'));assert.ok(records.repost_source.includes('新历史转载来源'));await page.screenshot({path:path.join(out,'profile-history-and-separate-mounts.png')});
   await page.keyboard.press('Escape');await manager.waitFor({state:'hidden'});checked('configuration histories support search, selection, deletion, shared persistence and layered Escape; new profiles have independent normal/sheep mount defaults');
   const mount=work.getByLabel('本组挂载方式',{exact:true});await mount.selectOption('false');await work.getByText('本组不挂载剧集；已记住的剧集关联会保留。',{exact:true}).waitFor();assert.equal(await work.getByLabel('搜索挂载剧集',{exact:true}).count(),0);
   await work.getByRole('tab',{name:/^羊视频/}).click();assert.equal(await mount.inputValue(),'false');await mount.selectOption('true');await work.getByRole('button',{name:'保存设置',exact:true}).click();await work.getByText('发布设置已保存。',{exact:true}).waitFor();
   let changed=await get(info.task_id);assert.equal(changed.settings.groups[0].mount_required,false);assert.equal(changed.settings.groups[1].mount_required,true);
   await mount.selectOption('false');await work.getByRole('tab',{name:/^正剧视频/}).click();await mount.selectOption('true');await work.getByRole('button',{name:'保存设置',exact:true}).click();await work.getByText('发布设置已保存。',{exact:true}).waitFor();
   checked('visible per-group mount selector saves independent values and no-mount hides irrelevant matching controls');
  }
  await page.setViewportSize({width:1200,height:820});await work.getByRole('button',{name:'默认配置',exact:true}).click();await manager.getByLabel('方案名称',{exact:true}).waitFor();await page.waitForFunction(()=>!document.querySelector('[data-publishing-profiles] fieldset')?.disabled);
  assert.ok(await manager.evaluate(e=>e.scrollWidth<=e.clientWidth));assert.ok(await work.evaluate(e=>e.scrollWidth<=e.clientWidth));await page.screenshot({path:path.join(out,'profiles-1200.png')});
  await page.keyboard.press('Escape');await manager.waitFor({state:'hidden'});await page.keyboard.press('Escape');await work.waitFor({state:'hidden'});
  assert.deepEqual(await get(info.task_id,'execution'),beforeExecution);assert.deepEqual(errors,[]);checked('1200px layout has no horizontal overflow; task execution unchanged; no browser errors or draft/publication requests');
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({checks,errors,writes,mcp:'connection and drama reads mocked; all profile/task persistence real isolated API'},null,2));
 }catch(e){await page.screenshot({path:path.join(out,'profiles-failure.png')});fs.writeFileSync(path.join(out,'browser-failure.json'),JSON.stringify({error:e.stack,checks,errors,writes},null,2));throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
