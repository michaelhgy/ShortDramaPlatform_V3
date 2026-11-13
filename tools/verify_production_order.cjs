const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve('local-test-output/production-order-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'current.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1500,height:1050}}),page=await context.newPage(),checks=[],errors=[],orderWrites=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/final-composition/order'))orderWrites.push(r.postDataJSON());});
 const ids=()=>page.getByTestId('production-task-card').evaluateAll(cards=>cards.map(c=>c.dataset.productionTask));
 const card=id=>page.locator(`[data-production-task="${id}"]`);
 const api=async path=>(await context.request.get(info.url+path)).json();
 const hold=async id=>{const b=await card(id).boundingBox();await page.mouse.move(b.x+b.width*.5,b.y+b.height*.3);await page.mouse.down();await page.waitForTimeout(1100);await page.getByTestId('production-drag-preview').waitFor();};
 const drop=async id=>{const b=await card(id).boundingBox();await page.mouse.move(b.x+b.width*.5,b.y+10,{steps:7});await page.getByTestId('production-drop-marker').waitFor();await page.mouse.up();};
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('[data-production-task]').length===3);
  assert.deepEqual(await ids(),info.tasks);assert.equal(await page.getByTestId('automatic-composition').getAttribute('aria-checked'),'false');checks.push('default-card-date-order-and-automatic-off');
  await card(info.tasks[0]).click();assert.ok((await card(info.tasks[0]).innerText()).includes('10月11日'));await page.getByTestId('production-task-header').getByText('10月11日',{exact:true}).waitFor();assert.equal((await api('/api/v2/production-task-summaries')).items.find(t=>t.id===info.tasks[0]).planned_publish_at,'2026-10-11');checks.push('month-day-display-preserves-iso-storage-and-overdue-rules');
  const b=await card(info.tasks[2]).boundingBox();await page.mouse.move(b.x+100,b.y+20);await page.mouse.down();await page.waitForTimeout(250);await page.mouse.move(b.x+110,b.y-70,{steps:3});await page.mouse.up();assert.equal(orderWrites.length,0);assert.deepEqual(await ids(),info.tasks);checks.push('short-press-and-early-movement-do-not-reorder');
  await hold(info.tasks[2]);await page.keyboard.press('Escape');await page.mouse.up();assert.equal(orderWrites.length,0);assert.deepEqual(await ids(),info.tasks);checks.push('escape-cancels-long-press-drag');
  await hold(info.tasks[2]);const target=await card(info.tasks[0]).boundingBox();await page.mouse.move(target.x+100,target.y+10,{steps:8});await page.getByTestId('production-drop-marker').waitFor();await page.screenshot({path:path.join(out,'长按拖动排序.png'),fullPage:true});await page.mouse.up();
  await page.waitForFunction(id=>document.querySelector('[data-production-task]')?.dataset.productionTask===id,info.tasks[2]);await page.waitForFunction(async()=>{const r=await fetch('/api/v2/production-task-summaries');return(await r.json()).items.some(t=>t.manual_order>0);});assert.equal(orderWrites.length,1);checks.push('one-second-hold-drag-saves-real-order');
  const expected=[info.tasks[2],info.tasks[0],info.tasks[1]];assert.deepEqual(await ids(),expected);
  await page.reload();await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('[data-production-task]').length===3);assert.deepEqual(await ids(),expected);checks.push('manual-order-survives-full-reload');
  await page.getByTestId('automatic-composition').click();await page.waitForFunction(()=>document.querySelector('[data-testid="automatic-composition"]')?.getAttribute('aria-checked')==='true');assert.equal((await api('/api/v3/final-composition')).auto_enabled,true);await page.screenshot({path:path.join(out,'自动合成已开启.png'),fullPage:true});checks.push('automatic-switch-controls-backend-with-enabled-style');
  await page.getByTestId('automatic-composition').click();await page.waitForFunction(()=>document.querySelector('[data-testid="automatic-composition"]')?.getAttribute('aria-checked')==='false');assert.equal((await api('/api/v3/final-composition')).auto_enabled,false);checks.push('automatic-switch-closes-again');
  assert.equal((await api('/api/v3/final-composition')).jobs.length,0);checks.push('automatic-does-not-choose-templates-or-create-unready-jobs');
  await page.screenshot({path:path.join(out,'卡片顺序与自动合成关闭.png'),fullPage:true});
  await page.setViewportSize({width:1100,height:850});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);checks.push('narrow-header-has-no-page-overflow');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({checks,errors,orderWrites,realBusinessWrites:0,actualMediaRendered:false},null,2));console.log(JSON.stringify({checks:checks.length,errors,orderWrites:orderWrites.length}));
 }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
