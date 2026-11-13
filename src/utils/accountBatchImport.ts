import type { AccountBusinessItem, AccountBusinessStatus, TheaterBusinessItem } from '../assetsTypes';

const STATUSES: AccountBusinessStatus[] = ['正常', '观察', '限流', '二限', '实名', '封禁', '停用', '注销'];

export function parseAccountBatch(text: string, theaters: TheaterBusinessItem[]): Omit<AccountBusinessItem, 'id'>[] {
  const results: Omit<AccountBusinessItem, 'id'>[] = [];
  let firstRow = true;
  let legacyColumns: boolean | undefined;
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line.trim()) continue;
    // Choose the table delimiter first. Empty cells, including the leading
    // nickname and cells between optional fields, must retain their positions.
    const delimiter = line.includes('\t') ? '\t' : line.includes(',') ? ',' : line.includes(';') ? ';' : null;
    const parts = (delimiter ? line.split(delimiter) : line.trim().split(/\s{2,}/)).map((part) => part.trim());
    const [nickname = '', accountId = '', theaterName = '', subTheaterName = '', rawStatus = ''] = parts;
    const isHeader = /^(账号昵称|昵称)$/.test(nickname) && /^(账号ID|平台ID|ID)$/i.test(accountId) && /^(所属剧场|剧场)$/.test(theaterName);
    if (firstRow && isHeader) { legacyColumns = parts.includes('报白时间') || parts.includes('注册时间'); firstRow = false; continue; }
    firstRow = false;
    const row = `第 ${index + 1} 行`;
    if (!nickname) throw new Error(`${row}缺少账号昵称`);
    if (!accountId) throw new Error(`${row}缺少账号ID，账号ID不能为空`);
    if (!theaterName) throw new Error(`${row}缺少所属剧场，剧场不能为空`);
    const theater = theaters.find((item) => item.name === theaterName && item.status === '启用');
    if (!theater) throw new Error(`${row}所属剧场“${theaterName}”不存在或已停用，请先在剧场管理中创建或启用`);
    if (rawStatus && !STATUSES.includes(rawStatus as AccountBusinessStatus)) throw new Error(`${row}账号状态不正确，请填写正常、观察、限流、二限、实名、封禁、停用或注销`);
    // Headerless old eight-column exports can still be pasted. A new header
    // fixes the layout, so commas in new-format notes never shift its columns.
    const looksLikeOldDate = (value: string) => !value || value === '未报白'
      || /^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/.test(value) || /^\d+(?:\.\d+)?$/.test(value);
    const isLegacyRow = legacyColumns ?? (parts.length >= 8 && parts.slice(5, 7).every(looksLikeOldDate));
    results.push({
      nickname, accountId, theaterId: theater.id, theaterName,
      subTheaterName,
      status: (rawStatus || '正常') as AccountBusinessStatus,
      revenueCollectorId: '',
      notes: parts.slice(isLegacyRow ? 7 : 5).join(delimiter || '  ').trim(),
    });
  }
  if (!results.length) throw new Error('请粘贴至少一行账号数据，昵称、账号ID和剧场必须填写');
  return results;
}
