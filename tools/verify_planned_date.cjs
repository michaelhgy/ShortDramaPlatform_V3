/** Date-only planning, legacy display, duration layout and independent publishing time. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-planned-date-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];
function checked(text){checks.push(text);console.log(text);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 await context.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()!=='GET'){
   writes.push({path:url.pathname,data:request.postDataJSON()});
   if(/\/drafts$|\/release(?:\/|$)|\/cleanup(?:\/|$)|\/batches$/.test(url.pathname))throw Error('Execution forbidden in planning verification');
  }
  return route.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();
  const header=page.getByTestId('production-task-header');await header.getByText('2分05秒',{exact:true}).waitFor();
  const headerText=await header.innerText();assert.match(headerText,/计划发布日期：/);assert.match(headerText,/2026-10-26/);assert.doesNotMatch(headerText,/08:00|计划发布时间|逾期未完成/);
  const date=header.getByText('2026-10-26',{exact:true});const duration=header.getByTestId('task-generation-duration');
  const d=await date.boundingBox(),g=await duration.boundingBox();assert.ok(g.y>d.y&&Math.abs(g.x-(d.x-100))<150);
  await header.screenshot({path:path.join(out,'date-and-duration-header.png')});
  checked('legacy 08:00 plan shows calendar date only, is not overdue today, duration is beneath date');
  const api=`${info.url}/api/v2/publishing/tasks/${info.task_id}`;
  let response=await page.request.get(api);let saved=await response.json();
  assert.equal(saved.planned_time,'2026-10-26');assert.equal(saved.settings.schedule.schedule_type,'now');
  await page.getByRole('button',{name:'自动发布',exact:true}).click();const publishing=page.getByRole('dialog',{name:'发布工作台',exact:true});
  await publishing.getByText(/名称一致或仅符号差异，已自动关联。|已复用原关联，当前账号可挂载。/).waitFor({timeout:100000});
  await publishing.getByLabel('时间方式',{exact:true}).selectOption('timing');
  await publishing.getByLabel('整批开始日期和时间',{exact:true}).fill('2026-10-27T19:37');
  await publishing.getByRole('button',{name:'保存设置',exact:true}).click();await publishing.getByText('发布设置已保存。',{exact:true}).waitFor();
  saved=await(await page.request.get(api)).json();assert.equal(saved.settings.schedule.start_time,'2026-10-27 19:37');
  await page.keyboard.press('Escape');await publishing.waitFor({state:'detached'});
  checked('actual automatic-publishing start keeps 19:37 and is independent of calendar planning');
  await page.getByRole('button',{name:'安排今天',exact:true}).click();
  const schedule=page.getByRole('dialog',{name:'安排制作任务',exact:true});await schedule.waitFor();
  await schedule.getByRole('button',{name:/一只羊13652/}).click();
  await schedule.getByRole('button',{name:/日期新建验证剧/}).click();
  const planInput=schedule.getByLabel('计划发布日期',{exact:true});await planInput.waitFor();
  assert.equal(await planInput.isDisabled(),true);assert.equal(await schedule.locator('input[type="time"]').count(),0);
  assert.equal(await schedule.getByText(/错峰|黄金档/).count(),0);
  await schedule.getByRole('checkbox',{name:/暂不设置计划发布日期/}).uncheck();
  await planInput.fill('2026-10-27');
  await page.screenshot({path:path.join(out,'date-only-new-task.png')});
  const created=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/v2/production-tasks');
  await schedule.getByRole('button',{name:/保存并加入今日安排/}).click();
  response=await created;assert.equal(response.ok(),true);const task=await response.json();assert.equal(task.planned_publish_at,'2026-10-27');
  assert.equal(writes.find(w=>w.path==='/api/v2/production-tasks').data.planned_publish_at,'2026-10-27');
  checked('new-task drawer has date-only control and sends/stores YYYY-MM-DD with no hidden time');
  await page.getByRole('button',{name:'生产中心',exact:true}).click();
  await page.setViewportSize({width:1200,height:820});
  await header.getByText('2分05秒',{exact:true}).waitFor();
  const narrowDate=await header.getByText('2026-10-26',{exact:true}).boundingBox(),narrowDuration=await duration.boundingBox();assert.ok(narrowDuration.y>narrowDate.y);
  await header.screenshot({path:path.join(out,'date-and-duration-1200.png')});
  checked('date/duration stay vertically arranged after creating another plan and at 1200 width');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'PASS',checks,errors,writes,createdTaskId:task.id},null,2));
 }catch(error){await page.screenshot({path:path.join(out,'ui-failure.png')});fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'FAIL',checks,errors,writes,error:String(error)},null,2));throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
