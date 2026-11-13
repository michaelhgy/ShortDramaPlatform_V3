/** Isolated static UI verification: every API request is fulfilled with fixtures. */
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const out = path.resolve(process.argv[2]), root = path.join(out, 'dist');
const ids = ['a'.repeat(32),'b'.repeat(32),'c'.repeat(32),'d'.repeat(32)];
const makeTask = (id, name, date, completed=false) => ({id,source_id:id,account_id:'account',account_name:'电话号行不行158',drama_name:name,
 created_date:'2026-11-05',created_at:'2026-11-05T12:00:00',updated_at:'2026-11-05T12:00:00',planned_publish_at:date,
 release_status:completed?'registered':'unregistered',actual_release_time:completed?'2026-11-05 19:57:36':'',cleanup_status:'active',
 task_display_status:completed?'released':'awaiting_release',template_display_status:'video_ready',template:null,pending_material_count:0,
 materials_count:1,exported_count:1,draft_count:1,paths:{root:'fixture',materials:'fixture/materials',template:'fixture/template',finals:'fixture/finals'},
 materials:[],videos:[{id:'v-'+id,source_material_id:'m-'+id,engine:'ffmpeg',status:'ffmpeg_done',display_status:'video_exported',sequence_no:1,
 name:name+'-1.mp4',size_bytes:1024,output_exists:true,output_path:'fixture/'+name+'-1.mp4',output_size_bytes:1024,output_duration_seconds:15}]
});
let tasks=[makeTask(ids[0],'待发布测试','2026-11-06'),makeTask(ids[1],'异常测试','2026-11-05'),makeTask(ids[2],'灵泉在手，荒田我有','2026-11-05',true),makeTask(ids[3],'八零春风拂芳华','2026-11-05',true)];
tasks[1].task_display_status='action_required';tasks[1].videos[0].display_status='video_error';tasks[1].videos[0].error_message='测试错误，只在原有详情查看';
const copy=(task,index,mode='timing')=>({key:'g:'+task.videos[0].id+':'+index,video_id:task.videos[0].id,name:task.videos[0].name,
 group_name:'正剧视频',copy:index+1,time:'2026-11-07 19:30',status:'success',error:'',submitted:true,delivery_confirmed:true,local_id:'local-'+task.id+'-'+index,
 schedule_type:mode,submitted_at:'2026-11-05T19:57:36+08:00',mount:{enabled:false,source:'',name:''},location:{name:'',full_address:''}});
const progress=task=>({task_id:task.id,publication:{state:'success',running:false,error:'',items:task.release_status==='registered'?Array.from({length:task.id===ids[2]?75:90},(_,i)=>copy(task,i)):[]},drafts:{state:'idle',running:false,error:'',items:[]},needs_poll:false,refresh_error:''});
const queue={jobs:[],paused:false,auto_enabled:false,counts:{waiting:0,running:0,done:0,error:0,cancelled:0}};
const server=http.createServer((req,res)=>{
 const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname), file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 fs.readFile(file,(err,body)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');res.end(body);});
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;const checks=[],errors=[],writes=[],progressReads=[];
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1540,height:1100},timezoneId:'Asia/Shanghai'});
  await context.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;
   if(!['GET','HEAD'].includes(request.method())){writes.push(request.method()+' '+p);await route.abort();return;}
   if(p==='/api/v3/operations-dashboard'){await route.fulfill({status:503,json:{error:'Dashboard excluded from isolated production test'}});return;}
   let result={items:[]};
   if(p==='/api/v2/settings')result={publish_presets:['12:00'],publish_date_offset_days:0};
   else if(p==='/api/v2/task-center')result={tasks:[],executors:[],dramaPriorities:[],isQueuePaused:false,finalComposition:queue,templateGeneration:queue,sceneryProcessing:queue};
   else if(p==='/api/v2/revenue/source-data')result={rows:[],accounts:[],theaters:[]};
   else if(p==='/api/v2/production-tasks'||p==='/api/v2/production-task-summaries')result={items:tasks};
   else if(/^\/api\/v2\/production-tasks\/[a-f0-9]+(?:\/details)?$/.test(p))result=tasks.find(t=>p.includes(t.id));
   else if(p==='/api/v2/publishing/progress-index')result={items:Object.fromEntries(tasks.filter(t=>t.release_status==='registered').map(t=>[t.id,{total:t.id===ids[2]?75:90,done:t.id===ids[2]?75:90,delivered:t.id===ids[2]?75:90,processing:0,queued:0,paused:0,issues:0,draft_only:false,scheduled:true}]))};
   else if(/\/publishing\/tasks\/.*\/progress$/.test(p)){const t=tasks.find(t=>p.includes(t.id));progressReads.push(t?.id);if(t)result=progress(t);}
   else if(p==='/api/v2/template-library')result={items:[],selected_template_id:null};
   await route.fulfill({json:result||{}});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.stack||e.message));
  const cards=page.getByTestId('production-task-card');
  const visibleIds=()=>cards.evaluateAll(elements=>elements.map(e=>e.dataset.productionTask));
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.getByRole('button',{name:'生产中心',exact:true}).click();await cards.first().waitFor();
  const normal=page.getByRole('group',{name:'进行中的剧集筛选',exact:true}),done=page.getByRole('group',{name:'已完成剧集筛选',exact:true});
  assert.equal(await normal.getByRole('button').count(),3);assert.equal(await done.getByRole('button').count(),1);
  assert.match(await normal.innerText(),/全部 \(2\)/);assert.match(await done.innerText(),/已完成 \(2\)/);
  assert.deepEqual(new Set(await visibleIds()),new Set(ids.slice(0,2)));checks.push('default all excludes completed cards; existing four buttons form two groups');
  assert.equal(await cards.getByText('模板处理中',{exact:true}).count(),0);assert.equal(await cards.getByText('模板异常',{exact:true}).count(),0);
  assert.equal(await cards.getByText('待处理异常',{exact:true}).count(),1);checks.push('one compact exception badge; no template stage badges');
  await page.getByTestId('production-stage-filters').screenshot({path:path.join(out,'stage-filters.png')});
  await normal.getByRole('button',{name:'逾期 (1)',exact:true}).click();await page.waitForFunction(id=>document.querySelectorAll('[data-production-task]').length===1&&document.querySelector('[data-production-task]').dataset.productionTask===id,ids[1]);checks.push('overdue excludes completed past-date tasks');
  await normal.getByRole('button',{name:'未完成 (2)',exact:true}).click();assert.equal(await cards.count(),2);
  await done.getByRole('button',{name:'已完成 (2)',exact:true}).click();await cards.first().waitFor();assert.deepEqual(new Set(await visibleIds()),new Set(ids.slice(2)));
  await cards.first().click();await page.getByTestId('production-video-publishing').first().waitFor();assert.equal(await cards.getByText('官方已定时',{exact:true}).count(),2);assert.equal(await cards.getByText('逾期',{exact:true}).count(),0);
  assert.match(await page.getByTestId('production-video-publishing').first().innerText(),/官方已定时 75\/75 份/);
  await page.getByTestId('production-video-publishing').first().locator('summary').click();assert.equal(await page.getByTestId('production-copy-detail').count(),75);assert.match(await page.getByTestId('production-copy-detail').first().innerText(),/官方已定时/);checks.push('completed card and expandable per-copy detail consistently show official schedule acceptance');
  await page.getByTestId('production-video-publishing').first().locator('summary').click();await page.screenshot({path:path.join(out,'completed-wide.png'),fullPage:true});
  tasks=tasks.filter(t=>t.id!==ids[3]);await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='已完成 (1)'),{timeout:10000});
  assert.deepEqual(await visibleIds(),[ids[2]]);checks.push('a cleaned task disappears from completed without a historical archive');
  await normal.getByRole('button',{name:'全部 (2)',exact:true}).click();tasks[0].release_status='registered';tasks[0].task_display_status='released';
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='全部 (1)'),{timeout:10000});
  assert.deepEqual(await visibleIds(),[ids[1]]);assert.match(await page.getByTestId('production-task-header').innerText(),/异常测试/);checks.push('completion removes the selected card from normal list and selects the next visible task');
  await page.setViewportSize({width:430,height:1000});await page.getByTestId('production-stage-filters').screenshot({path:path.join(out,'stage-filters-narrow.png')});
  const bounds=await page.getByTestId('production-stage-filters').boundingBox();assert.ok(bounds.width<430);checks.push('four filters remain compact on a narrow viewport');
  tasks.find(t=>t.id===ids[1]).release_status='registered';
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='全部 (0)'),{timeout:10000});
  assert.equal(await cards.count(),0);assert.equal(await page.getByTestId('production-task-header').count(),0);
  await page.waitForTimeout(500);const settled=progressReads.length;await page.waitForTimeout(3500);assert.equal(progressReads.length,settled);
  checks.push('an empty normal group keeps hidden completed details closed across summary refreshes');
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({checks,errors,writes},null,2));console.log(JSON.stringify({checks,errors,writes},null,2));
 }catch(error){fs.writeFileSync(path.join(out,'ui-failure.json'),JSON.stringify({message:error.message,stack:error.stack,checks,errors,writes},null,2));throw error;}
 finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
