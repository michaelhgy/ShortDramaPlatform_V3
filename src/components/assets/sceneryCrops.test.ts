import assert from 'node:assert/strict';
import { test } from 'node:test';
import { initialCrops, validCrops, sceneryOutputCount, sceneryTimeSummary } from './sceneryCrops.ts';
import type { SceneryDetail } from '../../api/scenery.ts';

test('批量默认按各自尺寸分配：竖版三份，横版一份，偶数像素且不越界', () => {
  for (const [width,height,count] of [[720,1280,3],[1081,1921,3],[1920,1080,1],[640,360,1],[800,800,1]]) {
    const crops=initialCrops(width,height,'auto');
    assert.equal(crops.length,count);assert.ok(validCrops(crops,{width,height}));
    assert.equal(crops[0].width,Math.floor(width/2)*2);
    assert.ok(crops.every((c,i)=>!i||c.y>=crops[i-1].y+crops[i-1].height));
  }
});

test('每条两份与三份支持不同源尺寸，极小源不能提交无效区域', () => {
  for(const count of [2,3] as const) {
    for(const [width,height] of [[360,640],[640,360]]) {
      const crops=initialCrops(width,height,count);assert.equal(crops.length,count);assert.ok(validCrops(crops,{width,height}));
    }
  }
  assert.equal(validCrops(initialCrops(16,90,'auto'),{width:16,height:90}),false);
});

test('人工区域禁止重复、奇数、越界和竖向，单独调整可保持合法横向区域', () => {
  const source={width:720,height:1280},crops=initialCrops(720,1280,'auto');
  assert.ok(validCrops([{...crops[0],height:400},...crops.slice(1)],source));
  assert.equal(validCrops([crops[0],crops[0]],source),false);
  for(const patch of [{x:1},{y:1200},{width:30},{height:800}]) assert.equal(validCrops([{...crops[0],...patch}],source),false);
});

test('横屏一份保留完整画面，手动两份仍可裁切，方形保留已有横向取景',()=>{
  for(const [width,height] of [[1920,1080],[640,480],[1080,1000]]) {
    assert.deepEqual(initialCrops(width,height,'auto'),[{x:0,y:0,width,height}]);
    assert.deepEqual(initialCrops(width,height,1),[{x:0,y:0,width,height}]);
    assert.equal(initialCrops(width,height,2).length,2);
  }
  assert.equal(initialCrops(800,800,'auto')[0].height,600);
});

test('最终份数按画面区域乘时间段计算，说明明确时间与画面布局',()=>{
  const source={duration:60,time_segments:[{start_frame:0,frames:570},{start_frame:570,frames:720},{start_frame:1290,frames:510}]} as SceneryDetail;
  const crops=initialCrops(360,640,'auto');assert.equal(sceneryOutputCount(source,crops),9);
  assert.equal(sceneryTimeSummary(source),'时间切成 3 段，每段 17.0—24.0 秒');
  assert.equal(sceneryTimeSummary({...source,duration:25,time_segments:[{start_frame:0,frames:750}]}),'保留整段 25.0 秒');
});
