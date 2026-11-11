# SQSP MVP 交付清单

Phase 0–3 已交付为真实、本地可运行的闭环：Skill ZIP 安全导入 -> SQLite 持久化任务 -> 独立 Worker 静态检测 -> 质量覆盖 / 门禁 -> 看板报告 / 版本比较。没有执行未可信 Skill，也没有伪造动态或模型结果。

## 运行方式

项目不要求 Docker、容器引擎、PostgreSQL、Redis 或云账号。安装 Python 3.12+ 和 Node.js 22 后，按 [README](README.md) 安装依赖并运行：

```powershell
.\scripts\start-local.ps1
.\.venv\Scripts\python scripts/smoke_test.py
.\scripts\stop-local.ps1
```

Web：<http://127.0.0.1:5173>；API 文档：<http://127.0.0.1:8000/docs>。启动脚本只启动 API、独立 Worker 与 Vite，并在停止时保留 `data/` 下所有数据库、工件与日志。

## 关键交付

| 模块 | 关键文件 | 实际交付 |
|---|---|---|
| 轻量运行 | `pyproject.toml`、锁文件、`.env.example`、`scripts/start-local.ps1`、`scripts/stop-local.ps1` | SQLite 默认数据库、内容寻址本地工件、可核验进程管理 |
| API 与持久化 | `backend/app/main.py`、`api/routes.py`、`db/models.py`、`migrations/` | 上传、扫描、报告、比较、迁移、审计记录 |
| 独立扫描 | `backend/app/scan/orchestrator.py`、`worker/worker_main.py` | 数据库领取、租约、重试、签名漂移拒绝、报告保存 |
| 安全导入与规则 | `ingest/`、`skill/`、`scan/static_rules/`、`rules/` | ZIP / YAML 限制、哈希、静态规则、脱敏证据 |
| 前端与报告 | `frontend/src/`、`scripts/build_report_site.py` | 上传、轮询、证据筛选、图表看板、JSON 导出、静态分享摘要 |
| 扩展契约 | `scan/contracts.py`、`scan/adapters/disabled.py` | 动态、模型与宿主评测接口；默认安全地不可用 |

## 验收范围

测试和本地 HTTP 冒烟在本次重构后重新执行并记录到 [阶段报告](docs/IMPLEMENTATION.md)。CI 只安装锁定 Python / Node 依赖，运行 pytest、Ruff、前端测试和构建；不需要外部数据库或队列服务。

## 明确未实现

动态隔离、LLM 语义、真实宿主功能 / 稳定性评测和漏洞数据库仍未接入。它们保持 `UNAVAILABLE` / `NOT_RUN`，不以主机进程或普通容器降级。MVP 没有认证、RBAC、多租户或面向公网的上传服务。
