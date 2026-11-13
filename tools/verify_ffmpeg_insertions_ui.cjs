/** Actual built UI with isolated API fixtures; no business service/database access. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require('playwright');
const out=path.resolve(process.argv[2]),fixture=JSON.parse(fs.readFileSync(path.join(out,'ui-fixture.json'),'utf8'));
let task=fixture.task,parameters=fixture.parameters;const errors=[],writes=[];
const root=path.resolve('dist');
const server=http.createServer((req,res)=>{const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname);const file=path.resolve(root,'.'+(name==='/'?'/index.html':name));if(!file.startsWith(root+path.sep))return res.writeHead(403).end();fs.readFile(file,(e,body)=>{if(e)return res.writeHead(404).end();res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');res.end(body);});});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
 browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1050}});
 await context.route('**/api/**',route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;const json=value=>route.fulfill({json:value});
  if(req.method()==='POST'){
   const body=req.postDataJSON();writes.push({path:p,body});
   if(p==='/api/v3/operations-dashboard')return json({schema:'isolated',today:'2026-11-02',latest_date:'2026-11-01',accounts:[],theaters:[],video_accounts:[],video_account_daily:[],video_posts:[],video_post_punishments:[],revenue_account_periods:[],coverage:{account_days:0,failed_account_days:0,failed_revenue_periods:0,unclassified_risks:0}});
  if(p==='/api/v2/engine-parameters'){parameters.midroll_endroll={strategy:body.midroll_endroll,configured:true};return json(parameters);}
   if(p===`/api/v2/production-tasks/${task.id}/insertion-strategy`){task.midroll_endroll_strategy=body.strategy;return json(task);}
   const m=task.materials.find(m=>p===`/api/v2/production-files/${m.id}/insertion-strategy`);
   if(m){m.insertion_strategy=body.strategy;return json(task);}
   throw Error('Unexpected write '+p);
  }
  if(p==='/api/v3/operations-dashboard')return json({schema:'isolated',today:'2026-11-02',latest_date:'2026-11-01',accounts:[],theaters:[],video_accounts:[],video_account_daily:[],video_posts:[],video_post_punishments:[],revenue_account_periods:[],coverage:{account_days:0,failed_account_days:0,failed_revenue_periods:0,unclassified_risks:0}});
  if(p==='/api/v2/engine-parameters')return json(parameters);
  if(p==='/api/v2/production-resources')return json({items:['中插01.mp4','尾插01.mp4'].map((name,i)=>({id:'ad'+i,name,category:'lead_video',categoryName:'引流视频',filePath:'isolated/'+name,status:'available',fileSizeMb:1,durationSeconds:10}))});
  if(p==='/api/v3/template-generation/config')return json(fixture.templateConfig);
  if(p==='/api/v2/production-task-summaries'||p==='/api/v2/production-tasks')return json({items:[task]});
  if(p===`/api/v2/production-tasks/${task.id}/details`)return json(task);
  if(p==='/api/v2/template-library')return json({items:[],directory:'隔离测试',selected_template_id:null,selection_locked:false,selection_lock_reason:''});
  if(p==='/api/v2/task-center')return json({tasks:[],executors:[],dramaPriorities:[],isQueuePaused:false,finalComposition:{jobs:[],paused:false,counts:{running:0,waiting:0,done:0,error:0,cancelled:0}}});
  if(p==='/api/v2/settings')return json({publish_presets:['12:00'],publish_date_offset_days:0});
  if(p==='/api/v2/revenue/source-data')return json({rows:[],accounts:[],theaters:[]});
  return json({items:[],tasks:[],accounts:[],theaters:[],dramas:[],jobs:[],runs:[]});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(12000);
 await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'参数中心',exact:true}).click();
 const section=page.locator('section').filter({has:page.getByRole('heading',{name:'成片插片（中插 / 尾插）',exact:true})});
 await section.getByLabel('不插中插的视频时长门槛').fill('5:00');
 await section.getByLabel('中插位置下限').fill('3:00');await section.getByLabel('中插位置上限').fill('2:00');
 assert.equal(await section.getByRole('button',{name:'保存并生效'}).isDisabled(),true);
 await section.getByLabel('中插位置上限').fill('5:00');await section.getByRole('button',{name:'保存并生效'}).click();
 assert.equal(parameters.midroll_endroll.strategy.midroll.min_source_duration_seconds,300);
 await page.getByText('插片规则已保存，后续新提交的 FFmpeg 成片使用本设置',{exact:true}).first().waitFor({state:'hidden'});
 await section.screenshot({path:path.join(out,'parameters.png')});
 await page.getByRole('button',{name:'生产中心',exact:true}).click();
 const taskButton=page.getByRole('button',{name:'本剧集插片：跟随全局',exact:true});await taskButton.click();
 let dialog=page.getByRole('dialog',{name:'本剧集插片设置'});
 await dialog.getByLabel('本剧集中插规则').selectOption('off');
 await dialog.getByRole('button',{name:'保存',exact:true}).click();
 await page.getByRole('button',{name:'本剧集插片：部分覆盖'}).waitFor();
 assert.deepEqual(task.midroll_endroll_strategy,{midroll:{enabled:false}});
 const clipButton=page.getByRole('button',{name:'隔离演示剧集-1.mp4插片设置',exact:true});await clipButton.click();
 dialog=page.getByRole('dialog',{name:'本素材插片设置'});
 assert.ok((await dialog.innerText()).includes('当前生效：不插入'));
 await dialog.getByLabel('本素材尾插规则').selectOption('off');await dialog.screenshot({path:path.join(out,'material-dialog.png')});
 await dialog.getByRole('button',{name:'保存',exact:true}).click();
 await page.getByText('本片不接尾插',{exact:true}).waitFor();
 assert.deepEqual(task.materials[0].insertion_strategy,{endroll:{enabled:false}});
 assert.equal(await page.getByRole('dialog').count(),0);
 await page.screenshot({path:path.join(out,'production.png'),fullPage:true});
 await page.getByRole('button',{name:'本剧集插片：部分覆盖'}).click();dialog=page.getByRole('dialog',{name:'本剧集插片设置'});
 await dialog.getByLabel('本剧集中插规则').selectOption('on');
 await dialog.getByLabel('中插位置下限').fill('2:30');await dialog.getByLabel('中插位置上限').fill('4:30');
 await dialog.getByLabel('中插取材方式').selectOption('locked');await dialog.getByLabel('中插指定素材').selectOption('中插01.mp4');
 await dialog.screenshot({path:path.join(out,'task-dialog.png')});await dialog.getByRole('button',{name:'保存',exact:true}).click();
 assert.equal(task.midroll_endroll_strategy.midroll.position_start_seconds,150);assert.equal(task.midroll_endroll_strategy.midroll.file,'中插01.mp4');assert.equal(task.midroll_endroll_strategy.endroll,undefined);
 await clipButton.click();dialog=page.getByRole('dialog',{name:'本素材插片设置'});assert.equal(await dialog.getByLabel('本素材尾插规则').inputValue(),'off');
 await dialog.getByRole('button',{name:'恢复跟随剧集'}).click();assert.equal(task.materials[0].insertion_strategy,null);
 await page.getByRole('button',{name:'本剧集插片：部分覆盖'}).click();dialog=page.getByRole('dialog',{name:'本剧集插片设置'});await dialog.getByRole('button',{name:'恢复跟随全局'}).click();
 await taskButton.waitFor();assert.equal(task.midroll_endroll_strategy,null);
 await page.setViewportSize({width:1920,height:1080});await page.screenshot({path:path.join(out,'production-wide.png'),fullPage:true});
 await page.setViewportSize({width:900,height:700});await taskButton.click();dialog=page.getByRole('dialog',{name:'本剧集插片设置'});
 assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth),false);await dialog.screenshot({path:path.join(out,'task-dialog-small.png')});
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 parameters.midroll_endroll.configured=false;
 await taskButton.click();dialog=page.getByRole('dialog',{name:'本剧集插片设置'});
 await dialog.getByText('当前生效：不插入',{exact:true}).first().waitFor();
 assert.equal(await dialog.getByText('当前生效：不插入',{exact:true}).count(),2);
 await dialog.getByRole('button',{name:'取消',exact:true}).click();
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-verification.json'),JSON.stringify({status:'PASS',writes,errors},null,2));console.log(JSON.stringify({status:'PASS',writes:writes.length,errors}));
 }catch(e){console.error('Browser errors:',errors);throw e;}finally{if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
