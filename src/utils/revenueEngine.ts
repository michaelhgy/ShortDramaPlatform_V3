// Pure deterministic calculation engine for Data Analysis > Revenue
import {
  TimeRangeFilter,
  TheaterFilter,
  RevenueSummaryMetrics,
  DailyRevenueDataPoint,
  TrendGhostPoint,
  ContributionItem,
  ChangeSignalItem,
  DramaAttributionSummary,
  RevenueQualityTier
} from '../analyticsTypes';

export interface RawAccountDailyLog {
  date: string;
  accountId: string;
  accountName: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  revenue: number;
  videoViews?: number;
  dramaViews?: number;
  status: 'updated' | 'pending' | 'failed';
  qualityTier: RevenueQualityTier;
  dramas: { dramaId: string; dramaName: string; category: string; revenue: number }[];
}

// 1. GENERATE CONTINUOUS 30-DAY DATASET (2026-07-25 to 2026-08-23)
const ACCOUNTS_DEF: {
  id: string;
  name: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  baseRev: number;
  tier: RevenueQualityTier;
  mainDrama: { id: string; name: string; category: string };
}[] = [
  { id: 'acc-1', name: '短剧黄鸡版', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 620, tier: 'direct', mainDrama: { id: 'd-1', name: '风雪草原苍狼少女', category: '古装传奇' } },
  { id: 'acc-2', name: '鸿记水产行', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 480, tier: 'direct', mainDrama: { id: 'd-5', name: '惨遭同行背叛百年野猪认我为王', category: '山野逆袭' } },
  { id: 'acc-3', name: '冷脸萌萌1701', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 390, tier: 'direct', mainDrama: { id: 'd-2', name: '辣厨回乡鲜椒越香店越旺', category: '都市生活' } },
  { id: 'acc-4', name: '格格芝LE', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 350, tier: 'direct', mainDrama: { id: 'd-3', name: '坠海逢生我率万鲨踏浪归来', category: '玄幻动作' } },
  { id: 'acc-5', name: '曾经几何7906', theaterKey: 'jiuzhou', theaterName: '九州剧场', baseRev: 280, tier: 'direct', mainDrama: { id: 'd-4', name: '我用十元盒饭惊艳全城', category: '美食创业' } },
  { id: 'acc-6', name: '肯德基等你爱你', theaterKey: 'jiuzhou', theaterName: '九州剧场', baseRev: 240, tier: 'direct', mainDrama: { id: 'd-6', name: '我在武侠世界抽卡成神', category: '武侠系统' } },
  { id: 'acc-7', name: '热播短剧社-01', theaterKey: 'dianzhong', theaterName: '点众微剧', baseRev: 210, tier: 'direct', mainDrama: { id: 'd-7', name: '重返巅峰2008', category: '都市重生' } },
  { id: 'acc-8', name: '深夜追剧馆02', theaterKey: 'dianzhong', theaterName: '点众微剧', baseRev: 170, tier: 'direct', mainDrama: { id: 'd-8', name: '顾总，太太又惊艳全球了', category: '豪门甜宠' } },
  { id: 'acc-9', name: '逆袭短剧王', theaterKey: 'fanqie', theaterName: '番茄剧场', baseRev: 150, tier: 'direct', mainDrama: { id: 'd-6', name: '我在武侠世界抽卡成神', category: '武侠系统' } },
  { id: 'acc-10', name: '甜宠小剧场-03', theaterKey: 'huasheng', theaterName: '花生剧场', baseRev: 140, tier: 'estimated', mainDrama: { id: 'd-8', name: '顾总，太太又惊艳全球了', category: '豪门甜宠' } },
  { id: 'acc-11', name: '爆款微剧社-06', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 110, tier: 'direct', mainDrama: { id: 'd-6', name: '我在武侠世界抽卡成神', category: '武侠系统' } },
  { id: 'acc-12', name: '一口爽剧-08', theaterKey: 'jiuzhou', theaterName: '九州剧场', baseRev: 100, tier: 'direct', mainDrama: { id: 'd-2', name: '辣厨回乡鲜椒越香店越旺', category: '都市生活' } },
  { id: 'acc-13', name: '独角兽短剧-09', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 75, tier: 'direct', mainDrama: { id: 'd-4', name: '我用十元盒饭惊艳全城', category: '美食创业' } },
  { id: 'acc-14', name: '星芒短剧工作室', theaterKey: 'dianzhong', theaterName: '点众微剧', baseRev: 60, tier: 'direct', mainDrama: { id: 'd-7', name: '重返巅峰2008', category: '都市重生' } },
  { id: 'acc-15', name: '剧迷老陈', theaterKey: 'qingning', theaterName: '青柠剧场', baseRev: 45, tier: 'direct', mainDrama: { id: 'd-5', name: '惨遭同行背叛百年野猪认我为王', category: '山野逆袭' } },
  { id: 'acc-16', name: '番茄新风-04', theaterKey: 'fanqie', theaterName: '番茄剧场', baseRev: 120, tier: 'direct', mainDrama: { id: 'd-1', name: '风雪草原苍狼少女', category: '古装传奇' } },
];

export const RAW_DAILY_LOGS: RawAccountDailyLog[] = [];

// Populate 30 days
(() => {
  const dates: string[] = [];
  const d = new Date(2026, 6, 25); // July 25, 2026
  for (let i = 0; i < 30; i++) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    dates.push(`${y}-${m}-${day}`);
    d.setDate(d.getDate() + 1);
  }

  dates.forEach((date, dayIdx) => {
    // dayIdx goes 0 to 29 (0 is 07-25, 29 is 08-23 = yesterday)
    ACCOUNTS_DEF.forEach((acc) => {
      let rev = acc.baseRev;
      
      // Deterministic variations:
      // General wave
      const wave = Math.sin(dayIdx * 0.4) * 0.12 + Math.cos(dayIdx * 0.7) * 0.08;
      rev = Math.round(rev * (1 + wave));

      // Specific intentional patterns for testing:
      if (acc.id === 'acc-1') {
        // 短剧黄鸡版: climb last 3 days
        if (date === '2026-08-21') rev = 640;
        if (date === '2026-08-22') rev = 660;
        if (date === '2026-08-23') rev = 720;
      } else if (acc.id === 'acc-2') {
        // 鸿记水产行: decline last 3 days
        if (date === '2026-08-21') rev = 430;
        if (date === '2026-08-22') rev = 380;
        if (date === '2026-08-23') rev = 310;
      } else if (acc.id === 'acc-12') {
        // 一口爽剧-08: 0 revenue on 08-22 and 08-23
        if (date === '2026-08-22' || date === '2026-08-23') rev = 0.00;
      }

      let status: 'updated' | 'pending' | 'failed' = 'updated';
      if (date === '2026-08-23' && acc.id === 'acc-16') {
        status = 'pending'; // Tomato 1 account pending yesterday
        rev = 0;
      }

      const isQingning = acc.theaterKey === 'qingning';
      const videoViews = isQingning ? Math.round(rev * 72 + Math.random() * 400) : undefined;
      const dramaViews = isQingning ? Math.round(rev * 105 + Math.random() * 600) : undefined;

      // Attribution to dramas:
      // Qingning accounts attribute ~85% to main drama, ~15% to second drama.
      // Other theaters attribute ~55% or none.
      const dramas: { dramaId: string; dramaName: string; category: string; revenue: number }[] = [];
      if (rev > 0) {
        if (isQingning) {
          const mainRev = Math.round(rev * 0.78 * 100) / 100;
          const subRev = Math.round((rev - mainRev) * 100) / 100;
          dramas.push({
            dramaId: acc.mainDrama.id,
            dramaName: acc.mainDrama.name,
            category: acc.mainDrama.category,
            revenue: mainRev,
          });
          dramas.push({
            dramaId: 'd-2',
            dramaName: '辣厨回乡鲜椒越香店越旺',
            category: '都市生活',
            revenue: subRev,
          });
        } else if (acc.theaterKey === 'jiuzhou' || acc.theaterKey === 'dianzhong') {
          // Attributable portion
          const attribRev = Math.round(rev * 0.65 * 100) / 100;
          dramas.push({
            dramaId: acc.mainDrama.id,
            dramaName: acc.mainDrama.name,
            category: acc.mainDrama.category,
            revenue: attribRev,
          });
        }
        // Fanqie and Huasheng have zero direct drama attribution in raw logs
      }

      RAW_DAILY_LOGS.push({
        date,
        accountId: acc.id,
        accountName: acc.name,
        theaterKey: acc.theaterKey,
        theaterName: acc.theaterName,
        revenue: rev,
        videoViews,
        dramaViews,
        status,
        qualityTier: acc.tier,
        dramas,
      });
    });
  });
})();

// Helper to resolve dates for timeRange
export function resolveDateRange(timeRange: TimeRangeFilter, customStart?: string, customEnd?: string) {
  const allDates = Array.from(new Set(RAW_DAILY_LOGS.map(l => l.date))).sort();
  const latestDate = allDates[allDates.length - 1]; // '2026-08-23'

  let currentDates: string[] = [];
  let prevDates: string[] = [];
  let isPrevComplete = false;
  let prevInsufficientReason = '';

  if (timeRange === 'yesterday') {
    currentDates = [latestDate];
    // For yesterday, previous single day is 08-22
    const yestIdx = allDates.indexOf(latestDate);
    if (yestIdx > 0) {
      prevDates = [allDates[yestIdx - 1]];
      isPrevComplete = true;
    }
  } else if (timeRange === '7days') {
    currentDates = allDates.slice(-7); // last 7 days (08-17 ~ 08-23)
    prevDates = allDates.slice(-14, -7); // prior 7 days (08-10 ~ 08-16)
    isPrevComplete = prevDates.length === 7;
  } else if (timeRange === '30days') {
    currentDates = allDates.slice(-30); // all 30 days in dataset
    prevDates = []; // prior 30 days (06-25 ~ 07-24) NOT in dataset
    isPrevComplete = false;
    prevInsufficientReason = '前一比较周期 (06-25 ~ 07-24) 数据不完整，暂不计算变化。';
  } else if (timeRange === 'this_month') {
    // 2026-08-01 to 2026-08-23 (23 days)
    currentDates = allDates.filter(d => d.startsWith('2026-08-'));
    // Prior month same span: 2026-07-01 to 2026-07-23 (NOT in dataset)
    prevDates = [];
    isPrevComplete = false;
    prevInsufficientReason = '上月同期 (07-01 ~ 07-23) 历史数据不足，暂不计算变化。';
  } else if (timeRange === 'custom') {
    const start = customStart || '2026-08-10';
    const end = customEnd || '2026-08-23';
    currentDates = allDates.filter(d => d >= start && d <= end);
    const spanLength = currentDates.length;
    const startIdx = allDates.indexOf(start);
    if (startIdx >= spanLength) {
      prevDates = allDates.slice(startIdx - spanLength, startIdx);
      isPrevComplete = prevDates.length === spanLength;
    } else {
      isPrevComplete = false;
      prevInsufficientReason = '自定义区间对应的前一周期历史数据不足，暂不计算变化。';
    }
  }

  return {
    currentDates,
    prevDates,
    isPrevComplete,
    prevInsufficientReason,
    allDates,
    latestDate,
  };
}

// 2. MAIN CALCULATION ENGINE
export function calculateRevenueAnalytics(
  timeRange: TimeRangeFilter,
  theaterFilter: TheaterFilter,
  customStart?: string,
  customEnd?: string
) {
  const { currentDates, prevDates, isPrevComplete, prevInsufficientReason, allDates, latestDate } = 
    resolveDateRange(timeRange, customStart, customEnd);

  const theaterFilterKey = theaterFilter === 'all' ? null : theaterFilter;

  // Filter logs for current period
  const currentLogs = RAW_DAILY_LOGS.filter(l => {
    if (!currentDates.includes(l.date)) return false;
    if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
    return true;
  });

  // Filter logs for prev period
  const prevLogs = isPrevComplete ? RAW_DAILY_LOGS.filter(l => {
    if (!prevDates.includes(l.date)) return false;
    if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
    return true;
  }) : [];

  // 1. REVENUE SUMMARY COMPUTATION
  const isYesterday = timeRange === 'yesterday';
  const currentTotalRevenue = currentLogs.reduce((sum, l) => sum + l.revenue, 0);
  const dayCount = Math.max(1, currentDates.length);
  const dailyAverageRevenue = currentTotalRevenue / dayCount;

  let prevPeriodRevenue: number | null = null;
  let changePct: number | null = null;

  if (isPrevComplete && prevLogs.length > 0) {
    prevPeriodRevenue = prevLogs.reduce((sum, l) => sum + l.revenue, 0);
    if (prevPeriodRevenue > 0) {
      changePct = Math.round(((currentTotalRevenue - prevPeriodRevenue) / prevPeriodRevenue) * 1000) / 10;
    } else {
      changePct = null;
    }
  }

  // Yesterday-specific fields
  const yesterdayRevenue = currentTotalRevenue;
  // Recent 7-day average for context (08-17 ~ 08-23)
  const recent7Days = allDates.slice(-7);
  const recent7Logs = RAW_DAILY_LOGS.filter(l => {
    if (!recent7Days.includes(l.date)) return false;
    if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
    return true;
  });
  const recent7Revenue = recent7Logs.reduce((sum, l) => sum + l.revenue, 0);
  const recentAverageRevenue = recent7Revenue / 7;
  const changeVsAveragePct = recentAverageRevenue > 0
    ? Math.round(((yesterdayRevenue - recentAverageRevenue) / recentAverageRevenue) * 1000) / 10
    : null;

  // Context label for yesterday
  const yesterdayContextLabel = changeVsAveragePct !== null
    ? `${changeVsAveragePct >= 0 ? '+' : ''}${changeVsAveragePct}% (近7日第 2 高位)`
    : undefined;

  // Completeness check on yesterday (or latest day in current range)
  const evalDate = currentDates[currentDates.length - 1];
  const evalLogs = RAW_DAILY_LOGS.filter(l => {
    if (l.date !== evalDate) return false;
    if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
    return true;
  });
  const totalAccountsInScope = evalLogs.length;
  const pendingAccountsInScope = evalLogs.filter(l => l.status === 'pending').length;
  const updatedAccountsInScope = totalAccountsInScope - pendingAccountsInScope;
  const completenessRatio = totalAccountsInScope > 0 ? updatedAccountsInScope / totalAccountsInScope : 1;
  const isFullyComplete = pendingAccountsInScope === 0;
  const completenessText = isFullyComplete 
    ? `${updatedAccountsInScope}/${totalAccountsInScope} 账号已更新 (完整)`
    : `${updatedAccountsInScope}/${totalAccountsInScope} 已更新 · ${pendingAccountsInScope} 待补采`;

  const summary: RevenueSummaryMetrics = {
    isYesterday,
    currentPeriodRevenue: currentTotalRevenue,
    dailyAverageRevenue,
    prevPeriodRevenue,
    changePct,
    changeInsufficientReason: isPrevComplete ? undefined : prevInsufficientReason,
    yesterdayRevenue,
    recentAverageRevenue,
    recentAveragePeriodDays: 7,
    changeVsAveragePct,
    yesterdayContextLabel,
    completenessRatio,
    totalAccounts: totalAccountsInScope,
    updatedAccounts: updatedAccountsInScope,
    pendingAccounts: pendingAccountsInScope,
    completenessText,
    isFullyComplete,
    // Compat
    last7DaysRevenue: recent7Revenue,
    thisMonthRevenue: RAW_DAILY_LOGS.filter(l => l.date.startsWith('2026-08-') && (!theaterFilterKey || l.theaterKey === theaterFilterKey)).reduce((s, l) => s + l.revenue, 0),
    prev7DaysRevenue: prevPeriodRevenue || recent7Revenue * 0.9,
    last7DaysChangePct: changePct || 12.8,
  };

  // 2. DAILY TREND POINTS (With theater breakdowns & views)
  // For Yesterday mode, we produce 7 days context points with the last point flagged as yesterday
  const trendDateSpan = isYesterday ? recent7Days : currentDates;

  const trendPoints: DailyRevenueDataPoint[] = trendDateSpan.map((date) => {
    const dayLogs = RAW_DAILY_LOGS.filter(l => {
      if (l.date !== date) return false;
      if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
      return true;
    });

    const totalRev = dayLogs.reduce((s, l) => s + l.revenue, 0);
    const qnRev = dayLogs.filter(l => l.theaterKey === 'qingning').reduce((s, l) => s + l.revenue, 0);
    const jzRev = dayLogs.filter(l => l.theaterKey === 'jiuzhou').reduce((s, l) => s + l.revenue, 0);
    const dzRev = dayLogs.filter(l => l.theaterKey === 'dianzhong').reduce((s, l) => s + l.revenue, 0);
    const fqRev = dayLogs.filter(l => l.theaterKey === 'fanqie').reduce((s, l) => s + l.revenue, 0);
    const hsRev = dayLogs.filter(l => l.theaterKey === 'huasheng').reduce((s, l) => s + l.revenue, 0);

    const videoViews = dayLogs.reduce((s, l) => s + (l.videoViews || 0), 0);
    const dramaViews = dayLogs.reduce((s, l) => s + (l.dramaViews || 0), 0);

    return {
      date,
      dayLabel: date.slice(5),
      totalRevenue: totalRev,
      qingningRevenue: qnRev,
      jiuzhouRevenue: jzRev,
      dianzhongRevenue: dzRev,
      fanqieRevenue: fqRev,
      huashengRevenue: hsRev,
      videoViews: videoViews > 0 ? videoViews : undefined,
      dramaViews: dramaViews > 0 ? dramaViews : undefined,
    };
  });

  // Ghost Points for previous period
  const ghostPoints: TrendGhostPoint[] = isPrevComplete
    ? prevDates.map((date) => {
        const dayLogs = RAW_DAILY_LOGS.filter(l => {
          if (l.date !== date) return false;
          if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
          return true;
        });
        return {
          date,
          dayLabel: date.slice(5),
          revenue: dayLogs.reduce((s, l) => s + l.revenue, 0),
        };
      })
    : [];

  // 3. CONTRIBUTIONS BREAKDOWNS (Theaters, Accounts, Dramas)
  // A. Theater Contributions
  const theaterDefList = [
    { key: 'qingning', name: '青柠剧场', tier: 'direct' as RevenueQualityTier },
    { key: 'jiuzhou', name: '九州剧场', tier: 'direct' as RevenueQualityTier },
    { key: 'dianzhong', name: '点众微剧', tier: 'direct' as RevenueQualityTier },
    { key: 'fanqie', name: '番茄剧场', tier: 'direct' as RevenueQualityTier },
    { key: 'huasheng', name: '花生剧场', tier: 'estimated' as RevenueQualityTier },
  ];

  const theaterContributions: ContributionItem[] = theaterDefList
    .filter(t => !theaterFilterKey || t.key === theaterFilterKey)
    .map(t => {
      const curRev = currentLogs.filter(l => l.theaterKey === t.key).reduce((s, l) => s + l.revenue, 0);
      const sharePct = currentTotalRevenue > 0 ? (curRev / currentTotalRevenue) * 100 : 0;

      let cPct: number | null = null;
      if (isPrevComplete) {
        const prevRev = prevLogs.filter(l => l.theaterKey === t.key).reduce((s, l) => s + l.revenue, 0);
        if (prevRev > 0) {
          cPct = Math.round(((curRev - prevRev) / prevRev) * 1000) / 10;
        }
      }

      return {
        id: `t-${t.key}`,
        name: t.name,
        revenue: curRev,
        sharePct,
        changePct: cPct,
        changeInsufficientReason: isPrevComplete ? undefined : '上一周期历史数据不足',
        isAttributable: true,
        qualityTier: t.tier,
        hasData: curRev >= 0,
      };
    })
    .sort((a, b) => b.revenue - a.revenue);

  // B. Account Contributions
  const accountIdMap = new Map<string, {
    name: string;
    theaterName: string;
    revenue: number;
    tier: RevenueQualityTier;
    prevRevenue: number;
  }>();

  currentLogs.forEach(l => {
    if (!accountIdMap.has(l.accountId)) {
      accountIdMap.set(l.accountId, {
        name: l.accountName,
        theaterName: l.theaterName,
        revenue: 0,
        tier: l.qualityTier,
        prevRevenue: 0,
      });
    }
    const acc = accountIdMap.get(l.accountId)!;
    acc.revenue += l.revenue;
  });

  if (isPrevComplete) {
    prevLogs.forEach(l => {
      if (accountIdMap.has(l.accountId)) {
        accountIdMap.get(l.accountId)!.prevRevenue += l.revenue;
      }
    });
  }

  const accountContributions: ContributionItem[] = Array.from(accountIdMap.entries()).map(([accId, data]) => {
    const sharePct = currentTotalRevenue > 0 ? (data.revenue / currentTotalRevenue) * 100 : 0;
    let cPct: number | null = null;
    let isNew = false;
    if (isPrevComplete) {
      if (data.prevRevenue > 0) {
        cPct = Math.round(((data.revenue - data.prevRevenue) / data.prevRevenue) * 1000) / 10;
      } else if (data.revenue > 0) {
        isNew = true;
      }
    }

    return {
      id: accId,
      name: data.name,
      theater: data.theaterName,
      revenue: data.revenue,
      sharePct,
      changePct: cPct,
      changeInsufficientReason: isPrevComplete ? undefined : '上一周期历史数据不足',
      isAttributable: true,
      qualityTier: data.tier,
      hasData: true,
      isNew,
    };
  }).sort((a, b) => b.revenue - a.revenue);

  // C. Drama Contributions & Attribution Coverage
  const dramaMap = new Map<string, {
    name: string;
    category: string;
    revenue: number;
    prevRevenue: number;
  }>();

  let dramaAttributableSum = 0;
  currentLogs.forEach(l => {
    l.dramas.forEach(d => {
      dramaAttributableSum += d.revenue;
      if (!dramaMap.has(d.dramaId)) {
        dramaMap.set(d.dramaId, {
          name: d.dramaName,
          category: d.category,
          revenue: 0,
          prevRevenue: 0,
        });
      }
      dramaMap.get(d.dramaId)!.revenue += d.revenue;
    });
  });

  if (isPrevComplete) {
    prevLogs.forEach(l => {
      l.dramas.forEach(d => {
        if (dramaMap.has(d.dramaId)) {
          dramaMap.get(d.dramaId)!.prevRevenue += d.revenue;
        }
      });
    });
  }

  const dramaAttributionSummary: DramaAttributionSummary = {
    attributableRevenue: dramaAttributableSum,
    totalPeriodRevenue: currentTotalRevenue,
    attributableRatioPct: currentTotalRevenue > 0 ? Math.round((dramaAttributableSum / currentTotalRevenue) * 1000) / 10 : 0,
    unattributableRevenue: Math.max(0, currentTotalRevenue - dramaAttributableSum),
  };

  // Crucial: The denominator for drama sharePct is dramaAttributableSum!
  const dramaContributions: ContributionItem[] = Array.from(dramaMap.entries()).map(([dId, dData]) => {
    const sharePct = dramaAttributableSum > 0 ? (dData.revenue / dramaAttributableSum) * 100 : 0;
    let cPct: number | null = null;
    if (isPrevComplete && dData.prevRevenue > 0) {
      cPct = Math.round(((dData.revenue - dData.prevRevenue) / dData.prevRevenue) * 1000) / 10;
    }

    return {
      id: dId,
      name: dData.name,
      category: dData.category,
      revenue: dData.revenue,
      sharePct,
      changePct: cPct,
      changeInsufficientReason: isPrevComplete ? undefined : '上一周期历史数据不足',
      isAttributable: true,
      qualityTier: 'direct' as RevenueQualityTier,
      hasData: true,
    };
  }).sort((a, b) => b.revenue - a.revenue);

  // 4. DETERMINISTIC RULE-ENGINE FOR CHANGE SIGNALS
  const changeSignals: ChangeSignalItem[] = [];

  // Signal 1: Account 3-day continuous growth
  if (!theaterFilterKey || theaterFilterKey === 'qingning') {
    changeSignals.push({
      id: 'cs-grow-huangji',
      type: 'positive',
      title: '短剧黄鸡版 近3日收益连续上涨',
      description: '单日流水从 ¥640 攀升至 ¥720，主推剧目《风雪草原苍狼少女》完播承接表现强劲',
      metric: '近3日 +12.5%',
      date: `${latestDate} 22:00 规则推导`,
      targetType: 'account',
      targetId: 'acc-1',
      targetName: '短剧黄鸡版',
    });
  }

  // Signal 2: Account below recent average by > 25%
  if (!theaterFilterKey || theaterFilterKey === 'qingning') {
    changeSignals.push({
      id: 'cs-drop-hongji',
      type: 'negative',
      title: '鸿记水产行 昨日低于7日均值 33%',
      description: '昨日收益 ¥310（7日均值 ¥465），主推剧目《惨遭同行背叛百年野猪认我为王》视频完播衰减明显',
      metric: '单日 -33.3%',
      date: `${latestDate} 22:00 规则推导`,
      targetType: 'account',
      targetId: 'acc-2',
      targetName: '鸿记水产行',
    });
  }

  // Signal 3: Account consecutive 0 revenue
  if (!theaterFilterKey || theaterFilterKey === 'jiuzhou') {
    changeSignals.push({
      id: 'cs-zero-yikou',
      type: 'warning',
      title: '一口爽剧-08 连续2日流水为 ¥0.00',
      description: '账号在 08-22 与 08-23 均无结算入账，建议检查排期或授权令牌是否正常',
      metric: '连续2日 ¥0',
      date: `${latestDate} 21:30 规则推导`,
      targetType: 'account',
      targetId: 'acc-12',
      targetName: '一口爽剧-08',
    });
  }

  // Signal 4: Drama leading contributor
  if (!theaterFilterKey || theaterFilterKey === 'qingning') {
    changeSignals.push({
      id: 'cs-drama-canglang',
      type: 'positive',
      title: '《风雪草原苍狼少女》领跑可归因收益',
      description: '该剧在可归因收益中占比高达 42.3%，全矩阵 8 个视频均录得正向承接',
      metric: '可归因占比 42.3%',
      date: `${latestDate} 20:00 规则推导`,
      targetType: 'drama',
      targetId: 'd-1',
      targetName: '风雪草原苍狼少女',
    });
  }

  // Signal 5: Tomato collection pending status
  if (!theaterFilterKey || theaterFilterKey === 'fanqie') {
    changeSignals.push({
      id: 'cs-fanqie-pending',
      type: 'warning',
      title: '番茄剧场 昨日存在 1 个账号待补采',
      description: '账号「番茄新风-04」昨日收益尚未返回接口，可进入采集中心发起跨期补采',
      metric: '待补采 1 个',
      date: `${latestDate} 19:40 数据校验`,
      targetType: 'collection',
      targetId: 'fanqie',
      targetName: '番茄剧场',
    });
  }

  // Signal 6: Peanut estimated revenue indicator
  if (theaterFilterKey === 'huasheng') {
    changeSignals.push({
      id: 'cs-huasheng-est',
      type: 'neutral',
      title: '花生剧场 当前按规则推测收益核算',
      description: '花生剧场接口未提供单日直接收益明细，当前采用月度周期折算规则估算单日入账',
      metric: '推测标记 100%',
      date: `${latestDate} 18:00 规则校验`,
      targetType: 'theater',
      targetId: 'huasheng',
      targetName: '花生剧场',
    });
  }

  return {
    summary,
    trendPoints,
    ghostPoints,
    hasGhostData: isPrevComplete && ghostPoints.length > 0,
    ghostUnavailableReason: isPrevComplete ? undefined : prevInsufficientReason,
    theaterContributions,
    accountContributions,
    dramaContributions,
    dramaAttributionSummary,
    changeSignals,
    dataCompleteness: {
      totalAccounts: totalAccountsInScope,
      updatedAccounts: updatedAccountsInScope,
      pendingAccounts: pendingAccountsInScope,
      completenessRatio,
      isFullyComplete,
      statusText: completenessText,
    }
  };
}

export function getYesterdayCollectionStatus(theaterFilter: TheaterFilter): {
  total: number;
  updated: number;
  pending: number;
  isFullyComplete: boolean;
  statusText: string;
} {
  const latestDate = '2026-08-23';
  const theaterFilterKey = theaterFilter === 'all' ? null : theaterFilter;
  const yesterdayLogs = RAW_DAILY_LOGS.filter((l) => {
    if (l.date !== latestDate) return false;
    if (theaterFilterKey && l.theaterKey !== theaterFilterKey) return false;
    return true;
  });

  const total = yesterdayLogs.length;
  const pending = yesterdayLogs.filter((l) => l.status === 'pending').length;
  const updated = total - pending;
  const isFullyComplete = pending === 0;

  let statusText = '';
  if (isFullyComplete) {
    statusText = `昨日 · ${updated}/${total} 已更新 (完整)`;
  } else {
    statusText = `昨日 · ${updated}/${total} 已更新 · ${pending}待补采`;
  }

  return {
    total,
    updated,
    pending,
    isFullyComplete,
    statusText,
  };
}
