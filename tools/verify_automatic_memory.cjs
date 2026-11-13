/** Built UI + isolated API; run enable/on/off across actual fixture process restarts. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve('local-test-output/auto-composition-memory-20261026'),info=JSON.parse(fs.readFileSync(path.join(out,'current.json'),'utf8')),phase=process.argv[2];
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1200,height:900}}),page=await context.newPage(),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 const state=async()=>{const r=await context.request.get(info.url+'/api/v3/final-composition');assert.ok(r.ok(),await r.text());return r.json();};
 const toggle=page.getByTestId('automatic-composition');
 async function expect(enabled){await page.waitForFunction(value=>document.querySelector('[data-testid="automatic-composition"]')?.getAttribute('aria-checked')===String(value),enabled);assert.equal((await state()).auto_enabled,enabled);}
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();await page.getByTestId('production-task-card').first().waitFor();
  await expect(phase==='on');checks.push(`process-start-state-${phase==='on'?'on':'off'}`);
  const cards=page.getByTestId('production-task-card');assert.equal(await cards.count(),3);assert.equal(await cards.locator('svg.lucide-grip-vertical').count(),0);
  const sizes=await cards.getByTestId('production-account-avatar').evaluateAll(items=>items.map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height,left:e.getBoundingClientRect().left-e.closest('[data-production-task]').getBoundingClientRect().left})));
  assert.ok(sizes.every(s=>s.width===24&&s.height===24&&s.left<=16),JSON.stringify(sizes));checks.push('card-grip-removed-and-full-size-avatar-first');
  if(phase==='enable'){
   await toggle.click();await expect(true);await page.reload();await page.getByRole('button',{name:'生产中心',exact:true}).click();await expect(true);checks.push('enable-and-page-reload-remembers-on');
   const r=await cards.first().boundingBox();await page.mouse.move(r.x+r.width*.5,r.y+25);await page.mouse.down();await page.getByTestId('production-drag-preview').waitFor();await page.keyboard.press('Escape');await page.mouse.up();await page.getByTestId('production-drag-preview').waitFor({state:'hidden'});checks.push('whole-card-long-press-and-escape-still-work-without-grip');
  }else if(phase==='on'){await toggle.click();await expect(false);checks.push('disable-after-backend-process-restart');}
  else assert.equal(phase,'off');
  assert.equal((await state()).jobs.length,0);assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(out,`state-${phase}.png`)});fs.writeFileSync(path.join(out,`browser-${phase}.json`),JSON.stringify({phase,checks,errors,sizes,actualMediaRendered:false},null,2));console.log(JSON.stringify({phase,checks,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
