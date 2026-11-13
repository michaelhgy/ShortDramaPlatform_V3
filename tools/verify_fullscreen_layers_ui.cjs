/** Formal frontend against isolated API fixtures; never contacts the business server. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const guidance=process.argv.includes('--guidance');
const root=path.resolve('dist'),out=path.resolve(process.argv[2]),fixture=JSON.parse(fs.readFileSync(path.join(out,'ui-config.json'),'utf8'));
let config=fixture.config;const writes=[],errors=[];
const photos=[{id:'fixture-photo',name:'隔离图片.png',category:'real_image',categoryName:'真人图片',status:'available',filePath:'isolated/photo.png',fileSizeMb:1,usageCount:2,usageLimit:5,reservedCount:1,remainingCount:2},
{id:'locked-photo',name:'隔离占用图片.png',category:'real_image',categoryName:'真人图片',status:'used',filePath:'isolated/locked.png',fileSizeMb:1,usageCount:5,usageLimit:5,reservedCount:0,remainingCount:0,cleanupError:'文件正被占用'}];
const server=http.createServer((req,res)=>{
 const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname),file=path.resolve(root,'.'+(name==='/'?'/index.html':name));
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 fs.readFile(file,(e,body)=>{if(e){res.writeHead(404).end();return;}res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');res.end(body);});
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1050}});
  await context.route('**/api/**',route=>{
   const r=route.request(),u=new URL(r.url());
   if(u.pathname==='/api/v3/template-generation/config'){
    if(r.method()==='POST'){
     config=r.postDataJSON().config;
     if(guidance){
      const checked=require('node:child_process').spawnSync(process.env.PYTHON_FOR_VALIDATION||'C:/Users/Michael/AppData/Local/Programs/Python/Python312/python.exe',
       ['-X','utf8','-c','import json,sys;from server.ffmpeg_templates.config import validate;print(json.dumps(validate(json.load(sys.stdin)),ensure_ascii=False))'],
       {input:JSON.stringify(config),encoding:'utf8',windowsHide:true});
      assert.equal(checked.status,0,checked.stderr);config=JSON.parse(checked.stdout);
     }
     writes.push(u.pathname);return route.fulfill({json:{config}});
    }
    return route.fulfill({json:{...fixture,config}});
   }
   if(r.method()!=='GET')throw Error('Unexpected API write '+u.pathname);
   if(u.pathname==='/api/v2/production-resources')return route.fulfill({json:{items:photos}});
   if(u.pathname==='/api/v2/engine-parameters')return route.fulfill({json:{template_copy:{blessing:[],drama_prompt:[],blessing_default:[],drama_prompt_default:[],configured:false},midroll_endroll:{configured:false,strategy:{midroll:{enabled:false,mode:'latest',file:''},endroll:{enabled:false,mode:'latest',file:''}}}}});
   if(u.pathname==='/api/v2/task-center')return route.fulfill({json:{tasks:[],executors:[],dramaPriorities:[],isQueuePaused:false}});
   if(u.pathname==='/api/v2/settings')return route.fulfill({json:{publish_presets:['12:00'],publish_date_offset_days:0}});
   if(u.pathname==='/api/v2/revenue/source-data')return route.fulfill({json:{rows:[],accounts:[],theaters:[]}});
   return route.fulfill({json:{items:[]}});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'参数中心',exact:true}).click();
  const section=page.locator('section[aria-label="模板生成参数"]');await section.getByLabel('启用全屏贴纸叠层',{exact:true}).waitFor();
  if(guidance){
   assert.equal(await page.getByRole('heading',{name:'文案',exact:true}).count(),0);
   assert.equal(await page.getByText('祝福语',{exact:true}).count(),0);assert.equal(await page.getByText('引导语',{exact:true}).count(),0);
   await page.getByRole('heading',{name:'成片插片（中插 / 尾插）',exact:true}).waitFor();
   assert.equal(await section.locator('[data-parameter-key]').count(),25);
   for(const [key,info] of Object.entries(fixture.fields)){
    const card=section.locator(`[data-parameter-key="${key}"]`);
    assert.ok((await card.innerText()).includes(info.description));assert.ok((await card.innerText()).includes(info.rule));
   }
   assert.equal(await section.locator('input[type="number"][min], input[type="number"][max]').count(),0);
  }
  assert.equal(await section.getByLabel('启用全屏贴纸叠层',{exact:true}).isChecked(),false);
  await section.getByLabel('启用全屏贴纸叠层',{exact:true}).check();await section.getByLabel('启用真人图片叠层',{exact:true}).check();
  await section.getByLabel('每模板叠层贴纸数量下限',{exact:true}).fill('20');
  await section.getByLabel('每模板叠层贴纸数量上限',{exact:true}).fill('40');
  await section.getByLabel('真人叠层可见程度（%，越小越淡）',{exact:true}).fill('3');
  await section.getByLabel('每张真人图片使用上限（成功模板数）',{exact:true}).fill('7');
  if(guidance){
   for(const [name,value] of [['模板时长（秒）','2400'],['时长正负误差（秒）','400'],['大区域高度（画面 %）下限','40'],['大区域高度（画面 %）上限','50'],['贴纸整体透明度系数（%）','95'],['每模板叠层贴纸数量下限','128'],['每模板叠层贴纸数量上限','160'],['每模板真人图片数量下限','36'],['每模板真人图片数量上限','40'],['特效切换过渡（秒）下限','3'],['特效切换过渡（秒）上限','8'],['左右边条宽度（像素）下限','15'],['左右边条宽度（像素）上限','25'],['每张真人图片使用上限（成功模板数）','2000']])
    await section.getByLabel(name,{exact:true}).fill(value);
  }
  await section.getByRole('button',{name:'保存模板参数',exact:true}).click();await section.getByRole('status').waitFor();
  assert.equal(config.photo_layer_enabled,true);assert.equal(config.overlay_sticker_enabled,true);
  if(guidance){
   assert.deepEqual(config.overlay_sticker_count,[128,160]);assert.equal(config.photo_usage_limit,2000);assert.equal(config.sticker_alpha_percent,95);
   assert.equal(config.duration_seconds,2400);assert.deepEqual(config.border_width,[15,25]);
  }else{assert.deepEqual(config.overlay_sticker_count,[20,40]);assert.equal(config.photo_usage_limit,7);assert.equal(config.sticker_alpha_percent,80);}
  await section.getByRole('button',{name:'重新读取模板参数',exact:true}).click();await section.getByLabel('启用真人图片叠层',{exact:true}).waitFor();
  assert.equal(await section.getByLabel('启用真人图片叠层',{exact:true}).isChecked(),true);
  await section.screenshot({path:path.join(out,'parameters.png')});
  if(guidance){
   await section.locator('fieldset').filter({hasText:'全局与风景'}).screenshot({path:path.join(out,'parameter-help-wide.png')});
   await section.locator('fieldset').filter({hasText:'风景区域与融合'}).screenshot({path:path.join(out,'parameter-help-geometry.png')});
  }
  await page.setViewportSize({width:720,height:1000});assert.equal(await section.evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await section.screenshot({path:path.join(out,'parameters-narrow.png')});
  await page.getByRole('button',{name:'资料中心',exact:true}).click();await page.getByRole('button',{name:/生产资源/}).click();
  await page.getByText('隔离图片.png',{exact:true}).waitFor();await page.getByText('自动清理未完成：文件正被占用',{exact:true}).waitFor();
  assert.match(await page.locator('[data-resource-id="fixture-photo"]').innerText(),/已用 2\/5.*占用 1.*剩余 2/);
  await page.locator('[data-testid="production-resources"]').screenshot({path:path.join(out,'photo-quota.png')});
  assert.deepEqual(errors,[]);assert.equal(writes.length,1);
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({status:'PASS',errors,writes,guidance_mode:guidance,checks:guidance?['all 25 parameters explain purpose and intrinsic rules','no hard min/max input attributes','values beyond recommendations accepted by actual backend validator and reloaded','obsolete copy card absent; insertion card remains','narrow controls fit','photo quota and cleanup errors visible']:['independent toggles, bounds, opacity and quota saved and reloaded','original decoration opacity preserved','narrow controls fit','photo quota and cleanup errors visible']},null,2));
  console.log('PASS parameters, persistence, responsive layout, photo quota and cleanup errors');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
