# 阶段交付与验证记录

验证日期：2026-11-03。本文区分本机自动化、真实独立进程 HTTP 流程和尚未执行的容器验证。当前主机 Python 3.13 / Node.js 22；Compose 定义 Python 3.12 / PostgreSQL / Redis。

## Phase 0：工程与自动化

已实现 FastAPI、Pydantic / SQLAlchemy、Alembic、独立 Worker、React / TypeScript / Vite / Ant Design / React Query、Compose、环境变量样例、统一错误和结构化日志。

文件范围：`pyproject.toml`、`backend/app/core`、`backend/app/db`、`backend/app/main.py`、`worker`、`frontend` 工程文件、Docker / Compose 配置、README。

阶段验证：后端基础测试 3 passed；前端 UI smoke 1 passed；TypeScript 检查与前端构建通过。Compose YAML 完成解析 / 结构检查；没有 Docker，未执行 `docker compose up --build`。

## Phase 1：安全导入与解析

已实现有界 ZIP 导入、条目路径 / 链接 / Unicode / 设备名 / 压缩比校验、文件清单与 hash、内容寻址只读对象、同 hash 去重、Skill 版本记录、安全 YAML、frontmatter 和侧边 schema / 引用路径检查。

文件范围：`backend/app/ingest`、`backend/app/skill`、`backend/app/api/routes.py`、`schemas`、`backend/tests/test_safe_zip.py`、`test_parser.py`、`test_upload.py`、`docs/INGEST.md`。

阶段验证：累计后端 **75 passed**，覆盖 SEC-07 / 08 / 09 / 10 及导入 API 成功 / 失败 / 去重。安全校验不向宿主提取上传条目；被拒绝归档不产生 Skill 版本记录。

## Phase 2：真实静态检测与异步报告

已实现 SQSP-S001–S016、Python AST / alias / 有限局部数据流、脱敏稳定 finding 指纹、规则版本、真实 scan_id 队列、独立 Worker 领取 / 租约 / 重试与失败恢复、报告持久化 / 导出、finding 筛选，以及默认禁用的扩展适配器。

文件范围：`backend/app/scan`、`backend/app/policy`、`backend/app/reports`、`rules`、`backend/tests/test_static.py`、`test_scans.py`、`test_queue.py` 等测试、`examples`、`scripts/seed_examples.py`、`docs/RULES.md`。

阶段验证：累计后端 **159 passed**，核心后端覆盖率 **90%**。真实归档解析后的内置良性样例 0 findings；疑似风险样例 14 findings、13 类规则；v2 修复后移除 S003，其他发现继续保留。所有素材只解析、未执行。外部漏洞库、模型和动态执行未接入。

## Phase 3：质量、门禁与报告界面

交付范围：规范 / 可维护性静态维度、完整质量分为空、40% 最大覆盖、门禁优先级、Dashboard / 上传 / 报告 / 比较页面、筛选 / 导出 / 阶段原因与证据展示。

新增交付：`scripts/start-local.ps1`、`stop-local.ps1`、`smoke_test.py`，依赖 hash 锁、独立 PostgreSQL / Redis 测试 profile，以及 API / 安全 / 架构文档。

**Phase 3 代码与本机运行验收完成。** 规范与可维护性合计覆盖 0.4，完整质量分保持 null；门禁和对比 API 已工作。真实错误 schema 从 FastAPI 导出为 `docs/openapi.json`，前端 DTO 由该契约生成，测试检查导出与生成结果一致。

最终自动化结果：

- 后端 **200 passed、1 skipped**，覆盖率 **94%**。跳过项是真实 Redis / RQ 集成测试，因本机没有配置专用测试 Redis；不能当作已通过。另有 1 条 Starlette TestClient 的 httpx 弃用警告。
- `ruff check backend worker scripts` 通过；`alembic check` 未发现模型 / 迁移差异。
- 前端 **14/14 passed**，TypeScript 与 Vite build 通过。共享块约 568 kB，保留 chunk 大小警告；不影响构建结果。
- npm audit 与 Python pip-audit 均为 **0 个已知漏洞**；该结果只针对本平台当时安装的依赖，不代表上传 Skill 依赖已经查过漏洞库。
- PowerShell 脚本语法、启动 / 安全停止实跑验证通过；修复 Windows 多 node 路径、虚拟环境 launcher 身份时间比较及子进程处理。Vite 显式使用 frontend 根，启动检查同时确认 API ready 和前端 HTTP 200。

真实独立进程 HTTP smoke 已完整通过一次：ZIP 上传 → 数据库队列 → 独立 Worker → 报告 → v2 比较，目录遍历 ZIP 返回 INVALID_ARCHIVE，完整质量分为空，动态能力 UNAVAILABLE。它没有在脚本里直接调用扫描器。

Edge 浏览器实际操作验证 Dashboard 中真实扫描记录、报告证据展开、规则 / 引擎版本、完整质量分为空、40% 质量覆盖与 NOT_RUN 状态；版本比较实际显示 S003 已解决 1 项、其余持续 12 项。此处是当时浏览器数据快照，不是静态演示数据。

**Compose、PostgreSQL 与真实 Redis / RQ profile 仍未执行，不能从本机验收推导它们已通过。**

## 可复现命令

- 后端：`.venv\Scripts\python -m pytest backend/tests -q --basetemp=.pytest-tmp`
- 覆盖：`.venv\Scripts\python -m pytest backend/tests --cov=backend/app --cov-report=term-missing --basetemp=.pytest-tmp-coverage`
- 静态检查：`.venv\Scripts\python -m ruff check backend worker scripts`
- 前端：在 `frontend` 运行 `npm test`、`npm run build`
- 真实服务：`.\scripts\start-local.ps1`，然后 `.venv\Scripts\python scripts/smoke_test.py`
- 独立 PostgreSQL / Redis：`docker compose --profile test run --build --rm test`（当前未执行）

## 已知限制与下一阶段

动态沙箱、LLM 语义、实际宿主任务质量与漏洞匹配未运行，准确返回 UNAVAILABLE / NOT_RUN。静态文本与局部 AST 分析具有误报和漏报，不是安全证明。没有生产认证、多租户、审核流程和企业部署审计。

下一阶段首先在可用 Docker 环境运行 Compose 与 PostgreSQL / Redis profile；然后固定第三方扫描器版本和输出契约。合格 gVisor / microVM Runner 与真实宿主评测均需独立安全控制和测试，不允许以宿主命令或普通容器降级。
