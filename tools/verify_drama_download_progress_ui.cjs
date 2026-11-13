/* Isolated component interaction checks. Never calls the business backend. */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const esbuild = require('esbuild');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'local-test-output', 'drama-download-progress-20261109');
fs.mkdirSync(out, {recursive:true});
const entry = path.join(out, 'fixture.tsx');
fs.writeFileSync(entry, `import React from 'react';
import {createRoot} from 'react-dom/client';
import {DramaDownloadModal} from '../../src/components/assets/modals/DramaDownloadModal';
const initial={status:'running',phase:'collect-links',created_at:'fixture',current_step:'正在复制第11集分享链接',task:{drama_name:'隔离验证剧',task_label:'#隔离验证剧',chat_name:'任务群'},expected_count:48,collected_count:48,parsed_episodes:[],downloaded_episodes:[],verified_count:0,stage_logs:{'read-task':['已识别置顶任务：#隔离验证剧'],'collect-links':['正在选择第11集','正在打开第11集分享面板','正在复制第11集分享链接']}};
function App(){const [state,setState]=React.useState(initial);window.setTaskState=(patch)=>setState(old=>({...old,...patch,stage_logs:{...old.stage_logs,...patch.stage_logs}}));return <DramaDownloadModal isOpen downloadRoot="Z:/04短剧原片" readTaskState={state} onClose={()=>{}} onOpenFolder={()=>{}} onStartPipeline={()=>{}} onStopPipeline={()=>{}}/>;}
createRoot(document.getElementById('root')).render(<App/>);`);
esbuild.buildSync({entryPoints:[entry],bundle:true,format:'iife',outfile:path.join(out,'fixture.js'),jsx:'automatic'});
const cssFile=fs.readdirSync(path.join(root,'dist/assets')).find(n=>n.endsWith('.css'));
const server=http.createServer((req,res)=>{
  if(req.url==='/fixture.js'){res.setHeader('Content-Type','text/javascript');return res.end(fs.readFileSync(path.join(out,'fixture.js')));}
  if(req.url==='/style.css'){res.setHeader('Content-Type','text/css');return res.end(fs.readFileSync(path.join(root,'dist/assets',cssFile)));}
  res.setHeader('Content-Type','text/html');res.end('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/style.css"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1060}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const stages=page.getByRole('button',{name:/，(收起|展开)进展$/});
  await stages.nth(1).waitFor();
  async function expanded(expected){
   await page.waitForFunction(exp=>JSON.stringify(Array.from(document.querySelectorAll('[aria-expanded]')).map(e=>e.getAttribute('aria-expanded')))==JSON.stringify(exp),expected);
  }
  await expanded(['false','true','false','false']);
  await stages.nth(0).click();await expanded(['true','true','false','false']);
  await page.evaluate(()=>window.setTaskState({phase:'parse-download',current_step:'正在解析第11集，等待接口返回',stage_logs:{'parse-download':['正在解析第11集，等待接口返回']}}));
  await expanded(['false','false','true','false']);
  await page.evaluate(()=>window.setTaskState({current_step:'正在下载第11集：已接收 5.0 MB / 20.0 MB（25%）',parsed_episodes:[11],stage_logs:{'parse-download':['正在解析第11集，等待接口返回','第11集解析返回名称：隔离验证剧-第11集','正在连接第11集的视频下载地址，等待服务器响应']}}));
  await page.getByText('当前动作：正在下载第11集：已接收 5.0 MB / 20.0 MB（25%）',{exact:true}).first().waitFor();
  await page.screenshot({path:path.join(out,'stage3-progress.png'),fullPage:true});
  await stages.nth(0).click();
  await page.evaluate(()=>window.setTaskState({current_step:'正在下载第11集：已接收 10.0 MB / 20.0 MB（50%）'}));
  await expanded(['true','false','true','false']);
  await page.getByRole('button',{name:'停止脚本',exact:true}).waitFor();
  await page.evaluate(()=>window.setTaskState({phase:'verify-download',current_step:'正在校验第11集视频',stage_logs:{'verify-download':['正在校验第11集视频']}}));
  await expanded(['false','false','false','true']);
  await page.evaluate(()=>window.setTaskState({status:'succeeded',phase:'completed',complete:true,current_step:'任务完成'}));
  await expanded(['false','false','false','false']);
  await stages.nth(2).click();await expanded(['false','false','true','false']);
  await page.evaluate(()=>window.setTaskState({status:'running',phase:'collect-links',current_step:'正在补采第2集',stage_states:{'read-task':'done','collect-links':'running','parse-download':'failed','verify-download':'pending'},parsed_episodes:[1],downloaded_episodes:[1],verified_count:1}));
  await expanded(['false','true','false','false']);
  await page.getByText('已下载 1 集',{exact:true}).waitFor();
  await page.getByText('已校验 1 集',{exact:true}).waitFor();
  assert.equal(await page.getByText('任务完成后请手动删除微信中的剧名和卡片',{exact:true}).count(),0);
  await page.evaluate(()=>window.setTaskState({phase:'parse-download',stage_states:{'read-task':'done','collect-links':'done','parse-download':'running','verify-download':'pending'}}));
  await expanded(['false','false','true','false']);
  await page.evaluate(()=>window.setTaskState({status:'failed',phase:'cleanup-task',complete:true,cleanup_pending:true,cleanup_state:'failed',cleanup_error:'聊天身份未确认，卡片已删除、剧名保留',current_step:'视频校验已通过，微信任务清理未完成，已停止队列',downloaded_episodes:Array.from({length:48},(_,i)=>i+1),verified_count:48,parsed_episodes:Array.from({length:48},(_,i)=>i+1),task:{task_label:'#隔离验证剧',drama_name:'隔离验证剧',chat_name:'昨天'},tasks:[{task_label:'#尚未处理',chat_name:'昨天'},{task_label:'#隔离验证剧',chat_name:'昨天'}],current_task_index:1,completed_tasks:[],stage_states:{'read-task':'running','collect-links':'done','parse-download':'done','verify-download':'failed'},stage_logs:{'cleanup-task':['正在重新核对聊天顶部名称']}}));
  await expanded(['false','false','false','false']);
  assert.equal(await page.getByText('进行中',{exact:true}).count(),0);
  assert.equal(await page.getByText('失败',{exact:true}).count(),0);
  assert.equal(await page.getByText('已完成',{exact:true}).count(),4);
  await page.getByRole('button',{name:'重试微信清理',exact:true}).waitFor();
  await page.getByText('聊天 待重新核对',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('任务已完成',{exact:true}).count(),0);
  await page.screenshot({path:path.join(out,'cleanup-retry.png'),fullPage:true});
  await page.evaluate(()=>window.setTaskState({status:'running',phase:'cleanup-task',cleanup_state:'running',current_step:'正在删除已核对的剧名标签'}));
  await expanded(['false','false','false','false']);
  await page.getByText('当前动作：正在删除已核对的剧名标签',{exact:true}).waitFor();
  await page.getByRole('button',{name:'停止脚本',exact:true}).waitFor();
  await page.evaluate(()=>window.setTaskState({status:'stopped',cleanup_state:'pending'}));
  assert.equal(await page.getByText('进行中',{exact:true}).count(),0);
  await page.evaluate(()=>window.setTaskState({task_count:0,current_task_index:-1}));
  assert.equal(await page.getByText('0',{exact:true}).count(),0);
  await page.evaluate(()=>window.setTaskState({status:'failed',phase:'parse-download',resume_phase:'parse-download',complete:false,cleanup_pending:false,cleanup_state:'pending',expected_count:50,verified_count:49,missing_video_episodes:[47],current_step:'第47集下载未完成'}));
  await page.getByRole('button',{name:'继续解析下载',exact:true}).waitFor();
  await page.getByText('待完成 47',{exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'resume-episode47.png'),fullPage:true});
  await page.evaluate(()=>window.setTaskState({phase:'verify-download',resume_phase:'verify-download'}));
  await page.getByRole('button',{name:'继续校验视频',exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({passed:true,checks:['only active stage opens','manual history opens','phase change collapses previous stages','live byte progress visible','manual history survives progress update','stop control visible','completion collapses all','completed history can reopen','repair stage uses explicit state','live saved and verified counters','cleanup wording matches automatic queue','failed cleanup preserves four video stages','terminal state has no spinner','older task is not falsely completed','date alias is not displayed as chat','cleanup retry has specific action','cleanup stop preserves video result','zero task count does not render orphan text','download retry names its stage and only missing episode','verification retry names its stage'],errors},null,2));
  console.log('PASS: 20 UI interaction checks; screenshot: '+path.join(out,'stage3-progress.png'));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
