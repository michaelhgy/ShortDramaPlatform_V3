import { v2Client } from './client';

/**
 * 参数中心（资料中心之后的新页签）的数据接口。
 *
 * 后端只返回**完整解析后的生效值**：前端不需要知道"没设置过时该用哪个默认值"，
 * 只看生效值即可。产品与工程规则见 docs/V2参数中心规则.md。
 *
 * 注意：服务端返回的 key 是 snake_case（与其余 V2 接口一致），
 * 这一层保留 snake_case，由界面组件决定怎么显示。
 */

/** 单个插片位（中插或尾插）的设置。 */
export interface V2InsertionSlot {
  /** 是否要这一条插片。 */
  enabled: boolean;
  /** latest = 每次生成时动态取序号最大的一条；locked = 锁定 file 指定的那一条。 */
  mode: 'latest' | 'locked';
  /** mode 为 locked 时的文件名（不含目录）；latest 时为空串。 */
  file: string;
}

export interface V2MidrollEndrollStrategy {
  midroll: V2InsertionSlot;
  endroll: V2InsertionSlot;
}

export interface V2EngineParameters {
  template_copy: {
    /** 生效的祝福语池。空数组 = 不要这条轨道。 */
    blessing: string[];
    /** 生效的引导语池。空数组 = 不要这条轨道。 */
    drama_prompt: string[];
    /** 内置默认池，供界面上"恢复默认"使用。 */
    blessing_default: string[];
    drama_prompt_default: string[];
    /** 用户是否已经在界面里保存过（false = 仍在使用默认池或旧配置文件）。 */
    configured: boolean;
  };
  midroll_endroll: {
    strategy: V2MidrollEndrollStrategy;
    /** 用户是否曾经设置过（false = 仍在使用"两条都要、各取最新"的历史行为）。 */
    configured: boolean;
  };
}

/** 只提交载荷里出现过的参数组；未出现的组保持原值。 */
export interface V2EngineParametersPayload {
  template_copy?: { blessing: string[]; drama_prompt: string[] };
  midroll_endroll?: V2MidrollEndrollStrategy;
}

export function getV2EngineParameters(): Promise<V2EngineParameters> {
  return v2Client.get('/api/v2/engine-parameters');
}

export function updateV2EngineParameters(payload: V2EngineParametersPayload): Promise<V2EngineParameters> {
  return v2Client.post('/api/v2/engine-parameters', payload);
}
