/** Built UI + isolated V3 API; never creates or publishes drafts. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-publishing-interaction-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],nativeDialogs=[],geometry=[];
function checked(value){checks.push(value);console.log(value);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 let delayed=false,failCheck=false,assistFixture=false,adopted=0;
 const assisted={state:'needs_help',running:false,items:[{key:'fixture-assist',group_id:'fixture',group_name:'正剧视频',name:'测试草稿.mp4',copy:1,time:'',status:'needs_help',draft_id:900001}]};
 await context.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(assistFixture&&((request.method()==='GET'&&(url.pathname===new URL(api).pathname||url.pathname.endsWith('/execution')))||(request.method()==='POST'&&url.pathname.endsWith('/settings')))){
   if(url.pathname.endsWith('/execution'))return route.fulfill({json:assisted});
   const response=await route.fetch();const body=await response.json();body.execution=assisted;return route.fulfill({json:body});
  }
  if(assistFixture&&url.pathname.endsWith('/adopt-draft')){
   const args=request.postDataJSON();if(args.confirmed){adopted++;assisted.state='ready';assisted.items[0].status='ready';assisted.items[0].accepted_payload={};}
   return route.fulfill({json:{summary:{address:'测试地址',drama:'测试剧集',time:'测试时间',description:'测试简介'},accepted:Boolean(args.confirmed)}});
  }
  if(request.method()!=='GET'){
   if(/\/drafts$|\/release(?:\/|$)|\/cleanup(?:\/|$)|publish-task|publish-draft/.test(url.pathname))throw Error('Draft creation/publication is forbidden in this UI test');
   if(delayed)await new Promise(resolve=>setTimeout(resolve,350));
   if(failCheck&&url.pathname.endsWith('/check'))return route.fulfill({status:400,json:{error:'隔离测试：模拟连接异常，请重试。'}});
  }
  return route.continue();
 });
 const api=info.url+'/api/v2/publishing/tasks/'+info.task_id;
 let data=await(await context.request.get(api)).json();
 data.settings.groups[0].video_title='历史标题一测试';data.settings.groups[0].short_title='独立的短标题';data.settings.groups[0].desc='第一条简介\n第二行内容';data.settings.groups[0].tags=['短剧','精彩'];
 await context.request.post(api+'/settings',{data:data.settings});
 data.settings.groups[0].video_title='历史标题二测试';data.settings.groups[0].desc='第二条简介';
 await context.request.post(api+'/settings',{data:data.settings});
 const page=await context.newPage();page.setDefaultTimeout(25000);
 page.on('pageerror',error=>errors.push(error.message));page.on('dialog',async dialog=>{nativeDialogs.push(dialog.message());await dialog.dismiss();});
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'生产中心',exact:true}).click();
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'发布工作台',exact:true});
  await dialog.getByText(/名称一致或仅符号差异，已自动关联。|已复用原关联，当前账号可挂载。/).waitFor({timeout:100000});
  await page.getByRole('button',{name:'检查连接',exact:true}).waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('[aria-label="发布工作台"] button')?.disabled);
  await dialog.locator('main').evaluate(e=>e.scrollTop=0);
  delayed=true;
  for(let repeat=0;repeat<3;repeat++)for(const name of ['检查连接','刷新','保存设置','仅检查']){
   const action=dialog.getByRole('button',{name,exact:true});
   await page.evaluate(()=>{
    window.__recordLayout=true;window.__layoutSamples=[];
    function sample(){const root=document.querySelector('[aria-label="发布工作台"]');const main=root.querySelector('main'),header=root.querySelector('header'),footer=root.querySelector('footer');window.__layoutSamples.push([main.getBoundingClientRect().y,main.getBoundingClientRect().height,header.getBoundingClientRect().height,footer.getBoundingClientRect().y,footer.getBoundingClientRect().height,main.scrollTop]);if(window.__recordLayout)requestAnimationFrame(sample);}sample();
   });
   await action.click();await page.waitForTimeout(80);
   await page.waitForFunction(()=>!document.querySelector('[aria-label="发布工作台"] button')?.disabled);
   const samples=await page.evaluate(()=>{window.__recordLayout=false;return window.__layoutSamples;});
   const span=Array.from({length:6},(_,i)=>Math.max(...samples.map(s=>s[i]))-Math.min(...samples.map(s=>s[i])));
   geometry.push({name,repeat,samples:samples.length,span});assert.ok(span.every(value=>value<=1),JSON.stringify(geometry.at(-1)));
  }
  checked('12 delayed real API actions keep header/main/footer positions, height and scroll stable');
  failCheck=true;await dialog.getByRole('button',{name:'仅检查',exact:true}).click();
  await dialog.getByRole('alert').getByText('隔离测试：模拟连接异常，请重试。',{exact:true}).waitFor();
  assert.equal(await dialog.getByRole('alert').evaluate(e=>Boolean(e.closest('footer'))),true);
  await dialog.getByRole('button',{name:'查看错误详情',exact:true}).click();
  await page.getByRole('alertdialog',{name:'操作提示',exact:true}).getByRole('button',{name:'知道了',exact:true}).click();
  failCheck=false;await dialog.getByRole('button',{name:'检查连接',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('[aria-label="发布工作台"] button')?.disabled);
  checked('errors use fixed footer status and styled detail dialog without inserting a top row');
  const title=dialog.getByLabel('视频标题（选填）',{exact:true}),topics=dialog.getByLabel('话题（空格、逗号或 # 分隔）',{exact:true}),desc=dialog.getByLabel('简介（选填）',{exact:true});
  await desc.scrollIntoViewIfNeeded();
  let t=await title.boundingBox(),p=await topics.boundingBox(),d=await desc.boundingBox();
  assert.ok(t.x===p.x&&p.y>t.y&&d.x>t.x+t.width&&Math.abs(d.y-t.y)<2);
  assert.ok(d.y+d.height>=p.y+p.height-2);
  assert.equal(await dialog.getByText(/使用过的记录/).count(),0);
  checked('full-width copy card places title/topics on left, description on right with no expanded history blocks');
  const before=await desc.boundingBox();
  await dialog.getByRole('button',{name:'视频标题（选填）历史',exact:true}).click();
  let popup=page.getByRole('dialog',{name:'视频标题（选填）历史记录',exact:true});
  await popup.getByRole('button',{name:'历史标题一测试',exact:true}).waitFor();
  assert.deepEqual(await desc.boundingBox(),before);
  await page.screenshot({path:path.join(out,'history-popover.png')});
  await popup.getByLabel('搜索视频标题（选填）历史',{exact:true}).fill('一');
  assert.equal(await popup.getByRole('button',{name:'历史标题二测试',exact:true}).count(),0);
  await popup.getByRole('button',{name:'历史标题一测试',exact:true}).click();
  assert.equal(await title.inputValue(),'历史标题一测试');
  await dialog.getByRole('button',{name:'视频标题（选填）历史',exact:true}).click();
  await popup.getByRole('button',{name:'删除历史：历史标题二测试',exact:true}).click();
  await popup.getByRole('button',{name:'历史标题二测试',exact:true}).waitFor({state:'detached'});
  assert.equal(await title.inputValue(),'历史标题一测试');
  await page.keyboard.press('Escape');
  assert.equal(await dialog.count(),1);
  await dialog.getByRole('button',{name:'简介（选填）历史',exact:true}).click();
  popup=page.getByRole('dialog',{name:'简介（选填）历史记录',exact:true});
  await popup.getByRole('button',{name:'第一条简介 第二行内容',exact:true}).click();
  assert.equal(await desc.inputValue(),'第一条简介\n第二行内容');
  checked('history popovers search/select/delete, preserve multiline text and never reflow the form');
  await page.keyboard.press('Escape');
  let confirm=page.getByRole('alertdialog',{name:'关闭发布工作台',exact:true});
  await confirm.getByRole('button',{name:'取消',exact:true}).click();assert.equal(await title.inputValue(),'历史标题一测试');
  await dialog.getByRole('button',{name:'保存设置',exact:true}).click();await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  await dialog.getByRole('button',{name:'特殊调整',exact:true}).click();
  await dialog.getByRole('button',{name:'恢复自动识别',exact:true}).click();
  confirm=page.getByRole('alertdialog',{name:'恢复自动分组',exact:true});
  await page.screenshot({path:path.join(out,'styled-confirmation.png')});
  await page.keyboard.press('Escape');
  await dialog.getByRole('button',{name:'恢复自动识别',exact:true}).click();
  await confirm.getByRole('button',{name:'恢复自动分组',exact:true}).click();await confirm.waitFor({state:'detached'});
  await dialog.getByRole('button',{name:'收起特殊调整',exact:true}).click();
  checked('styled confirmations handle cancel, Escape and confirm without any browser-native dialog');
  await desc.scrollIntoViewIfNeeded();
  await dialog.getByRole('region',{name:'发布文案',exact:true}).screenshot({path:path.join(out,'copy-layout.png')});
  await page.screenshot({path:path.join(out,'publishing-workbench.png')});
  await dialog.getByRole('button',{name:'关闭发布工作台',exact:true}).click();
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  await dialog.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor({timeout:100000});
  assert.equal(await title.inputValue(),'历史标题一测试');assert.equal(await dialog.getByLabel('短标题（选填，6–16字）',{exact:true}).inputValue(),'独立的短标题');assert.equal(await desc.inputValue(),'第一条简介\n第二行内容');
  await page.setViewportSize({width:1200,height:820});await desc.scrollIntoViewIfNeeded();
  assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await dialog.getByRole('button',{name:'简介（选填）历史',exact:true}).click();
  popup=page.getByRole('dialog',{name:'简介（选填）历史记录',exact:true});await popup.waitFor();
  const b=await popup.boundingBox();assert.ok(b.x>=0&&b.y>=0&&b.x+b.width<=1201&&b.y+b.height<=821);
  await page.screenshot({path:path.join(out,'publishing-1200.png')});await page.keyboard.press('Escape');
  checked('saved values survive reopening and history popup fits a 1200x820 desktop');
  await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
  checked('Escape closes a clean workbench, confirms unsaved changes and only dismisses the topmost popup');
  assistFixture=true;
  await page.getByRole('button',{name:'自动发布',exact:true}).click();
  await dialog.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor({timeout:100000});
  await dialog.getByRole('button',{name:'采纳该条人工设置',exact:true}).click();
  confirm=page.getByRole('alertdialog',{name:'采纳该条人工设置',exact:true});
  await confirm.getByText(/地址：测试地址/).waitFor();await page.keyboard.press('Escape');assert.equal(adopted,0);
  await dialog.getByRole('button',{name:'采纳该条人工设置',exact:true}).click();
  await confirm.getByRole('button',{name:'确认采纳',exact:true}).click();
  await dialog.getByText('已采纳并检查该条人工设置，其他草稿和分组设置未改变。',{exact:true}).waitFor();assert.equal(adopted,1);
  checked('manual-adoption confirmation shows the per-draft summary and only submits after styled confirmation (response fixture)');
  assistFixture=false;

  assert.deepEqual(nativeDialogs,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'interaction-result.json'),JSON.stringify({status:'PASS',checks,geometry,nativeDialogs,errors},null,2));
 }catch(error){await page.screenshot({path:path.join(out,'interaction-failure.png')});fs.writeFileSync(path.join(out,'interaction-result.json'),JSON.stringify({status:'FAIL',checks,geometry,nativeDialogs,errors,error:String(error)},null,2));throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
