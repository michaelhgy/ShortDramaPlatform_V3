/** Shared address library + private defaults on an isolated real V3 database. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/v3-publishing-address-book-20261026');
const info=JSON.parse(fs.readFileSync(path.join(out,'isolated-current.json'),'utf8'));
const checks=[],errors=[],writes=[];let searches=0;
const addr=name=>({uid:`fixture-${name}`,poiCheckSum:`fixture-check-${name}`,name:`成都公共地址${name}`,city:'成都市',fullAddress:`四川省成都市测试地点${name}`,latitude:30.6,longitude:104.1,_searchQuery:{query:`成都公共地址${name}`,latitude:0,longitude:0}});
const a=addr('A'),b=addr('B'),c=addr('C');
function checked(text){checks.push(text);console.log(text);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1540,height:1050},timezoneId:'Asia/Shanghai'});
 const api=(task,action='')=>`${info.url}/api/v2/publishing/tasks/${task}${action?'/'+action:''}`;
 async function post(task,action,data){const response=await context.request.post(api(task,action),{data});assert.equal(response.ok(),true,await response.text());return response.json();}
 async function book(task){return(await context.request.get(api(task,'address-book'))).json();}
 await post(info.task_id,'address-save',{address:a,default:true});
 await post(info.other_task_id,'address-save',{address:b,default:true});
 await post(info.other_task_id,'address-save',{address:c});
 let data=await(await context.request.get(api(info.task_id))).json();
 data.settings.groups.forEach(g=>g.location=a);data.settings.groups[0].short_title='保留原有短标题';data.settings.groups[0].video_title='这是独立的视频标题';
 await post(info.task_id,'settings',data.settings);
 await context.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()!=='GET'){
   writes.push(url.pathname);if(url.pathname.endsWith('/addresses'))searches++;
   if(/\/drafts$|\/release(?:\/|$)|\/cleanup(?:\/|$)|\/batches$/.test(url.pathname))throw Error('Generation/publication is forbidden');
  }
  // Display only account A; B's actual defaults/library are checked via real API.
  if(request.method()==='GET'&&['/api/v2/production-tasks','/api/v2/production-task-summaries'].includes(url.pathname)){
   const response=await route.fetch();const body=await response.json();body.items=body.items.filter(item=>item.id===info.task_id);return route.fulfill({json:body});
  }
  return route.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(info.url,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByRole('button',{name:'自动发布',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'发布工作台',exact:true});
  await dialog.getByText(/名称一致或仅符号差异，已自动关联。|已复用原关联，当前账号可挂载。/).waitFor({timeout:100000});
  const address=dialog.getByRole('region',{name:'发布地址',exact:true});
  await address.getByText(new RegExp('^'+a.name)).waitFor();await address.getByText('账号默认',{exact:true}).waitFor();
  assert.deepEqual((await book(info.other_task_id)).default_address,b);
  checked('account A and B retain different defaults while both see all shared addresses');
  await address.getByRole('button',{name:'更换',exact:true}).click();
  await address.getByRole('tab',{name:'公共地址库（3）',exact:true}).waitFor();
  await address.getByLabel('筛选地址库',{exact:true}).fill('地点B');
  const list=address.locator('[aria-label="公共地址列表"]');assert.equal(await list.getByRole('button').count(),2);
  await list.getByRole('button',{name:new RegExp('^'+b.name)}).click();
  await address.getByText(b.name,{exact:true}).waitFor();
  assert.deepEqual((await book(info.task_id)).default_address,a);assert.deepEqual((await book(info.other_task_id)).default_address,b);assert.equal(searches,0);
  checked('selecting another account shared address uses full stored parameters without search or default changes');
  await address.getByRole('button',{name:'更换',exact:true}).click();await address.getByLabel('筛选地址库',{exact:true}).fill('地点C');await list.getByRole('button',{name:new RegExp('^'+c.name)}).click();
  await address.getByRole('button',{name:'设为账号默认',exact:true}).click();await address.getByText('账号默认',{exact:true}).waitFor();
  assert.deepEqual((await book(info.task_id)).default_address,c);assert.deepEqual((await book(info.other_task_id)).default_address,b);
  await dialog.getByRole('button',{name:'保存设置',exact:true}).click();await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  checked('setting A default to C leaves B default at B');
  await address.getByRole('button',{name:'更换',exact:true}).click();await address.getByLabel('筛选地址库',{exact:true}).fill('');
  await page.screenshot({path:path.join(out,'shared-address-book.png')});
  await address.getByRole('button',{name:`删除公共地址 ${c.name}`,exact:true}).click();
  await address.getByRole('tab',{name:'公共地址库（2）',exact:true}).waitFor();
  assert.deepEqual((await book(info.task_id)).default_address,c);assert.deepEqual((await book(info.other_task_id)).default_address,b);
  data=await(await context.request.get(api(info.task_id))).json();assert.deepEqual(data.settings.groups[0].location,c);
  await address.getByRole('tab',{name:/^本账号记录/}).click();await address.locator('[aria-label="本账号地址列表"]').getByRole('button',{name:new RegExp('^'+c.name)}).waitFor();
  await address.getByRole('button',{name:'收起',exact:true}).click();
  checked('public removal preserves both defaults, account history and existing task location');
  const short=dialog.getByLabel('短标题（选填，6–16字）',{exact:true});assert.equal(await short.isVisible(),false);assert.equal(await short.inputValue(),'保留原有短标题');
  await dialog.getByText('追评与更多设置',{exact:true}).click();await short.waitFor({state:'visible'});
  await short.fill('更多设置的短标题');await dialog.getByRole('button',{name:'保存设置',exact:true}).click();await dialog.getByText('发布设置已保存。',{exact:true}).waitFor();
  await dialog.getByRole('button',{name:'短标题（选填，6–16字）历史',exact:true}).click();
  const history=page.getByRole('dialog',{name:'短标题（选填，6–16字）历史记录',exact:true});await history.getByRole('button',{name:'保留原有短标题',exact:true}).waitFor();
  await page.keyboard.press('Escape');await dialog.getByText('追评与更多设置',{exact:true}).click();assert.equal(await short.isVisible(),false);
  await page.screenshot({path:path.join(out,'collapsed-short-title.png')});
  await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});await page.getByRole('button',{name:'自动发布',exact:true}).click();
  await dialog.getByText('已复用原关联，当前账号可挂载。',{exact:true}).waitFor({timeout:100000});
  assert.equal(await short.isVisible(),false);await dialog.getByText('追评与更多设置',{exact:true}).click();assert.equal(await short.inputValue(),'更多设置的短标题');
  assert.equal(await dialog.getByLabel('视频标题（选填）',{exact:true}).inputValue(),'这是独立的视频标题');
  checked('short title stays collapsed in more settings; saved content and separate history survive reopening');
  assert.equal(searches,0);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'address-book-result.json'),JSON.stringify({status:'PASS',checks,errors,writes,searches},null,2));
 }catch(error){await page.screenshot({path:path.join(out,'address-book-failure.png')});fs.writeFileSync(path.join(out,'address-book-result.json'),JSON.stringify({status:'FAIL',checks,errors,writes,searches,error:String(error)},null,2));throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
