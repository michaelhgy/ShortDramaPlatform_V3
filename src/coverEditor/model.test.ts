import assert from 'node:assert/strict';
import { test } from 'node:test';
import { activeImage, addTemplate, applyTemplate, createProject, deleteVersion, replaceOriginal, resizeTextBox, saveVersion, selectVersion, type CoverTemplate, type CoverVersion, type TextLayer } from './model.ts';
const version = (id: string): CoverVersion => ({ id, image: `render-${id}`, sourceImage: 'original-v1', layers: [], createdAt: '2026-10-26' });

test('两套各保存三张，第四张失败不改变现有封面', () => {
  let p = createProject('original-v1');
  for (const kind of ['drama', 'sheep'] as const) for (let i = 0; i < 3; i++) p = saveVersion(p, kind, version(`${kind}${i}`));
  assert.equal(p.drama.versions.length, 3); assert.equal(p.sheep.versions.length, 3);
  const previous = structuredClone(p);
  assert.throws(() => saveVersion(p, 'drama', version('fourth')), /已保存 3/);
  assert.deepEqual(p, previous);
});

const layer: TextLayer = { id: 'text1', text: '通用标题', styleId: 'style1', x: 40, y: 100, width: 300, height: 120, fontSize: 60, rotation: 0, align: 'center', verticalAlign: 'middle', background: '#000000', backgroundAlpha: 0 };
test('四边调整固定对边，四角独立改变宽高，旋转时保持对角锚点', () => {
  assert.equal(resizeTextBox(layer, 120, 'n', 0, -20).height, 140);
  assert.equal(resizeTextBox(layer, 120, 'n', 0, -20).y, 80);
  assert.equal(resizeTextBox(layer, 120, 's', 0, 20).y, 100);
  assert.equal(resizeTextBox(layer, 120, 'w', -20, 0).x, 20);
  for (const corner of ['nw', 'ne', 'se', 'sw']) {
    const result = resizeTextBox(layer, 120, corner, corner.includes('w') ? -20 : 20, corner.includes('n') ? -30 : 30);
    assert.equal(result.width, 320); assert.equal(result.height, 150); assert.equal(result.fontSize, 60);
  }
  const rotated = { ...layer, rotation: 90 }, result = resizeTextBox(rotated, 120, 'e', 0, 20);
  assert.equal(result.width, 320); assert.equal(result.height, 120); assert.equal(result.y, rotated.y + 10);
});
test('通用模板最多五个，套用尺寸适配且不改变模板本身', () => {
  let templates: CoverTemplate[] = [];
  for (let i = 0; i < 5; i++) templates = addTemplate(templates, { id: `${i}`, name: `模板${i}`, width: 540, height: 720, layers: [layer], createdAt: '2026-10-26' });
  const previous = structuredClone(templates);
  assert.throws(() => addTemplate(templates, { ...templates[0], id: 'six' }), /已保存 5/);
  const applied = applyTemplate(templates[0], 1080, 1440);
  assert.equal(applied[0].x, 80); assert.equal(applied[0].y, 200);
  assert.equal(applied[0].width, 600); assert.equal(applied[0].height, 240); assert.equal(applied[0].fontSize, 120);
  applied[0].text = '新剧微调'; assert.deepEqual(templates, previous);
});
test('羊头首次复制后独立，替换原图保留修改版和修改版底图', () => {
  let p = replaceOriginal(createProject(), 'drama', 'original-v1');
  assert.equal(p.sheep.original, 'original-v1');
  p = saveVersion(p, 'drama', version('d1'), true);
  p = replaceOriginal(p, 'drama', 'original-v2');
  assert.equal(p.sheep.original, 'original-v1'); assert.equal(p.drama.activeId, 'original');
  assert.equal(p.drama.versions[0].sourceImage, 'original-v1');
  p = replaceOriginal(p, 'sheep', 'sheep-own');
  assert.equal(p.drama.original, 'original-v2'); assert.equal(p.sheep.original, 'sheep-own');
});
test('查看与选用分开，保存默认不改变使用状态，选用只作用于本套', () => {
  let p = saveVersion(createProject('original-v1'), 'drama', version('d1'));
  assert.equal(activeImage(p.drama), 'original-v1');
  p = selectVersion(p, 'drama', 'd1');
  assert.equal(activeImage(p.drama), 'render-d1'); assert.equal(activeImage(p.sheep), 'original-v1');
  assert.throws(() => selectVersion(p, 'sheep', 'd1'), /不存在/);
});
test('删除在用版本回到本套原图，删除其他版本保持在用项，禁止删原图', () => {
  let p = saveVersion(createProject('original-v1'), 'drama', version('d1'), true);
  p = saveVersion(p, 'drama', version('d2'));
  p = deleteVersion(p, 'drama', 'd2'); assert.equal(p.drama.activeId, 'd1');
  p = deleteVersion(p, 'drama', 'd1'); assert.equal(activeImage(p.drama), 'original-v1');
  assert.throws(() => deleteVersion(p, 'drama', 'original'), /不能/);
});
test('满额可明确覆盖，保持版本编号和选用；不能静默覆盖不存在的版本', () => {
  let p = createProject('original-v1');
  for (const id of ['one', 'two', 'three']) p = saveVersion(p, 'sheep', version(id), id === 'two');
  p = saveVersion(p, 'sheep', { ...version('replacement'), image: 'new-render' }, false, 'two');
  assert.equal(p.sheep.versions.length, 3); assert.equal(p.sheep.activeId, 'two'); assert.equal(activeImage(p.sheep), 'new-render');
  assert.throws(() => saveVersion(p, 'sheep', version('bad'), false, 'missing'), /不存在/);
  assert.throws(() => saveVersion(p, 'drama', { ...version('bad'), sourceImage: '' }), /上传原图/);
});
