const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const info=JSON.parse(fs.readFileSync('local-test-output/cover-integration-20261026/current.json','utf8'));
const out=path.resolve('local-test-output/cover-visibility-paging-20261026');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1500,height:1000}}),page=await context.newPage(),checks=[],errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{errors.push('Unexpected native dialog: '+d.type());await d.dismiss();});
 const get=async path=>(await context.request.get(info.url+path)).json();
 const endpoint='/api/v2/cover-editor/dramas/'+info.drama_id;
 const snap=()=>get(endpoint),normal=page.locator(`[data-testid="task-drama-cover"][data-drama-id="${info.drama_id}"]`);
 const pair=page.getByTestId('task-cover-pair').filter({has:normal});
 const frame=()=>page.frameLocator('iframe[title="封面文字编辑器"]');
 try{
  await page.goto(info.url);await page.getByRole('button',{name:'生产中心',exact:true}).click();await normal.waitFor();assert.equal(await pair.locator('button').count(),1);
  await normal.click({button:'right'});await frame().locator('#editor-workspace').waitFor();
  assert.equal(await frame().locator('.style-card').count(),12);const first=await frame().locator('.style-card').evaluateAll(cards=>cards.map(c=>c.dataset.id));
  await frame().locator('#library-page-next').click();const second=await frame().locator('.style-card').evaluateAll(cards=>cards.map(c=>c.dataset.id));assert.equal(second.length,12);assert.equal(second.some(id=>first.includes(id)),false);checks.push('library-renders-twelve-per-page-with-distinct-pages');
  const all=new Set([...first,...second]);while(!await frame().locator('#library-page-next').isDisabled()){await frame().locator('#library-page-next').click();for(const id of await frame().locator('.style-card').evaluateAll(cards=>cards.map(c=>c.dataset.id)))all.add(id);}
  const library=await get('/api/v2/cover-editor/flowers?compact=1');assert.equal(all.size,library.styles.filter(s=>s.enabled!==false).length);checks.push('paging-reaches-every-library-style');
  await frame().locator('#flower-query').fill(first[0]);assert.equal(await frame().locator('.style-card').count(),1);assert.ok((await frame().locator('#library-page-label').textContent()).startsWith('1 / 1'));checks.push('search-spans-all-pages-and-resets-first-page');
  await frame().locator('#flower-query').fill('');await frame().locator('#flower-filter').selectOption('favorite');assert.ok((await frame().locator('#library-page-label').textContent()).startsWith('1 /'));assert.ok(await frame().locator('.style-card').count()<=12);checks.push('favorites-are-paginated-and-reset-page');
  await frame().locator('#flower-filter').selectOption('recent');assert.ok(await frame().locator('.style-card').count()<=12);await frame().locator('#flower-filter').selectOption('frequent');assert.ok(await frame().locator('.style-card').count()<=12);checks.push('recent-and-most-used-respect-pagination');
  await frame().locator('#flower-filter').selectOption('all');await frame().locator('#tab-sheep').click();await frame().locator('#save-use:not(:disabled)').waitFor();
  await page.waitForFunction(async id=>(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).project.sheep.versions.length===1,info.drama_id);
  let saved=await snap();assert.equal(saved.project.sheep.activeId,'original');assert.equal(saved.sheep_visible,false);assert.equal(await pair.locator('button').count(),1);checks.push('automatic-sheep-modification-does-not-reveal-second-card');
  await frame().locator('#save-use').click();await page.waitForFunction(async id=>(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).sheep_visible,info.drama_id);await pair.getByTestId('task-sheep-cover').waitFor();checks.push('selecting-sheep-modification-reveals-second-card');
  await page.getByRole('button',{name:'关闭封面编辑',exact:true}).click();await page.getByRole('dialog',{name:'封面编辑',exact:true}).waitFor({state:'hidden'});
  await page.screenshot({path:path.join(out,'羊头使用修改版显示两张.png'),fullPage:true});
  await pair.getByTestId('task-sheep-cover').click({button:'right'});await frame().locator('#editor-workspace').waitFor();await frame().locator('[data-version="original"]').click();await frame().locator('#save-use').getByText('设为使用',{exact:true}).waitFor();await frame().locator('#save-use').click();
  await page.waitForFunction(async id=>!(await(await fetch('/api/v2/cover-editor/dramas/'+id)).json()).sheep_visible,info.drama_id);await pair.getByTestId('task-sheep-cover').waitFor({state:'hidden'});saved=await snap();assert.equal(saved.project.sheep.versions.length,1);checks.push('choosing-original-hides-second-card-while-retaining-modification');
  await page.getByRole('button',{name:'关闭封面编辑',exact:true}).click();await page.getByRole('dialog',{name:'封面编辑',exact:true}).waitFor({state:'hidden'});
  await page.screenshot({path:path.join(out,'羊头使用原始封面只显示一张.png'),fullPage:true});
  await page.reload();await page.getByRole('button',{name:'生产中心',exact:true}).click();await normal.waitFor();assert.equal(await pair.locator('button').count(),1);checks.push('single-card-selection-survives-reload');
  const publishing=await get(`/api/v2/publishing/tasks/${info.task_id}/context`);assert.equal(publishing.sheep_cover_visible,false);assert.equal(publishing.sheep_cover.path,(await get(`/api/v2/cover-editor/tasks/${info.task_id}/context`)).sheep_cover.path);assert.equal(publishing.sheep_cover.exists,true);checks.push('publishing-still-resolves-selected-sheep-original');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({checks,styles:all.size,errors,realBusinessWrites:0},null,2));console.log(JSON.stringify({checks:checks.length,styles:all.size,errors}));
 }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
