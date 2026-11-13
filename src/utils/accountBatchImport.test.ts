import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseAccountBatch } from './accountBatchImport.ts';
import type { TheaterBusinessItem } from '../assetsTypes';

const theaters: TheaterBusinessItem[] = [
  { id: 'real-theater-id', name: '青柠剧场', status: '启用', defaultCommissionRate: 70, defaultTaxRate: 6 },
  { id: 'disabled-theater', name: '停用剧场', status: '停用', defaultCommissionRate: 70, defaultTaxRate: 6 },
];

test('账号批量只填三列即可，可选字段留空，状态默认正常', () => {
  assert.deepEqual(parseAccountBatch('测试账号\tchannel-1\t青柠剧场', theaters), [{
    nickname: '测试账号', accountId: 'channel-1', theaterId: 'real-theater-id', theaterName: '青柠剧场',
    subTheaterName: '', status: '正常', revenueCollectorId: '', notes: '',
  }]);
});

test('Excel 中间空列保持位置，空子剧场不会把状态、日期或备注挪到前面', () => {
  const [item] = parseAccountBatch('测试账号\tchannel-1\t青柠剧场\t\t观察\t\t2026/10/1\t备注,保留逗号', theaters);
  assert.equal(item.subTheaterName, '');
  assert.equal(item.status, '观察');
  assert.equal(item.whitelistedDate, undefined);
  assert.equal(item.registeredDate, undefined);
  assert.equal(item.notes, '备注,保留逗号');
});

test('逗号和分号文本的空列也保留，备注不自动补字', () => {
  for (const delimiter of [',', ';']) {
    const [item] = parseAccountBatch(['测试账号', 'channel-1', '青柠剧场', '', '', '2026-10-02', '', ''].join(delimiter), theaters);
    assert.equal(item.subTheaterName, '');
    assert.equal(item.status, '正常');
    assert.equal(item.whitelistedDate, undefined);
    assert.equal(item.registeredDate, undefined);
    assert.equal(item.notes, '');
  }
});

test('昵称、账号 ID 和剧场缺失都报错，不能用默认剧场或后面的列顶替', () => {
  for (const [line, error] of [
    ['\tchannel-1\t青柠剧场', /缺少账号昵称/],
    ['测试账号\t\t青柠剧场', /缺少账号ID/],
    ['测试账号\tchannel-1\t\t专用子剧场', /缺少所属剧场/],
    ['测试账号\tchannel-1', /缺少所属剧场/],
  ] as const) assert.throws(() => parseAccountBatch(line, theaters), error);
});

test('新格式第六列是备注，旧格式忽略退役日期并保留备注', () => {
  const [item] = parseAccountBatch('测试账号\tchannel-1\t青柠剧场\t\t观察\t备注内容', theaters);
  assert.equal(item.notes, '备注内容');
  const [commas] = parseAccountBatch('账号昵称,账号ID,剧场,子剧场,状态,备注\n测试账号,channel-1,青柠剧场,,观察,备注,多个,逗号', theaters);
  assert.equal(commas.notes, '备注,多个,逗号');
  assert.equal(item.revenueCollectorId, '');
  const [legacy] = parseAccountBatch('账号昵称\t账号ID\t剧场\t子剧场\t状态\t报白时间\t注册时间\t备注\n测试账号\tchannel-1\t青柠剧场\t\t观察\t无效旧日期\t无效旧日期\t保留备注', theaters);
  assert.equal(legacy.notes, '保留备注');
  assert.equal(legacy.whitelistedDate, undefined);
  assert.throws(() => parseAccountBatch('测试账号\tchannel-1\t青柠剧场\t\t不正常', theaters), /状态不正确/);
});

test('忽略表头和空行，错误行号对应实际粘贴内容', () => {
  const rows = parseAccountBatch('\n账号昵称\t账号ID\t剧场\t子剧场\t状态\t报白时间\t注册时间\t备注\r\n测试账号\tchannel-1\t青柠剧场\t\t\t\t\t', theaters);
  assert.equal(rows.length, 1);
  assert.throws(() => parseAccountBatch('账号昵称\t账号ID\t剧场\n\n\tchannel-1\t青柠剧场', theaters), /第 3 行缺少账号昵称/);
  assert.throws(() => parseAccountBatch('账号昵称\t账号ID\t剧场', theaters), /至少一行/);
});

test('所属剧场必须已存在且启用，不用假 ID 接受未知剧场', () => {
  for (const name of ['未知剧场', '停用剧场']) assert.throws(() => parseAccountBatch(`测试账号\tchannel-1\t${name}`, theaters), /不存在或已停用/);
});
