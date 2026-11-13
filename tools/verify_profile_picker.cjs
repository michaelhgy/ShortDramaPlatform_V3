/** Compact native select and direct configuration reapply, built UI/isolated API. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-profile-picker-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1540,height:1000}}),page=await context.newPage(),errors=[],checks=[];
 const root=`${info.url}/api/v2/publishing/tasks/${info.task_id}`;
 async function get(){return(await context.request.get(root)).json();}
 async function post(action,data){const r=await context.request.post(root+'/'+action,{data});assert.ok(r.ok(),await r.text());return r.json();}
 const initial=await post('profile-preview',{id:'builtin-daily'});await post('settings',initial.settings);
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByRole('button',{name:'自动发布',exact:true}).click();
  const work=page.getByRole('dialog',{name:'发布工作台',exact:true}),picker=work.getByLabel('当前发布方案',{exact:true}),apply=page.getByRole('dialog',{name:'应用发布方案',exact:true});
  await work.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor();await work.getByText('与配置一致',{exact:true}).waitFor();
  const width=await picker.evaluate(e=>e.getBoundingClientRect().width);assert.ok(width<140,`short options width ${width}`);await page.screenshot({path:path.join(out,'compact-picker.png')});checks.push('short-option select uses compact intrinsic width instead of fixed 176px');
  await work.getByLabel('每个视频的份数',{exact:true}).fill('2');const mismatch=work.getByRole('button',{name:'与配置不一致',exact:true});await mismatch.click();await apply.getByText('正剧 · 每视频份数',{exact:true}).waitFor();
  assert.equal((await get()).settings.groups[0].copies,1);await page.keyboard.press('Escape');await apply.waitFor({state:'hidden'});assert.equal(await work.getByLabel('每个视频的份数',{exact:true}).inputValue(),'2');checks.push('mismatch text opens current-profile preview directly; cancel preserves unsaved task values');
  await mismatch.focus();await page.keyboard.press('Enter');await apply.getByText('正剧 · 每视频份数',{exact:true}).waitFor();await page.screenshot({path:path.join(out,'direct-profile-preview.png')});await apply.getByRole('button',{name:'应用并保存当前任务',exact:true}).click();await apply.waitFor({state:'hidden'});await work.getByText('与配置一致',{exact:true}).waitFor();assert.equal(await work.getByLabel('每个视频的份数',{exact:true}).inputValue(),'1');checks.push('keyboard activation opens same preview; confirmed application restores profile values and green state');
  const config=(await get()).profile_library.items[0].config;await post('profile-save',{name:'账号专用定时发布方案',config});
  await work.getByRole('button',{name:'默认配置',exact:true}).click();const manager=page.getByRole('dialog',{name:'自动发布默认配置',exact:true});await manager.getByRole('button',{name:'账号专用定时发布方案',exact:true}).waitFor();await manager.getByRole('button',{name:'关闭默认配置',exact:true}).click();await manager.waitFor({state:'hidden'});
  const measured=await picker.evaluate(e=>{const s=getComputedStyle(e),c=document.createElement('canvas').getContext('2d');c.font=s.font;return{width:e.getBoundingClientRect().width,text:Math.max(...[...e.options].map(o=>c.measureText(o.text).width))};});assert.ok(measured.width>width+30);assert.ok(measured.width>=measured.text+20);assert.ok(measured.width<measured.text+70);
  await picker.selectOption('builtin-daily');await apply.waitFor();await page.keyboard.press('Escape');assert.equal(await picker.evaluate(e=>e.getBoundingClientRect().width),measured.width);checks.push('adding a longer option expands width enough for its text; choosing a shorter one preserves longest-option minimum');
  await page.setViewportSize({width:1200,height:820});assert.ok(await work.evaluate(e=>e.scrollWidth<=e.clientWidth));assert.deepEqual(errors,[]);await page.screenshot({path:path.join(out,'picker-1200.png')});
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({checks,errors,width,longer:measured,realMcp:false,realPublish:false},null,2));console.log(JSON.stringify({checks,errors,width,longer:measured}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png')});throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
