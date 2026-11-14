# 短剧推广运营系统 V3

当前开发目录：`D:\ShortDramaPlatform_V3`

## 启动

Windows 上运行 `启动V3开发版.bat`。开发版会从当前源码构建前端并启动本地服务。

## 新会话入口

先读：

1. `AGENTS.md`
2. `docs/项目状态.md`
3. `docs/项目总览.md`
4. `docs/功能地图.md`
5. 本次任务对应的 `docs/功能/` 文档

完整文档入口见 [docs/README.md](docs/README.md)。

## 数据与验证

业务数据使用既有数据目录；自动检查使用临时工作区。源码、开发版、安装包、真实运行和用户验收分开记录。

常用检查：

```powershell
py -3.12 tools\workspace_hygiene.py --check
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.release.json
npm run build
```
