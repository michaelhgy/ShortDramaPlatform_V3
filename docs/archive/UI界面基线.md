> 🗄 **2026-09-19 已归档**："当前实施顺序"四步均已做完，页面清单缺「参数中心」。
> **仍有效的数据规则已并入** `docs/功能档案/04-跨模块规则/界面与开发规范.md`；AI Studio 基准包路径一条见 `docs/项目现状地图.md`。

# V2 UI 界面基线

## 基准来源

- AI Studio 导入包解压基准：`D:\ShortDramaPlatform_V2_UI_20260825\src`
- 正式 V2 工程：`D:\ShortDramaPlatform_V2`

AI Studio 页面视觉、排版、颜色、组件层级和交互方案是 V2 的界面基准。业务接入不得借“无数据”“接口未接入”等理由增加新的页面、卡片、说明区或重排页面结构。

## 数据为空时的规则

- 不显示 AI Studio 示例业务数据。
- 不显示 V1、V2、接口、Mock（模拟数据）等技术说明。
- 保留原页面结构；具体业务区域无记录时只使用该区域已有的空列表、空表格或无数据图表表现。
- 原稿没有定义空状态的页面，先记录为待补齐的产品交互，不擅自设计替代页面。

## 当前已识别的接入影响页面

- 工作台：`src/components/explore/WorkbenchExplore.tsx`
- 生产中心：`src/components/production/ProductionCenter.tsx`
- 数据分析：`src/components/analytics/DataAnalyticsView.tsx`、`RevenueModule.tsx`、`AnalyticsHeader.tsx`
- 资料中心：`src/components/assets/AssetsCenterView.tsx`
- 任务中心：`src/components/taskcenter/TaskCenterModal.tsx`
- 系统设置：`src/components/settings/SettingsView.tsx`
- 全局外壳：`src/App.tsx`、`src/components/Header.tsx`

这些文件后续只允许通过 service（服务层，负责取数）和 adapter（适配层，负责转换数据）接入真实数据；视觉调整必须单独提出并由产品确认。

## 当前实施顺序

1. 锁定上述 UI 基线，移除此前新增的技术提示和替代性空页面。
2. 建立 V2 剧场、账号的真实数据合同和存储。
3. 仅在资料中心的既有 UI 内接入剧场、账号功能。
4. 再迁入剧集、生产任务、发布、收益等能力。
