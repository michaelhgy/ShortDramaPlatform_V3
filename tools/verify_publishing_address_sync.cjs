/** Real isolated persistence + built UI. No MCP calls or draft/publication writes. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-address-sync-history-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];function checked(value){checks.push(value);console.log(value);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 const api=(task,action='')=>`${info.url}/api/v2/publishing/tasks/${task}${action?'/'+action:''}`;
 async function get(task,action=''){const r=await context.request.get(api(task,action));assert.ok(r.ok(),await r.text());return r.json();}
 async function post(task,action,data){const r=await context.request.post(api(task,action),{data});assert.ok(r.ok(),await r.text());return r.json();}
 const address=n=>({name:`同步测试地点${n}`,poiCheckSum:`sync-place-${n}`,city:'测试城市',fullAddress:`测试城市完整地点${n}`,_searchQuery:{query:`同步测试地点${n}`},latitude:30,longitude:104});const a=address('A'),b=address('B');
 await post(info.task_id,'address-save',{address:a,default:true});await post(info.other_task_id,'address-save',{address:b,default:true});
 const config=(await get(info.task_id,'profiles')).items[0].config;config.schedule.schedule_type='now';config.groups.normal.video_title='历史测试标题';config.groups.normal.desc='历史测试简介';
 const profile=(await post(info.task_id,'profile-save',{name:'地址同步方案',config,software_default:true})).profile;
 const preview=await post(info.task_id,'profile-preview',{id:profile.id});await post(info.task_id,'settings',preview.settings);
 const before=await get(info.task_id,'execution');
 await context.route('**/api/**',async route=>{
  const r=route.request(),u=new URL(r.url());
  if(r.method()!=='GET'){writes.push(u.pathname);if(/\/drafts$|\/release(?:\/|$)|\/cleanup(?:\/|$)|\/batches$/.test(u.pathname))throw Error('Generation is forbidden');}
  if(u.pathname.endsWith('/connection'))return route.fulfill({json:{message:'测试账号匹配'}});
  if(u.pathname.endsWith('/dramas'))return route.fulfill({json:{items:[],binding:null,status:'not_found',message:'测试：不访问小V猫',queries:[]}});
  if(r.method()==='GET'&&['/api/v2/production-tasks','/api/v2/production-task-summaries'].includes(u.pathname)){
   const response=await route.fetch(),body=await response.json();body.items=body.items.filter(v=>v.id===info.task_id);return route.fulfill({json:body});
  }
  return route.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 const work=page.getByRole('dialog',{name:'发布工作台',exact:true}),manager=page.getByRole('dialog',{name:'自动发布默认配置',exact:true});
 async function openWork(){await page.getByRole('button',{name:'自动发布',exact:true}).click();await work.getByText('测试：不访问小V猫',{exact:true}).waitFor();}
 async function saved(){await work.getByRole('button',{name:'保存设置',exact:true}).click();await work.getByText('发布设置已保存。',{exact:true}).waitFor();}
 async function chooseAddress(value){const area=work.getByRole('region',{name:'发布地址',exact:true});await area.getByRole('button',{name:/^(更换|设置)$/}).click();await area.locator('[aria-label="公共地址列表"]').getByRole('button',{name:new RegExp('^'+value.name)}).click();await area.getByText(new RegExp('^'+value.name)).waitFor();}
 const placements=[];
 async function firstHistory(scope,label){
  await scope.getByRole('button',{name:`${label}历史`,exact:true}).scrollIntoViewIfNeeded();
  await page.evaluate(()=>{window.historyPositions=[];window.historyObserver=new MutationObserver(()=>{for(const e of document.querySelectorAll('[data-publishing-history]')){const r=e.getBoundingClientRect();window.historyPositions.push({x:r.x,y:r.y,width:r.width,height:r.height});}});window.historyObserver.observe(document.body,{subtree:true,childList:true,attributes:true});});
  await scope.getByRole('button',{name:`${label}历史`,exact:true}).click();const popup=page.getByRole('dialog',{name:`${label}历史记录`,exact:true});await popup.waitFor();
  await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
  const samples=await page.evaluate(()=>{window.historyObserver.disconnect();return window.historyPositions;});assert.ok(samples.length);assert.ok(samples.every(p=>p.x>=12&&p.y>=12),JSON.stringify(samples));placements.push({label,samples});
  await page.keyboard.press('Escape');await popup.waitFor({state:'hidden'});assert.ok(await scope.isVisible());
 }
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();await openWork();await work.getByText('与配置一致',{exact:true}).waitFor();
  await firstHistory(work,'视频标题（选填）');await firstHistory(work,'视频标题（选填）');await firstHistory(work,'简介（选填）');
  await page.keyboard.press('Escape');await work.waitFor({state:'hidden'});await openWork();await firstHistory(work,'视频标题（选填）');
  checked('first and repeated history openings, other fields and remounted workbench never render the popup at the top-left');
  await chooseAddress(b);await work.getByRole('tab',{name:/^羊视频/}).click();await work.getByRole('region',{name:'发布地址',exact:true}).getByText(b.name,{exact:true}).waitFor();assert.equal((await get(info.task_id)).default_address.poiCheckSum,a.poiCheckSum);
  await saved();let task=await get(info.task_id);assert.deepEqual(task.settings.groups.map(g=>g.location),[b,b]);assert.ok(task.settings.sync_location);
  checked('changing normal address immediately updates sheep and saves full parameters without changing account defaults');
  await work.getByLabel('正剧与羊同步地址',{exact:true}).uncheck();await chooseAddress(a);await saved();task=await get(info.task_id);assert.deepEqual(task.settings.groups.map(g=>g.location),[b,a]);assert.equal(task.settings.sync_location,false);
  await page.keyboard.press('Escape');await work.waitFor({state:'hidden'});await openWork();assert.equal(await work.getByLabel('正剧与羊同步地址',{exact:true}).isChecked(),false);
  await work.getByRole('tab',{name:/^羊视频/}).click();await work.getByRole('region',{name:'发布地址',exact:true}).getByText(new RegExp('^'+a.name)).waitFor();
  await work.getByRole('region',{name:'发布地址',exact:true}).getByRole('button',{name:'不显示位置',exact:true}).click();await work.getByLabel('正剧与羊同步地址',{exact:true}).check();await saved();task=await get(info.task_id);assert.deepEqual(task.settings.groups.map(g=>g.location),[null,null]);
  await chooseAddress(b);await work.getByRole('tab',{name:/^正剧视频/}).click();await work.getByRole('region',{name:'发布地址',exact:true}).getByText(b.name,{exact:true}).waitFor();
  await chooseAddress(a);await saved();await work.getByText('与配置一致',{exact:true}).waitFor();
  checked('independent mode persists after reopening; enabling sync uses current group including no-location; edits from sheep sync back to normal');
  const good=work.getByText('与配置一致',{exact:true});const goodColor=await good.evaluate(e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color}));
  await work.getByLabel('正剧与羊同步地址',{exact:true}).uncheck();const bad=work.getByText('与配置不一致',{exact:true});await bad.waitFor();const badColor=await bad.evaluate(e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color}));assert.notDeepEqual(goodColor,badColor);assert.equal(await work.getByText('本任务已调整',{exact:true}).count(),0);
  await saved();await work.getByRole('button',{name:'默认配置',exact:true}).click();await manager.getByRole('button',{name:'保存方案',exact:true}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('[data-publishing-profiles] fieldset')?.disabled);await firstHistory(manager,'视频标题');
  assert.equal(await manager.getByLabel('方案正剧与羊同步地址',{exact:true}).isChecked(),true);await manager.getByLabel('方案正剧与羊同步地址',{exact:true}).uncheck();
  await manager.getByRole('button',{name:'保存方案',exact:true}).click();await manager.getByText('方案已保存；已有任务的设置保持原样。',{exact:true}).waitFor();assert.equal((await get(info.task_id,'profiles')).items.find(p=>p.id===profile.id).config.location.sync,false);
  assert.equal((await get(info.other_task_id)).settings.sync_location,false);
  await page.screenshot({path:path.join(out,'address-sync-configuration.png')});await page.keyboard.press('Escape');await manager.waitFor({state:'hidden'});await work.getByText('与配置一致',{exact:true}).waitFor();
  await work.getByLabel('正剧与羊同步地址',{exact:true}).check();await work.getByText('与配置不一致',{exact:true}).waitFor();await saved();
  checked('configuration checkbox persists and seeds new tasks; consistency compares actual latest configuration with muted green/amber badges');
  await work.getByRole('button',{name:'默认配置',exact:true}).click();await manager.getByRole('button',{name:'保存并应用当前任务',exact:true}).click();const apply=page.getByRole('dialog',{name:'应用发布方案',exact:true});await apply.getByText('正剧与羊同步地址',{exact:true}).waitFor();await apply.getByRole('button',{name:'应用并保存当前任务',exact:true}).click();await apply.waitFor({state:'hidden'});assert.equal((await get(info.task_id)).settings.sync_location,false);await work.getByText('与配置一致',{exact:true}).waitFor();
  await work.getByLabel('每个视频的份数',{exact:true}).fill('2');await work.getByText('与配置不一致',{exact:true}).waitFor();await work.getByLabel('每个视频的份数',{exact:true}).fill('1');await work.getByText('与配置一致',{exact:true}).waitFor();await saved();
  await page.setViewportSize({width:1200,height:820});assert.ok(await work.evaluate(e=>e.scrollWidth<=e.clientWidth));await work.locator('main').evaluate(e=>{e.scrollTop=0;});await page.screenshot({path:path.join(out,'sync-and-consistency-1200.png')});
  await page.keyboard.press('Escape');await work.waitFor({state:'hidden'});assert.deepEqual(await get(info.task_id,'execution'),before);assert.deepEqual(errors,[]);
  checked('apply preview includes sync setting, consistency switches immediately with actual edits, 1200px layout and existing execution stay intact');
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({checks,errors,writes,placements,goodColor,badColor,mcp:'read routes mocked; persistence uses actual isolated API; no drafts'},null,2));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png')});fs.writeFileSync(path.join(out,'browser-failure.json'),JSON.stringify({error:e.stack,checks,errors,writes,placements},null,2));throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
