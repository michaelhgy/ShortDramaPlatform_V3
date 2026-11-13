/** Native Publish versus plugin Draft routing against real isolated HTTP/SQLite. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-real-publishing-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1400,height:1000}}),page=await context.newPage(),errors=[],checks=[];
 const root=`${info.url}/api/v2/publishing/tasks/${info.task_id}`;
 const get=async action=>(await context.request.get(root+'/'+action+'?t='+Date.now())).json();
 async function waitState(action,predicate){for(let i=0;i<100;i++){const value=await get(action);if(predicate(value))return value;await page.waitForTimeout(100);}throw Error('state did not settle');}
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByRole('button',{name:'自动发布',exact:true}).click();const work=page.getByRole('dialog',{name:'发布工作台',exact:true});await work.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor();
  await work.getByRole('button',{name:'发布',exact:true}).click();const first=await waitState('publication',v=>!v.running&&v.items.length===2&&v.items.every(i=>i.status==='success'));assert.ok(first.items.every(i=>i.local_id));assert.equal((await get('execution')).items.length,0);checks.push('native Publish submits real publication route and keeps local draft ledger empty');
  await work.getByRole('button',{name:'发布',exact:true}).waitFor();await work.getByRole('button',{name:'发布',exact:true}).click();const again=await waitState('publication',v=>!v.running&&v.items.length===2&&v.items.every(i=>i.status==='success'));assert.deepEqual(again.items.map(i=>i.local_id),first.items.map(i=>i.local_id));checks.push('repeat Publish reconciles existing queue identifiers without duplicate submissions');
  await page.screenshot({path:path.join(out,'native-publish.png')});await work.getByLabel('挂载方式',{exact:true}).selectOption('plugin');await work.getByText('挂载方式已保存到当前任务的发布设置。',{exact:true}).waitFor();
  await work.getByRole('button',{name:'发布草稿',exact:true}).click();const draft=await waitState('execution',v=>!v.running&&v.items.length===2&&v.items.every(i=>i.status==='ready'));assert.ok(draft.items.every(i=>i.draft_id));assert.deepEqual((await get('publication')).items.map(i=>i.local_id),first.items.map(i=>i.local_id));checks.push('plugin Draft routes to local drafts and leaves native publication records untouched');
  await work.getByRole('button',{name:'发布草稿',exact:true}).waitFor();await page.screenshot({path:path.join(out,'plugin-drafts.png')});assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({checks,errors,native:first,plugin:draft,realMcp:false},null,2));console.log(JSON.stringify({checks,errors}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png')});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
