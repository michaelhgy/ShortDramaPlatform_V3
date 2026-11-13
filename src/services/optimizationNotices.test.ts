import assert from 'node:assert/strict';
import test from 'node:test';
import { buildOptimizationDefinitions, createOptimizationReasonCounts, matchOptimizationAnalysis, optimizationAnalysisBody, OPTIMIZATION_NOTICE_RULES, getOptimizationAppearance } from '../types/optimizationNotices.ts';
import { summarizeAccountOptimization } from './accountOptimizationSummary.ts';
import type { AccountOptimizationStat } from '../types/shortDramaOps.ts';

test('each provisional analysis matches only its own tag, allowing heading and layout whitespace', () => {
  assert.deepEqual(OPTIMIZATION_NOTICE_RULES.map(rule => rule.tag), ['多次发布', '引导优化', '羊头链接', '未挂链接', '原创优化']);
  for (const rule of OPTIMIZATION_NOTICE_RULES) {
    assert.equal(matchOptimizationAnalysis(rule.analysis), rule.tag);
    assert.equal(matchOptimizationAnalysis(' 作品分析：\n' + rule.analysis.replace(/。/g, '。\n')), rule.tag);
    assert.equal(matchOptimizationAnalysis('作品分析: ' + rule.analysis), rule.tag);
  }
});

test('similar keywords, unknown text and missing analyses are not forced into a known category', () => {
  for (const text of ['', '推荐曝光减少', '开发场景：同质化内容', '作品存在同质化内容，请确认是否原创。', OPTIMIZATION_NOTICE_RULES[0].analysis + '另有其他情况。']) {
    assert.equal(matchOptimizationAnalysis(text), '待归类');
  }
  assert.equal(optimizationAnalysisBody('作品分析：第一行\n第二行'), '第一行\n第二行');
});

test('originality and repeated publishing remain different; only originality contributes to homogeneous rate', () => {
  const stats = [{ totalVideos: 20, optimizedVideos: 10, reasonCounts: { 多次发布: 9, 原创优化: 1 } }] as unknown as AccountOptimizationStat[];
  const summary = summarizeAccountOptimization(stats);
  assert.equal(summary.homogeneousCount, 1);
  assert.equal(summary.homogeneousRate, 5);
  assert.equal(summary.avgOptRate, 50);
  assert.equal(summary.topReason, '多次发布');
});

test('tag palettes follow the reference while unknown tags remain neutral', () => {
  const expected = { 多次发布: '#3B82F6', 引导优化: '#F59E0B', 羊头链接: '#DC2626', 未挂链接: '#EC4899', 原创优化: '#8B5CF6', 待归类: '#64748B' };
  for (const [tag, color] of Object.entries(expected)) {
    assert.equal(getOptimizationAppearance(tag).color, color);
    assert.equal(getOptimizationAppearance(tag).severity, '未判定');
    assert.equal(getOptimizationAppearance(tag).impactNotice, '');
  }
  assert.equal(getOptimizationAppearance('新类型').color, '#64748B');
});


test('saved free labels override defaults exactly and definitions follow reassigned original text', () => {
  const original = OPTIMIZATION_NOTICE_RULES[0].analysis;
  const mappings = [{analysis: original, tag: '同质化'}];
  assert.equal(matchOptimizationAnalysis('作品分析：\n' + original, mappings), '同质化');
  assert.equal(matchOptimizationAnalysis(original + '补充说明', mappings), '待归类');
  assert.equal(matchOptimizationAnalysis(original, [{analysis: original, tag: '待归类'}]), '待归类');
  const definitions = buildOptimizationDefinitions(mappings, [original]);
  assert.ok(definitions['同质化'].officialNotice.includes(original));
  assert.ok(!definitions['多次发布'].officialNotice.includes(original));
  assert.equal(definitions['同质化'].homogeneous, false);
  assert.equal(buildOptimizationDefinitions()['同质化'], undefined);
  assert.equal(matchOptimizationAnalysis(original), '多次发布');
});

test('arbitrary labels including object property names are safe and counted without renaming', () => {
  for (const tag of ['ALL', '__proto__', 'constructor', '自定义标签']) {
    const mappings = [{analysis:'采集到的新原文',tag}];
    const definitions = buildOptimizationDefinitions(mappings);
    assert.equal(definitions[tag].shortTag, tag);
    const counts = createOptimizationReasonCounts(Object.keys(definitions));
    counts[tag]++;
    assert.equal(counts[tag], 1);
    const summary = summarizeAccountOptimization([{totalVideos:2,optimizedVideos:1,reasonCounts:counts}] as unknown as AccountOptimizationStat[]);
    assert.equal(summary.topReason, tag);
    assert.equal(summary.homogeneousCount, 0);
  }
});


test('label explanations include only collected or saved originals, never unused default wording', () => {
  for (const rule of OPTIMIZATION_NOTICE_RULES) {
    const collected = rule.aliases?.[0] || rule.analysis;
    const definitions = buildOptimizationDefinitions([], [collected, '作品分析：\n' + collected]);
    assert.deepEqual(definitions[rule.tag].analysisTexts, [collected], rule.tag);
    assert.equal(definitions[rule.tag].officialNotice, collected);
    assert.deepEqual(buildOptimizationDefinitions()[rule.tag].analysisTexts, []);
  }
});

test('distinct saved and collected originals under one label remain separate and retain paragraph breaks', () => {
  const saved = '第一段。\n\n第二段。';
  const collected = '另一份实际采集分析。';
  const mappings = [{analysis:saved,tag:'自由标签'},{analysis:collected,tag:'自由标签'}];
  const definitions = buildOptimizationDefinitions(mappings,[collected]);
  assert.deepEqual(definitions['自由标签'].analysisTexts,[collected,saved]);
  assert.ok(definitions['自由标签'].officialNotice.includes(saved));
  assert.deepEqual(buildOptimizationDefinitions([{analysis:saved,tag:'自由标签'}])['自由标签'].analysisTexts,[saved]);
});
