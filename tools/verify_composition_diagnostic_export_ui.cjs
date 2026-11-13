/** Isolated rendered task center: no real backend, DB, media or Explorer. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {build}=require('esbuild');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(process.argv[2]||'local-test-output/composition-diagnostic-conditions-20261105');
const checks=[],writes=[],errors=[];
const counts={running:1,waiting:2,done:1,error:0,cancelled:0};
const jobs=['running','waiting','waiting','done'].map((status,i)=>({id:String(i+1).repeat(32),task_id:'isolated',material_id:'isolated',template_id:'isolated',status,name:`隔离测试剧集-${i+1}`,account_name:'诊断验证账号',drama_name:'隔离测试剧集',stage:'复用已完成模板，编码成片 · 26558/26898帧',progress:48,elapsed_seconds:172,error:'',output_path:null}));
const snapshot={tasks:[],executors:[],dramaPriorities:[],finalComposition:{jobs,counts,paused:false},templateGeneration:{jobs:[],counts:{...counts,running:0,waiting:0,done:0},paused:false},sceneryProcessing:{jobs:[],counts:{...counts,running:0,waiting:0,done:0},paused:false}};
const exportResult={directory:'D:\\短剧推广运营系统\\诊断输出\\20261105-190000-123456',report_path:'report.md',bundle_path:'logs.zip',attempts:33,summary_attempts:50,selection:{primary_attempts:30,baseline_attempts:3,omitted_detail_attempts:17},files:69,opened:true,warnings:[]};
const catalog={items:Array.from({length:60},(_,i)=>({key:(i+1).toString(16).padStart(64,'0'),name:`隔离诊断任务-${60-i}`,attempt:1,session_id:i<50?'current':'old',started_at:`2026-11-05T10:${String(59-i).padStart(2,'0')}:00`,status:i===0?'running':'done'})),latest_session_id:'current',latest_session_count:50,total:60,read_error_count:0};
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const assets=path.join(out,'dist','assets');
 const css=fs.readdirSync(assets).find(n=>n.endsWith('.css'));
 const entry=`import React,{useState} from 'react';import{createRoot}from'react-dom/client';import{FfmpegTaskCenter}from'./src/components/taskcenter/FfmpegTaskCenter';import{FfmpegQueue}from'./src/components/taskcenter/FfmpegQueue';const snapshot=${JSON.stringify(snapshot)};window.__taskCloseCount=0;function Demo(){const[toast,setToast]=useState('');return <><div role="alert" style={{position:'fixed',bottom:0,zIndex:100,fontSize:14,background:'white'}}>{toast}</div>{location.search.includes('compact')?<FfmpegQueue kind="final" compact snapshot={snapshot.finalComposition} showToast={setToast}/>:<FfmpegTaskCenter snapshot={snapshot} updatedAt={Date.now()} onClose={()=>{window.__taskCloseCount++}} onLegacy={()=>{}} showToast={setToast}/>}</>};createRoot(document.getElementById('root')).render(<Demo/>);`;
 await build({stdin:{contents:entry,resolveDir:process.cwd(),loader:'tsx'},bundle:true,outfile:path.join(out,'harness.js'),format:'iife',define:{'import.meta.env':'{}','process.env.NODE_ENV':'"production"'}});
 fs.writeFileSync(path.join(out,'index.html'),`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><link rel="stylesheet" href="/dist/assets/${css}"><div id="root"></div><script src="/harness.js"></script></html>`);
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost'),file=path.resolve(out,'.'+(url.pathname==='/'?'/index.html':url.pathname));
  if(!file.startsWith(out+path.sep))return res.writeHead(403).end();
  fs.readFile(file,(e,b)=>{if(e)return res.writeHead(404).end();res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');res.end(b);});
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1050}});let release,mode='success',catalogFailure=false,emptyCatalog=false,catalogReads=0;
  await context.route('**/api/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;
   if(pathname==='/api/v3/final-composition/diagnostics/catalog'){
    assert.equal(req.method(),'GET');catalogReads++;
    if(catalogFailure)return route.fulfill({status:400,json:{error:'隔离验证：摘要暂时不可读'}});
    return route.fulfill({json:emptyCatalog?{items:[],latest_session_id:'',latest_session_count:0,total:0,read_error_count:0}:catalog});
   }
   assert.equal(pathname,'/api/v3/final-composition/diagnostics/export');assert.equal(req.method(),'POST');
   const body=req.postDataJSON();writes.push({path:pathname,method:req.method(),body});
   if(mode==='pending')await new Promise(r=>{release=r;});
   if(mode==='failure')return route.fulfill({status:400,json:{error:'隔离验证：诊断输出磁盘不可写'}});
   const primary=emptyCatalog?0:body.scope==='all'?60:body.scope==='selected'?body.attempt_keys.length:Math.min(50,body.limit);
   const baseline=body.include_baseline&&!emptyCatalog?3:0,summary=body.scope==='recent'&&!emptyCatalog?50:primary+baseline;
   const result={...exportResult,attempts:primary+baseline,summary_attempts:summary,selection:{primary_attempts:primary,baseline_attempts:baseline,omitted_detail_attempts:summary-primary-baseline}};
   return route.fulfill({json:mode==='manual'?{...result,opened:false,warnings:['未能自动打开文件夹，请按下方路径手动打开。']}:result});
  });
  const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
  const url=`http://127.0.0.1:${server.address().port}/`;
  const button=()=>page.getByRole('button',{name:'导出合成诊断',exact:true});
  const dialog=()=>page.getByRole('dialog',{name:'导出合成诊断',exact:true});
  const open=async()=>{await button().click();await dialog().getByText(/共有 \d+ 条记录/).waitFor();};
  const choose=async name=>{await dialog().getByRole('radio',{name:new RegExp('^'+name)}).check();};
  const start=()=>dialog().getByRole('button',{name:'开始导出',exact:true});
  await page.goto(url);await button().waitFor();
  for(const [width,height] of [[1440,1050],[1024,768],[1566,1359]]){
   await page.setViewportSize({width,height});const a=await page.getByRole('heading',{name:'成片合成',exact:true}).boundingBox(),b=await button().boundingBox(),c=await page.getByRole('button',{name:'暂停后续成片',exact:true}).boundingBox();
   assert.ok(a.x+a.width<=b.x&&Math.abs(c.x-b.x-b.width-8)<2&&Math.abs(b.y-c.y)<4);
   await open();assert.equal(await dialog().evaluate(e=>e.scrollWidth>e.clientWidth),false);
   assert.equal(await dialog().getByRole('radio',{name:/^最近一轮运行/}).isChecked(),true);
   assert.equal(await dialog().getByRole('spinbutton',{name:'详细日志数量'}).inputValue(),'30');
   assert.equal(await dialog().getByRole('checkbox',{name:/^保留前段同条件/}).isChecked(),true);
   await page.screenshot({path:path.join(out,`conditions-${width}.png`),fullPage:true});
   await dialog().getByRole('button',{name:'取消',exact:true}).click();
  }
  assert.equal(writes.length,0);checks.push('right-side-entry-opens-conditions-no-POST; default-recent30-baseline; three-sizes-no-overflow');
  await open();await page.keyboard.press('Escape');await dialog().waitFor({state:'detached'});assert.equal(await page.evaluate(()=>window.__taskCloseCount),0);assert.equal(writes.length,0);
  checks.push('cancel-and-Escape-only-close-settings-no-export-no-parent-close');
  await open();mode='pending';await start().click();const pending=dialog().getByRole('button',{name:'导出中…',exact:true});await pending.waitFor();assert.equal(await pending.isDisabled(),true);
  await page.keyboard.press('Escape');assert.equal(await dialog().count(),1);assert.equal(await dialog().getByRole('button',{name:'取消',exact:true}).isDisabled(),true);
  assert.equal(await page.evaluate(()=>window.__taskCloseCount),0);assert.equal(writes.length,1);assert.ok(release);
  assert.deepEqual(writes[0].body,{scope:'recent',limit:30,include_baseline:true,session_id:'current'});release();
  await dialog().waitFor({state:'detached'});await page.getByRole('status').filter({hasText:'详细记录 33 条'}).waitFor();assert.ok((await page.getByRole('status').innerText()).includes(exportResult.directory));
  assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'),'48');
  await page.screenshot({path:path.join(out,'export-success.png'),fullPage:true});
  checks.push('confirmed-default-single-POST; pending-disabled-and-Escape-blocked; summary-detail-baseline-count-path-visible');
  mode='success';await open();await dialog().getByRole('spinbutton',{name:'详细日志数量'}).fill('0');assert.equal(await start().isDisabled(),true);await dialog().getByText('请输入1至200的整数。').waitFor();
  await dialog().getByRole('spinbutton',{name:'详细日志数量'}).fill('5');await dialog().getByRole('checkbox',{name:/^保留前段同条件/}).uncheck();await start().click();await dialog().waitFor({state:'detached'});
  assert.deepEqual(writes[1].body,{scope:'recent',limit:5,include_baseline:false,session_id:'current'});checks.push('custom-count-validation-and-baseline-off-reach-export');
  await open();await choose('指定任务');let boxes=dialog().getByRole('checkbox',{name:/^选择隔离诊断任务/});await boxes.first().check();
  await dialog().getByRole('button',{name:'下一页',exact:true}).click();await boxes.first().check();
  await dialog().getByRole('button',{name:'上一页',exact:true}).click();assert.equal(await boxes.first().isChecked(),true);
  await dialog().getByRole('searchbox',{name:'搜索诊断任务'}).fill('隔离诊断任务-3');assert.equal(await boxes.count(),11);
  await page.setViewportSize({width:1024,height:768});await page.screenshot({path:path.join(out,'selected-records-1024.png'),fullPage:true});
  await dialog().getByRole('checkbox',{name:/^保留前段同条件/}).uncheck();await start().click();await dialog().waitFor({state:'detached'});
  assert.deepEqual(writes[2].body,{scope:'selected',limit:30,include_baseline:false,attempt_keys:[catalog.items[0].key,catalog.items[20].key]});
  checks.push('specified-task-pagination-search-keeps-selection; only-explicit-keys-submitted');
  await open();await choose('全部历史');await dialog().getByText('将导出全部 60 条记录及仍保留的详细日志，可能生成较大的压缩包。').waitFor();assert.equal(await dialog().getByRole('checkbox',{name:/^保留前段同条件/}).count(),0);assert.equal(writes.length,3);
  await start().click();await dialog().waitFor({state:'detached'});assert.deepEqual(writes[3].body,{scope:'all',limit:30,include_baseline:false});checks.push('all-history-explicit-selection-and-confirm-only');
  mode='failure';await open();await dialog().getByRole('spinbutton',{name:'详细日志数量'}).fill('7');await start().click();await dialog().getByRole('alert').filter({hasText:'诊断输出磁盘不可写'}).waitFor();assert.equal(await start().isEnabled(),true);assert.equal(await dialog().getByRole('spinbutton',{name:'详细日志数量'}).inputValue(),'7');
  mode='manual';await start().click();await dialog().waitFor({state:'detached'});await page.getByRole('status').filter({hasText:'手动打开'}).waitFor();checks.push('export-failure-retains-conditions-and-retry; Explorer-failure-still-success-with-path');
  mode='success';catalogFailure=true;await button().click();await dialog().getByRole('alert').filter({hasText:'摘要暂时不可读'}).waitFor();assert.equal(await start().isDisabled(),true);const written=writes.length;catalogFailure=false;await dialog().getByRole('button',{name:'重新读取',exact:true}).click();await dialog().getByText(/共有 \d+ 条记录/).waitFor();assert.equal(writes.length,written);
  await dialog().getByRole('button',{name:'取消',exact:true}).click();emptyCatalog=true;await open();assert.equal(await start().isEnabled(),true);await start().click();await dialog().waitFor({state:'detached'});await page.getByRole('status').filter({hasText:'详细记录 0 条'}).waitFor();checks.push('catalog-read-failure-retry-does-not-export; empty-range-explicit-zero-result');
  await page.getByRole('tab',{name:/模板制作/}).click();assert.equal(await button().count(),0);
  await page.getByRole('tab',{name:/风景处理/}).click();assert.equal(await button().count(),0);
  await page.goto(url+'?compact');await page.getByLabel('成片合成队列').waitFor();assert.equal(await button().count(),0);checks.push('no-export-in-template-scenery-compact');
  assert.deepEqual(errors,[]);assert.equal(writes.length,7);
  const result={status:'PASS',checks,writes,catalogReads,errors};fs.writeFileSync(path.join(out,'ui-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
