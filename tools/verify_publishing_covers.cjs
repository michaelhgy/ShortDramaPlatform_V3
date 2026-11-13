const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(process.env.V3_PUBLISH_PROBE_OUTPUT||'artifacts/publishing-cover-options/20261105/probe');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const profileName='封面三项实测 '+Date.now();
const checks=[],errors=[];const checked=text=>{checks.push(text);console.log(text)};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1050},timezoneId:'Asia/Shanghai'});
 await context.route('**/api/**',async route=>{
  const r=route.request(),url=new URL(r.url());
  if(/\/(publish|drafts|check|release|cleanup|batches)$/.test(url.pathname)&&r.method()!=='GET')throw Error('External publication forbidden in UI check');
  if(url.pathname.endsWith('/connection'))return route.fulfill({json:{message:'隔离测试连接'}});
  if(url.pathname.endsWith('/dramas'))return route.fulfill({json:{items:[],binding:null,status:'not_found',queries:[],message:'隔离测试挂载'}});
  if(r.method()==='GET'&&['/api/v2/production-tasks','/api/v2/production-task-summaries'].includes(url.pathname)){
   const response=await route.fetch(),body=await response.json();body.items=body.items.filter(t=>t.id===info.task_id);return route.fulfill({json:body});
  }
  return route.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 const api=(action='')=>`${info.url}/api/v2/publishing/tasks/${info.task_id}${action?'/'+action:''}`;
 const read=async()=>{const r=await context.request.get(api());assert.ok(r.ok());return r.json()};
 async function save(work){await work.getByRole('button',{name:'保存设置',exact:true}).click();await work.getByText('发布设置已保存。',{exact:true}).waitFor()}
 async function open(){await page.getByRole('button',{name:'自动发布',exact:true}).click();const work=page.getByRole('dialog',{name:'发布工作台',exact:true});await work.getByLabel('本组使用封面',{exact:true}).waitFor();await work.getByText('隔离测试挂载',{exact:true}).waitFor();return work}
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();let work=await open();
  await work.getByLabel('本组使用封面',{exact:true}).uncheck();await save(work);
  assert.equal((await read()).settings.groups[0].cover_mode,'none');
  await work.getByLabel('关闭发布工作台',{exact:true}).click();work=await open();assert.equal(await work.getByLabel('本组使用封面',{exact:true}).isChecked(),false);checked('取消使用封面，真实保存及关闭重开均保持关闭');
  await work.getByLabel('本组使用封面',{exact:true}).check();
  const source=path.join(out,'temporary-selected-cover.png');fs.copyFileSync('D:/ShortDramaVideoCollector/experiments/vcat_20261026/probe-cover.png',source);
  const chooser=page.waitForEvent('filechooser');await work.getByLabel('本组替换封面',{exact:true}).click();await (await chooser).setFiles(source);
  await work.getByText('自定义图片已保存',{exact:true}).waitFor();await save(work);
  let data=await read(),group=data.settings.groups[0],imageId=group.custom_cover_id;assert.equal(group.cover_mode,'custom');assert.equal(imageId.length,64);
  fs.unlinkSync(source);
  const image=await context.request.get(`${info.url}/api/v2/publishing/covers/${imageId}.jpg`);assert.equal(image.status(),200);assert.match(image.headers()['content-type'],/image\/jpeg/);
  checked('点击封面打开文件选择，保存自定义图片；删除原选图后托管图片仍可读');
  await work.getByLabel('本组使用自带',{exact:true}).check();await save(work);assert.equal((await read()).settings.groups[0].cover_mode,'auto');
  await work.getByLabel('本组使用自定义',{exact:true}).check();await save(work);assert.equal((await read()).settings.groups[0].custom_cover_id,imageId);
  await work.getByLabel('本组使用封面',{exact:true}).uncheck();await save(work);await work.getByLabel('关闭发布工作台',{exact:true}).click();work=await open();
  assert.equal(await work.getByLabel('本组使用封面',{exact:true}).isChecked(),false);await work.getByLabel('本组使用封面',{exact:true}).check();assert.equal(await work.getByLabel('本组使用自定义',{exact:true}).isChecked(),true);await save(work);
  checked('使用自带与使用自定义可切换；关闭总开关后重开仍记住图片和来源');
  await work.getByRole('button',{name:'默认配置',exact:true}).click();const manager=page.getByRole('dialog',{name:'自动发布默认配置',exact:true});
  await manager.getByRole('button',{name:'新建方案',exact:true}).click();await manager.getByLabel('方案名称',{exact:true}).fill(profileName);
  await manager.getByLabel('方案正剧使用封面',{exact:true}).uncheck();
  await manager.getByLabel('方案羊选择封面图片',{exact:true}).setInputFiles({name:'custom.png',mimeType:'image/png',buffer:fs.readFileSync('D:/ShortDramaVideoCollector/experiments/vcat_20261026/probe-cover-sheep.png')});
  await manager.getByText('自定义图片已保存',{exact:true}).waitFor();
  await manager.getByRole('button',{name:'保存方案',exact:true}).click();await manager.getByText('方案已保存；已有任务的设置保持原样。',{exact:true}).waitFor();
  data=await read();const profile=data.profile_library.items.find(p=>p.name===profileName);assert.ok(profile);assert.equal(profile.config.groups.normal.cover_mode,'none');assert.equal(profile.config.groups.sheep.cover_mode,'custom');assert.notEqual(profile.config.groups.sheep.custom_cover_id,imageId);
  await manager.screenshot({path:path.join(out,'profile-cover-settings.png')});
  await manager.getByLabel('关闭默认配置',{exact:true}).click();await work.getByRole('button',{name:'默认配置',exact:true}).click();
  await manager.getByRole('button',{name:new RegExp(profileName)}).click();assert.equal(await manager.getByLabel('方案正剧使用封面',{exact:true}).isChecked(),false);assert.equal(await manager.getByLabel('方案羊使用自定义',{exact:true}).isChecked(),true);
  checked('默认配置正剧关闭、羊使用独立自定义图，保存及重开保持一致');
  await manager.getByRole('button',{name:'保存并应用当前任务',exact:true}).click();
  const apply=page.getByRole('dialog',{name:/应用发布方案/});await apply.waitFor();await apply.getByRole('button',{name:'应用并保存当前任务',exact:true}).click();await work.getByText('方案已应用并保存到当前任务。',{exact:true}).waitFor();
  data=await read();assert.equal(data.settings.groups.find(g=>g.kind==='normal').cover_mode,'none');assert.equal(data.settings.groups.find(g=>g.kind==='sheep').custom_cover_id,profile.config.groups.sheep.custom_cover_id);checked('配置应用实际保存，两个分组封面正确且互不串用');
  await work.screenshot({path:path.join(out,'workbench-cover-settings.png')});
  await page.setViewportSize({width:1280,height:720});await work.getByLabel('本组替换封面',{exact:true}).scrollIntoViewIfNeeded();
  let bounds=await work.boundingBox();assert.ok(bounds.x>=0 && bounds.x+bounds.width<=1280);await work.screenshot({path:path.join(out,'workbench-cover-1280.png')});
  await work.getByRole('button',{name:'默认配置',exact:true}).click();await manager.getByLabel('方案正剧使用封面',{exact:true}).scrollIntoViewIfNeeded();bounds=await manager.boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=1280);await manager.screenshot({path:path.join(out,'profile-cover-1280.png')});
  checked('1280×720界面封面与配置控件保持可操作，弹窗未越界');assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'cover-ui-results.json'),JSON.stringify({checks,errors},null,2));
 }catch(e){await page.screenshot({path:path.join(out,'cover-ui-failure.png')});fs.writeFileSync(path.join(out,'cover-ui-failure.txt'),String(e)+'\n'+await page.locator('body').innerText());throw e}
 finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
