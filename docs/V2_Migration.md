# V2 独立数据迁移规范

## 关系与边界

V2 的产品流程和数据从零开始建立。V1 保留为不可修改的能力参考，不再作为 V2 的默认 API、数据库或业务数据来源。V2 的本地 Python 服务和 SQLite 只管理 `D:\短剧推广运营系统` 下的 V2 数据。

## API 调用

- API 客户端位于 `src/api/client.ts`；默认超时 15 秒，统一解析 V2 的 `{ error }` 错误响应。
- 生产环境：`VITE_V1_API_BASE_URL` 留空，调用当前 pywebview 页面所在的 `/api/v1/...`。
- 独立开发：先从 V1 `backend` 运行 `python run_v1_api.py --port 8765`，并保持 `VITE_V1_API_BASE_URL` 为空。V2 开发服务器默认将同源 `/api` 代理到 `http://127.0.0.1:8765`；如需连接其他 V1 实例，可设置 `VITE_V1_API_PROXY_TARGET` 覆盖该地址。Vite 代理可避免 V1 未开启 CORS（跨域访问）时浏览器拦截请求。
- 连通性检查：`GET /api/v1/health`，预期 `{ "status": "ok", "version": 2 }`。V2 不启动 Express，不创建第二个后端。

## 数据源和转换

页面不得直接导入 `*MockData.ts`。页面通过 `src/services/mockServices.ts` 取得开发数据；该层是日后按功能切换至 `src/api/` 与 `src/adapters/` 的唯一入口。

`VITE_V2_DATA_SOURCE` 缺省或为 `v2` 时使用 V2 本地真实数据模式；只有显式设为 `mock` 才使用现有模拟数据。尚未迁移的页面显示“暂无真实数据”，不会静默回退为 AI Studio 示例数据。V2 展示类型继续位于各页面现有 `*Types.ts`，转换函数置于 `src/adapters/`。

未知 V1 状态必须保留为“未知状态（原始值）”；不可将失败、无数据或待人工处理显示为零或已完成。

## 页面顺序

第一阶段：数据分析（先收益、账号）和生产中心（计划、素材、生成、导出状态）。

第二阶段：资料中心、任务中心、工作台、系统设置。

剧集/视频收益归因、虚拟定位、智能推荐和小V猫推送目前没有已确认的 V1 数据合同，不能提前接入或用模拟数值冒充真实能力。

## 已接入：数据分析 - 收益

当 `VITE_V2_DATA_SOURCE=v1` 时，收益页通过 `services/revenueAnalyticsService.ts` 调用：

- `GET /api/v1/revenue/daily-revenues`：逐账号、逐日、按剧场筛选的规范化日收益；V2 在适配层汇总趋势、账号贡献和剧场贡献。
- `GET /api/v1/accounts` 与 `GET /api/v1/theaters`：计算当前日期“已有日收益记录”的账号覆盖度，并解析采集目标剧场。
- `POST /api/v1/revenue/collect-now` 与 `POST /api/v1/revenue/backfill`：采集抽屉展示本次请求实际返回的账号尝试结果。

V1 未提供历史采集尝试列表，所以首次打开抽屉不会伪造历史日志；仅显示当前 V2 会话触发请求后的结果。V1 的 `daily_revenues` 没有剧集归因字段，收益页中的剧集贡献保持无数据，不回退为 Mock 数值。

## 当前页面可用性

- 已接入真实数据：数据分析的“收益”子页；生产中心的计划、剧集、素材、模板、成片、生成和导出只读状态；生产中心的 V2 素材扫描与重命名。
- 暂无真实数据：工作台、资料中心、任务中心、系统设置，以及数据分析的账号、剧集、视频、组合子页。这些模块仍显示新版 UI 的空状态，而不是隐藏页面。
- V1 模式下，上述未接入页面不会显示 AI Studio 示例数据；Mock 仅供开发时显式设置 `VITE_V2_DATA_SOURCE=mock` 使用。

## Windows 桌面测试

V2 可通过 `tools/run_v2_desktop_test.py` 使用与 V1 相同的 pywebview/Edge WebView2 窗口基线进行开发测试。详见 `docs/Desktop_Test.md`；该入口只加载 V2 开发服务器，不改动 V1。

## V2 文件服务（第一项真实生产能力）

V2 的素材扫描和重命名使用独立的 `server/v2_file_service.py`，不调用会写入 V1 旧目录的扫描接口。默认工作目录为 `D:\短剧推广运营系统`，系统数据默认保存到 `D:\短剧推广运营系统\系统数据`；运行 `python tools/run_v2_file_service.py` 时会自动创建五个一级目录。开发环境可通过 `V2_WORKSPACE_ROOT` 和 `V2_SYSTEM_DATA_ROOT` 覆盖，但绝不能指向 V1 目录。Vite 将 `/api/v2` 代理到该服务，`/api/v1` 仍代理到 V1。

当前接口只包含：创建生产任务目录、扫描生产任务的 `素材` 目录、两阶段安全重命名、MD5/SHA-256 记录。生产中心的“重新扫描素材”已接入该接口；它不会自动扫描或迁移现有 V1 目录。
