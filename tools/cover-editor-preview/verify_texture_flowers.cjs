const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Michael/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve('local-test-output/texture-flowers-20261026');fs.mkdirSync(out,{recursive:true});
const info=JSON.parse(fs.readFileSync('local-test-output/cover-integration-20261026/current.json','utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1200,height:1000},acceptDownloads:true});
 const page=await context.newPage(),errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 const api=async(action='',body)=>{const response=await context.request[body===undefined?'get':'post'](info.url+'/api/v2/cover-editor/flowers'+action,body===undefined?{}:{data:body,timeout:60000});const value=await response.json();assert.ok(response.ok(),JSON.stringify(value));return value;};
 const selected=async()=>Number((await page.locator('#import-flowers').textContent()).match(/（(\d+)）/)[1]);
 try{
  await context.request.post(info.url+'/api/v2/dramas/'+info.drama_id+'/cover',{data:{filename:'cover.jpeg',content_base64:fs.readFileSync('D:/短剧推广运营系统/剧集资料/一口铁锅走天下/封面/一口铁锅走天下-封面.jpeg').toString('base64')}});
  const library=await api(),known=new Set(library.styles.filter(s=>s.enabled!==false).map(s=>s.id));
  const scan=await api('/scan',{remember:false}),available=scan.items.filter(s=>s.status==='ready'&&!known.has(s.id));assert.ok(available.length>1);
  await page.goto(info.url+'/cover-editor.html?dramaId='+info.drama_id);await page.waitForFunction(()=>window.coverPreview?.ready);
  await page.locator('#manage-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor();
  const pageAvailable=scan.items.slice(0,48).filter(s=>s.status==='ready'&&!known.has(s.id)).length;
  await page.locator('#select-page-flowers').click();assert.equal(await selected(),pageAvailable);checks.push('select-current-page');
  await page.locator('#clear-flower-selection').click();assert.equal(await selected(),0);checks.push('clear-all-selection');
  for(const candidate of available.slice(0,2))await page.locator(`.cache-card[data-id="${candidate.id}"] input`).check();
  assert.equal(await selected(),2);checks.push('individual-multiple-selection');
  await page.locator('#clear-flower-selection').click();await page.locator('#cache-query').fill(available[0].id);await page.locator('#select-all-flowers').click();assert.equal(await selected(),1);checks.push('select-all-respects-search');
  await page.locator('#clear-flower-selection').click();await page.locator('#cache-query').fill('');await page.locator('#cache-filter').selectOption('unsupported');await page.locator('#select-all-flowers').click();assert.equal(await selected(),0);checks.push('unsupported-skipped');
  await page.locator('#cache-filter').selectOption('all');await page.locator('#select-all-flowers').click();assert.equal(await selected(),available.length);
  await page.locator('#flower-page-next').click();assert.ok(await page.locator('#cache-results input:checked').count()>0);checks.push('select-all-across-pages-skips-imported');
  await page.screenshot({path:path.join(out,'全选与多选.png'),fullPage:true});
  await page.locator('#import-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor({timeout:60000});assert.equal(await selected(),0);
  assert.equal((await api()).styles.length,scan.ready_count);checks.push('bulk-import-selected-real-cache');
  await page.locator('#close-flowers').click();
  const allRendered=await page.evaluate(async()=>{const p=window.coverPreview;await p.prepareFlowerStyles(p.getStyles());return p.getStyles().map(s=>{const o=p.renderText({...p.getLayers()[0],text:'通用花字验证',width:700,height:150,fontSize:80},s);const d=o.canvas.getContext('2d').getImageData(0,0,o.canvas.width,o.canvas.height).data;let pixels=0;for(let i=3;i<d.length;i+=4)if(d[i]>5)pixels++;return {id:s.id,pixels};});});
  assert.ok(allRendered.every(s=>s.pixels>100));checks.push('all-imported-styles-generate-pixels');
  const visual=await page.evaluate(async()=>{
   const p=window.coverPreview,ids=['7313160248175398154','7328988266768764194','7371391474404986150','7312801045271399714','7306901916288666906'];
   const styles=ids.map(id=>p.getStyles().find(s=>s.id===id)).filter(Boolean);if(styles.length<4)throw Error('Expected real texture fixtures');
   const sheet=document.createElement('canvas');sheet.width=1200;sheet.height=90+styles.length*230;const ctx=sheet.getContext('2d');ctx.fillStyle='#eef1f5';ctx.fillRect(0,0,sheet.width,sheet.height);ctx.fillStyle='#182032';ctx.font='bold 26px Microsoft YaHei';ctx.fillText('剪映缓存原预览  /  V3实际文字绘制',35,48);
   const rows=[];
   for(let i=0;i<styles.length;i++){
    const s=styles[i],top=90+i*230;ctx.fillStyle='#fff';ctx.fillRect(18,top,1164,214);ctx.fillStyle='#182032';ctx.font='17px Microsoft YaHei';ctx.fillText(s.name,35,top+26);
    const icon=new Image();icon.src=s.icon;await icon.decode();ctx.fillStyle='#555b63';ctx.fillRect(35,top+44,240,130);ctx.drawImage(icon,35,top+44,240,130);
    const output=p.renderText({...p.getLayers()[0],text:'一口铁锅走天下',width:820,height:130,fontSize:96,background:'transparent',backgroundAlpha:0},s);
    const data=output.canvas.getContext('2d').getImageData(0,0,output.canvas.width,output.canvas.height).data;let pixels=0;for(let k=3;k<data.length;k+=4)if(data[k]>5)pixels++;
    ctx.save();ctx.beginPath();ctx.rect(300,top+40,860,160);ctx.clip();ctx.drawImage(output.canvas,310-output.padding,top+55-output.padding);ctx.restore();
    rows.push({id:s.id,name:s.name,pixels});
   }
   return {image:sheet.toDataURL('image/png'),rows};
  });
  assert.ok(visual.rows.every(r=>r.pixels>100));fs.writeFileSync(path.join(out,'纹理花字实际效果.png'),Buffer.from(visual.image.split(',')[1],'base64'));checks.push('representative-real-texture-previews-and-nonempty-renders');
  await page.locator('#flower-query').fill('7328988266768764194');await page.locator('.style-card').click();await page.locator('#copy').fill('一口铁锅\n走天下');
  await page.locator('#save-use').click();await page.locator('#save-use:not(:disabled)').waitFor();
  const downloading=page.waitForEvent('download');await page.locator('#export').click();await(await downloading).saveAs(path.join(out,'金属纹理封面.png'));checks.push('texture-cover-save-and-export');
  await page.reload();await page.waitForFunction(()=>window.coverPreview?.ready&&document.querySelector('#copy')?.value==='一口铁锅\n走天下');checks.push('texture-edit-reopens');
  await page.locator('#manage-flowers').click();await page.locator('#scan-flowers:not(:disabled)').waitFor();await page.setViewportSize({width:720,height:950});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);checks.push('narrow-window-bulk-controls');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({checks,cached:scan.items.length,compatible:scan.ready_count,added:available.length,allRendered,visual:visual.rows,errors,realBusinessWrites:0},null,2));console.log(JSON.stringify({checks:checks.length,compatible:scan.ready_count,added:available.length,errors}));
 }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
