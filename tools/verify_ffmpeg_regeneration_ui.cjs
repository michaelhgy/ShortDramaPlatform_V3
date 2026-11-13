/** Built UI, all APIs intercepted. No real database, account or publishing access. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(process.argv[2]||'local-test-output/final-regeneration-20261103');
const fixture={"task":{"mount_source":"","mount_external_id":"","id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_id":"isolated-regeneration","created_date":"2026-11-03","account_name":"插片验收账号","drama_name":"隔离演示剧集","planned_publish_at":"2026-11-03T12:00","manual_order":0,"created_at":"2026-11-03T12:00:00","release_status":"unregistered","actual_release_time":"","release_province":"","release_city":"","release_district":"","release_detail_address":"","final_video_manual_check":false,"midroll_endroll_strategy":null,"paths":{"root":"D:/isolated/root","materials":"D:/isolated/materials","template":"D:/isolated/template","finals":"D:/isolated/finals"},"materials":[{"id":"11111111111111111111111111111111","name":"隔离演示剧集-1.mp4","path":"D:/isolated/source0.mp4","sequence_no":1,"size_bytes":7,"duration_seconds":600,"thumbnail_path":"","resolution":"","scanned_at":"2026-11-02T20:28:45","status":"available","insertion_strategy":null},{"id":"22222222222222222222222222222222","name":"隔离演示剧集-2.mp4","path":"D:/isolated/source1.mp4","sequence_no":2,"size_bytes":7,"duration_seconds":600,"thumbnail_path":"","resolution":"","scanned_at":"2026-11-02T20:28:45","status":"available","insertion_strategy":null}],"videos":[],"template":null,"pending_material_count":0,"template_display_status":"not_generated","task_display_status":"awaiting_template"},"parameters":{"template_copy":{"blessing":["愿您身体健康","愿您平安喜乐","愿您福气常伴","愿您万事顺心","愿您幸福安康","祝您笑口常开","愿您每天都开心","愿您日子越过越好","愿您一家幸福美满","祝您日子红红火火"],"drama_prompt":["左下角免费看全集","左下角免费看后续","左下角免费看结局","左下角免费继续看","左下角免费接着看","点免费剧集看全集","点免费剧集看后续","免费剧集接着看","后续请点免费剧集","结局请点免费剧集"],"blessing_default":["愿您身体健康","愿您平安喜乐","愿您福气常伴","愿您万事顺心","愿您幸福安康","祝您笑口常开","愿您每天都开心","愿您日子越过越好","愿您一家幸福美满","祝您日子红红火火"],"drama_prompt_default":["左下角免费看全集","左下角免费看后续","左下角免费看结局","左下角免费继续看","左下角免费接着看","点免费剧集看全集","点免费剧集看后续","免费剧集接着看","后续请点免费剧集","结局请点免费剧集"],"configured":false},"midroll_endroll":{"strategy":{"midroll":{"enabled":true,"mode":"latest","file":"","min_source_duration_seconds":300,"position_start_seconds":180,"position_end_seconds":300},"endroll":{"enabled":true,"mode":"latest","file":""}},"configured":true}},"templateConfig":{"config":{"width":1080,"height":2400,"fps":30,"duration_seconds":600,"duration_jitter":30,"template_usage_limit":20,"scenery_count":6,"scenery_count_jitter":0,"scenery_usage_limit":5,"scenery_group_gap_percent":[15,70],"height_large_percent":[28,33],"height_small_percent":[20,25],"mask_percent":[40,55],"feather_percent":[55,80],"sticker_alpha_percent":80,"overlay_sticker_enabled":false,"overlay_sticker_count":[24,48],"overlay_sticker_opacity_percent":2,"photo_layer_enabled":false,"photo_layer_count":[6,6],"photo_layer_opacity_percent":2,"photo_usage_limit":5,"effect_count":[3,5],"effect_segment_seconds":[30,60],"effect_strength_percent":[90,100],"effect_pair_percent":[15,30],"effect_transition_seconds":[1,2],"border_width":[5,10]},"limits":{"template_usage_limit":[1,1000],"duration_seconds":[10,1800],"duration_jitter":[0,300],"scenery_count":[4,30],"scenery_count_jitter":[0,10],"scenery_usage_limit":[1,1000],"scenery_group_gap_percent":[1,95],"height_large_percent":[28,33],"height_small_percent":[20,25],"mask_percent":[40,55],"feather_percent":[55,80],"sticker_alpha_percent":[1,80],"effect_count":[1,23],"overlay_sticker_count":[1,64],"overlay_sticker_opacity_percent":[1,100],"photo_layer_count":[1,30],"photo_layer_opacity_percent":[1,100],"photo_usage_limit":[1,1000],"effect_segment_seconds":[10,180],"effect_strength_percent":[1,100],"effect_pair_percent":[0,30],"effect_transition_seconds":[1,2],"border_width":[5,10]},"profile":"isolated","library":{"effects":0,"borders":0}}};
const errors=[],writes=[],checks=[];
let task,fail=false;
function reset(statuses=['video_exported','video_error','cancelled','video_queued']){
 task=structuredClone(fixture.task);task.task_display_status='video_exported';
 task.materials=Array.from({length:4},(_,i)=>({...task.materials[0],id:String(i+1).repeat(32),name:`隔离演示剧集-${i+1}.mp4`,sequence_no:i+1}));
 task.videos=statuses.map((status,i)=>({id:String(i+5).repeat(32),source_material_id:task.materials[i].id,engine:'ffmpeg',status:`ffmpeg_${{video_exported:'done',video_error:'error',cancelled:'cancelled',video_queued:'waiting',video_exporting:'running'}[status]}`,display_status:status,sequence_no:i+1,name:task.materials[i].name,original_name:task.materials[i].name,size_bytes:1024,output_exists:status==='video_exported',output_path:status==='video_exported'?`D:/isolated/隔离演示剧集-${i+1}.mp4`:'',output_size_bytes:1024,source_duration_seconds:600,output_duration_seconds:600}));
}
reset();
const dashboard={schema:'isolated',today:'2026-11-03',latest_date:'2026-11-02',accounts:[],theaters:[],video_accounts:[],video_account_daily:[],video_posts:[],video_post_punishments:[],revenue_account_periods:[],coverage:{account_days:0,failed_account_days:0,failed_revenue_periods:0,unclassified_risks:0}};
const root=path.resolve('dist');
const server=http.createServer((req,res)=>{const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));if(!file.startsWith(root+path.sep))return res.writeHead(403).end();fs.readFile(file,(e,b)=>{if(e)return res.writeHead(404).end();res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');res.end(b);});});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1050}});
  await context.route('**/api/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname,json=value=>route.fulfill({json:value});
   if(req.method()==='POST'){
    if(p==='/api/v3/operations-dashboard')return json(dashboard);
    writes.push({path:p,body:req.postDataJSON()});
    if(p==='/api/v3/final-composition/regenerate'||/\/jobs\/[a-f0-9]+\/regenerate$/.test(p)){
     await new Promise(r=>setTimeout(r,350));
     if(fail)return route.fulfill({status:400,json:{error:'隔离验证：缺少中插素材，本次未提交任何任务'}});
     const selected=p.endsWith('/final-composition/regenerate')?task.videos:task.videos.filter(v=>p.includes(v.id));
     selected.forEach(v=>{v.status='ffmpeg_waiting';v.display_status='video_queued';});
     return json({regenerated_count:selected.length});
    }
    throw Error('Unexpected write '+p);
   }
   if(p==='/api/v3/operations-dashboard')return json(dashboard);
   if(p==='/api/v2/engine-parameters')return json(fixture.parameters);
   if(p==='/api/v3/template-generation/config')return json(fixture.templateConfig);
   if(p==='/api/v2/production-task-summaries'||p==='/api/v2/production-tasks')return json({items:[task]});
   if(p===`/api/v2/production-tasks/${task.id}/details`)return json(task);
   if(p==='/api/v2/template-library')return json({items:[],directory:'隔离测试',selected_template_id:null,selection_locked:false,selection_lock_reason:''});
   if(p==='/api/v2/task-center')return json({tasks:[],executors:[],dramaPriorities:[],isQueuePaused:false,finalComposition:{jobs:[],paused:false,counts:{running:0,waiting:0,done:0,error:0,cancelled:0}}});
   if(p==='/api/v2/settings')return json({publish_presets:['12:00'],publish_date_offset_days:0});
   if(p==='/api/v2/revenue/source-data')return json({rows:[],accounts:[],theaters:[]});
   if(p.includes('/media'))return route.fulfill({status:404,body:'isolated: no video'});
   if(p.includes('/thumbnail'))return route.fulfill({status:404,body:'isolated: no thumbnail'});
   return json({items:[],tasks:[],accounts:[],theaters:[],dramas:[],jobs:[],runs:[]});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(12000);
  const open=async()=>{await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByRole('button',{name:'全部成品重新生成',exact:true}).waitFor();};
  await open();
  const all=page.getByRole('button',{name:'全部成品重新生成',exact:true});
  const singles=()=>page.getByRole('button',{name:/隔离演示剧集-\d\.mp4重新生成/});
  assert.equal(await singles().count(),3);
  const a=await all.boundingBox(),b=await page.getByRole('button',{name:'批量合成',exact:true}).boundingBox();assert.ok(a.x+a.width<=b.x+1&&Math.abs(a.y-b.y)<3);
  checks.push('completed-failed-cancelled-use-existing-icon; waiting-has-no-single-regeneration; batch-button-left-of-compose');
  await page.screenshot({path:path.join(out,'production.png'),fullPage:true});
  await all.click();let dialog=page.getByRole('dialog',{name:'全部成品重新生成',exact:true});await dialog.waitFor();
  assert.ok((await dialog.innerText()).includes('4 条成品'));
  assert.ok((await dialog.innerText()).includes('全局 → 本剧集 → 本素材'));
  assert.ok((await dialog.innerText()).includes('确认后立即删除'));
  assert.equal(writes.length,0);await dialog.getByRole('button',{name:'取消',exact:true}).click();assert.equal(writes.length,0);
  await all.click();await page.keyboard.press('Escape');assert.equal(await dialog.count(),0);assert.equal(writes.length,0);
  checks.push('batch-confirmation-explains-current-rules-scope-immediate-deletion-and-publishing; cancel-and-Escape-never-submit');
  for(const index of [1,2,3]){
   const button=page.getByRole('button',{name:`隔离演示剧集-${index}.mp4重新生成`,exact:true});await button.click();
   await page.waitForResponse(r=>r.url().includes(`/jobs/${String(index+4).repeat(32)}/regenerate`)&&r.request().method()==='POST');
   await button.waitFor({state:'detached'});
  }
  assert.equal(writes.length,3);assert.ok(writes.every(w=>w.path.endsWith('/regenerate')));checks.push('each-single-status-submits-regeneration-not-old-retry; refreshed-record-disables-repeat');
  await all.click();await dialog.getByRole('button',{name:'确认全部重新生成',exact:true}).click();
  await dialog.getByRole('button',{name:'提交中…',exact:true}).waitFor();assert.equal(await dialog.getByRole('button',{name:'提交中…',exact:true}).isDisabled(),true);
  await dialog.waitFor({state:'detached'});assert.equal(writes.length,4);assert.deepEqual(writes[3].body,{task_id:task.id});checks.push('batch-confirm-only-one-request-and-submit-disabled-while-pending');
  reset();fail=true;await open();await all.click();await dialog.getByRole('button',{name:'确认全部重新生成',exact:true}).click();
  await page.getByText('隔离验证：缺少中插素材，本次未提交任何任务',{exact:true}).first().waitFor();assert.equal(await dialog.count(),1);assert.equal(await dialog.getByRole('button',{name:'确认全部重新生成',exact:true}).isEnabled(),true);checks.push('API-failure-keeps-confirm-dialog-and-allows-correction');
  await dialog.getByRole('button',{name:'取消',exact:true}).click();fail=false;
  reset(['video_exporting','video_error','cancelled','video_queued']);await open();const count=writes.length;await all.click();
  assert.equal(await dialog.getByRole('button',{name:'确认全部重新生成',exact:true}).isDisabled(),true);await dialog.getByRole('alert').waitFor();assert.equal(writes.length,count);checks.push('running-job-blocks-batch-with-pause-and-wait-guidance');
  await dialog.getByRole('button',{name:'取消',exact:true}).click();reset();await open();
  await page.setViewportSize({width:1920,height:1080});await page.screenshot({path:path.join(out,'production-wide.png'),fullPage:true});
  await page.setViewportSize({width:900,height:700});await all.click();await dialog.waitFor();assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth),false);await dialog.screenshot({path:path.join(out,'confirmation-small.png')});
  await dialog.getByRole('button',{name:'取消',exact:true}).click();await page.setViewportSize({width:1440,height:1050});await all.click();await dialog.screenshot({path:path.join(out,'confirmation.png')});
  checks.push('1440-1920-page-and-900x700-dialog-no-horizontal-overflow');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-verification.json'),JSON.stringify({status:'PASS',checks,writes,errors},null,2));console.log(JSON.stringify({status:'PASS',checks,writes:writes.length,errors},null,2));
 }finally{if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
