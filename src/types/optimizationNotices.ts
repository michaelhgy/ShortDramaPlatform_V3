import config from '../data/optimizationNoticeRules.json' with { type: 'json' };

export type KnownOptimizationReason = '多次发布' | '引导优化' | '羊头链接' | '未挂链接' | '原创优化';
export type SimplifiedOptimizationReason = string;
export interface OptimizationAnalysisMapping {analysis:string;tag:string;updated_at?:string}
export interface OptimizationAnalysisConfiguration {version:number;mappings:OptimizationAnalysisMapping[]}
export type OptimizationReasonType = SimplifiedOptimizationReason;
export type OptimizationSeverity = '严重' | '中度' | '轻微' | '未判定';
type Rule = { id: string; tag: KnownOptimizationReason; analysis: string; aliases?: string[]; color: 'blue' | 'amber' | 'red' | 'pink' | 'violet'; homogeneous: boolean };
export const OPTIMIZATION_NOTICE_RULES = config.rules as Rule[];
export const OPTIMIZATION_NOTICE_VERSION = config.version;

const palettes = {
  blue: { color: '#3B82F6', pill: 'bg-blue-50 text-blue-700 border-blue-200' },
  amber: { color: '#F59E0B', pill: 'bg-amber-50 text-amber-700 border-amber-200' },
  red: { color: '#DC2626', pill: 'bg-red-50 text-red-700 border-red-200' },
  pink: { color: '#EC4899', pill: 'bg-pink-50 text-pink-700 border-pink-200' },
  violet: { color: '#8B5CF6', pill: 'bg-purple-50 text-purple-700 border-purple-200' },
  slate: { color: '#64748B', pill: 'bg-slate-100 text-slate-600 border-slate-200' },
};

export interface OfficialNoticeDefinition {
  simplifiedReason: SimplifiedOptimizationReason;
  officialNotice: string;
  severity: OptimizationSeverity;
  impactNotice: string;
  shortTag: string;
  color: string;
  pill: string;
  homogeneous: boolean;
}

/** Compatibility name: these are the user's provisional mappings, not an official taxonomy. */
export const OFFICIAL_OPTIMIZATION_DEFINITIONS: Record<SimplifiedOptimizationReason, OfficialNoticeDefinition> = Object.fromEntries([
  ...OPTIMIZATION_NOTICE_RULES.map(rule => [rule.tag, { simplifiedReason: rule.tag, officialNotice: rule.analysis,
    shortTag: rule.tag, severity: '未判定', impactNotice: '', homogeneous: rule.homogeneous, ...palettes[rule.color] }]),
  ['待归类', { simplifiedReason: '待归类', officialNotice: '', shortTag: '待归类', severity: '未判定', impactNotice: '', homogeneous: false, ...palettes.slate }],
]) as Record<SimplifiedOptimizationReason, OfficialNoticeDefinition>;

export const OPTIMIZATION_REASONS = Object.keys(OFFICIAL_OPTIMIZATION_DEFINITIONS) as SimplifiedOptimizationReason[];
export function createOptimizationReasonCounts(reasons:readonly string[]=OPTIMIZATION_REASONS): Record<SimplifiedOptimizationReason, number> {
  return Object.assign(Object.create(null), Object.fromEntries(reasons.map(tag => [tag, 0])));
}
export function getOptimizationAppearance(tag: string) {
  return Object.hasOwn(OFFICIAL_OPTIMIZATION_DEFINITIONS, tag)
    ? OFFICIAL_OPTIMIZATION_DEFINITIONS[tag as SimplifiedOptimizationReason] : {...OFFICIAL_OPTIMIZATION_DEFINITIONS['待归类'],simplifiedReason:tag||'待归类',shortTag:tag||'待归类'};
}

/** Normalize formatting only; never classify by vague keywords or overwrite the stored original. */
export function normalizeOptimizationAnalysis(text: string): string {
  return text.replace(/<br\s*\/?\s*>/gi, '\n').replace(/&nbsp;/g, ' ').replace(/^\s*作品分析\s*[:：]\s*/, '').replace(/\s+/g, '');
}
export function matchOptimizationAnalysis(text: string, mappings:readonly OptimizationAnalysisMapping[]=[]): SimplifiedOptimizationReason {
  const normalized = normalizeOptimizationAnalysis(text);
  if(!normalized)return '待归类';
  const saved=mappings.find(mapping=>normalizeOptimizationAnalysis(mapping.analysis)===normalized);
  if(saved)return saved.tag;
  return OPTIMIZATION_NOTICE_RULES.find(rule => [rule.analysis,...(rule.aliases||[])].some(analysis=>normalizeOptimizationAnalysis(analysis)===normalized))?.tag ?? '待归类';
}

/** One display heading, while callers retain the unmodified analysis string separately. */
export function optimizationAnalysisBody(text: string): string {
  return text.replace(/^\s*作品分析\s*[:：]\s*/, '');
}

/** Build each model's definitions without leaking assignments into other windows or fixtures. */
export function buildOptimizationDefinitions(mappings:readonly OptimizationAnalysisMapping[]=[], observed:readonly string[]=[]) {
  // Default rules classify legacy text; they are not evidence of collected analyses.
  const texts=[...observed,...mappings.map(m=>m.analysis)];
  const unique=new Map<string,string>();
  for(const text of texts){const normalized=normalizeOptimizationAnalysis(text);if(normalized&&!unique.has(normalized))unique.set(normalized,text);}
  const tags=[...new Set([...OPTIMIZATION_REASONS.filter(t=>t!=='待归类'),...mappings.map(m=>m.tag)].filter(t=>t&&t!=='待归类')),'待归类'];
  return Object.fromEntries(tags.map(tag=>{
    const analysisTexts=[...unique.values()].filter(text=>matchOptimizationAnalysis(text,mappings)===tag);
    return [tag,{...getOptimizationAppearance(tag),analysisTexts,officialNotice:analysisTexts.join('\n\n')}];
  })) as Record<string,OfficialNoticeDefinition & {analysisTexts:string[]}>;
}
