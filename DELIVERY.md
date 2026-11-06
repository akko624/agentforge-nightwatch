# SQSP MVP 交付清单

交付日期：2026-11-03。Phase 0–3 的真实代码、本机服务、自动化与浏览器流程已经完成。交付是可运行的 Skill ZIP → 静态检测 → 质量覆盖 / 门禁 → 报告 / 版本比较闭环；没有执行未可信 Skill，也没有伪造动态或模型结果。

## 运行

依赖安装与完整说明见 [README](README.md)。Windows 原生环境安装锁定依赖后：

```powershell
.\scripts\start-local.ps1
.\.venv\Scripts\python scripts/smoke_test.py
# 核对进程身份后只停止本项目服务，保留数据
.\scripts\stop-local.ps1
```

本地 Web 为 <http://127.0.0.1:5173>，API 为 <http://127.0.0.1:8000/docs>。Windows 使用独立 database Worker；Redis / RQ Worker 要求 Linux Compose。

Docker 部署配置已提供：`docker compose up --build`，Web 8080、API 8000。**本机没有 Docker，不能宣称该命令的容器验收已通过。**

## 按模块列出真实文件

| 模块 | 关键文件 | 实际交付 |
|---|---|---|
| 工程与部署 | `pyproject.toml`、`requirements.lock`、`requirements-dev.lock`、`docker-compose.yml`、`backend/Dockerfile`、`worker/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf`、`.env.example` | 固定依赖及 hash、六服务部署、独立测试 profile、非 root / 只读根文件系统 |
| API / 配置 / 错误 | `backend/app/main.py`、`api/routes.py`、`core/config.py`、`core/errors.py`、`core/upload_limit.py`、`schemas/api.py` | 健康检查、限流式请求体、统一错误、真实上传 / 扫描 / 报告 / 比较 API |
| 数据库 | `backend/app/db/models.py`、`session.py`、`migrations/env.py`、`migrations/versions/e484c6f237b3_initial_schema.py`、`alembic.ini` | Skill / 版本 / 扫描 / findings / 质量 / 审计持久化及迁移 |
| 安全导入 | `backend/app/ingest/safe_zip.py`、`store.py`、`skill/parser.py`、`schemas/skill-security.schema.json`、`skill-evals.schema.json` | 安全 ZIP / YAML、文件清单与 hash、侧边声明、引用检查、内容寻址工件 |
| 静态分析 | `backend/app/scan/static_rules/builtin.py`、`rules/builtin-rules.yaml`、`core/redaction.py` | SQSP-S001–S016、AST / 别名 / 局部数据流、脱敏证据与稳定指纹、覆盖限制 |
| 队列与 Worker | `backend/app/scan/orchestrator.py`、`queue.py`、`worker/worker_main.py` | 独立任务生命周期、租约 / CAS / 重试恢复、签名漂移拒绝、报告保存 |
| 质量 / 策略 / 比较 | `backend/app/scan/quality/static.py`、`policy/decision.py`、`policy/permissions.py`、`reports/compare.py`、`rules/policy.yaml` | 40% 最大静态质量覆盖、完整分 null、独立安全门禁、deny 优先权限交集、跨版本差异 |
| 扩展契约 | `backend/app/scan/contracts.py`、`scan/adapters/disabled.py` | 扫描器 / 沙箱 / 语义 / 宿主质量接口；默认不可用并拒绝不安全降级 |
| 前端 | `frontend/src/App.tsx`、`pages/Dashboard.tsx`、`UploadPage.tsx`、`ReportPage.tsx`、`ComparePage.tsx`、`api/client.ts`、`api/generated.ts`、`components/shared.tsx` | 真实列表 / 上传 / 轮询 / 筛选 / 证据 / 覆盖 / JSON 导出 / 比较 |
| 契约与运行工具 | `scripts/export_openapi.py`、`generate_api_types.py`、`start-local.ps1`、`stop-local.ps1`、`smoke_test.py`、`docs/openapi.json` | 实际 API 类型生成、可安全停止的本地服务、真实 HTTP 验收 |
| 合成样例 | `examples/benign-skill`、`examples/suspicious-skill`、`examples/zips`、`scripts/seed_examples.py` | 良性 / 风险 / v2 确定性 ZIP；只读取，从未执行 |
| 说明 | `docs/SPECIFICATION.md`、`ARCHITECTURE.md`、`SECURITY.md`、`INGEST.md`、`RULES.md`、`API.md`、`DECISIONS.md`、`IMPLEMENTATION.md` | 原规格、实现决策、安全边界和逐阶段真实证据 |

表中从第二个文件起省略相同父目录以便阅读；完整目录可直接检索仓库。测试素材均为合成内容，不包含生产密钥或实际攻击目标。

## 自动化与实际运行证据

| 检查 | 结果 |
|---|---|
| 后端 pytest | **200 passed，1 skipped**；跳过真实 Redis / RQ 集成，因未配置专用测试 Redis |
| 核心后端覆盖 | **94%** |
| Ruff | `backend worker scripts` 通过 |
| Alembic | `alembic check` 无模型 / 迁移差异 |
| 前端测试 | **14/14 passed** |
| TypeScript / Vite | 构建成功；约 568 kB 共享块保留大小警告 |
| npm audit / pip-audit | **0 个已知漏洞**；仅针对本平台已安装依赖 |
| 独立服务 HTTP smoke | 完整通过：上传、真实 Worker、报告、S003 修复比较、目录遍历拒绝、质量空值与沙箱不可用 |
| Edge 浏览器 | 实际 Dashboard 记录、报告证据展开与版本 / 40% 覆盖 / null / NOT_RUN、S003 解决差异可见 |
| 本地启动 / 停止 | 隐藏进程启动、API ready / 前端 HTTP 200、身份核验后停止自己的 launcher / Python 子进程已验证 |
| Compose / PostgreSQL / 真实 Redis profile | **未运行**，当前无 Docker |

后端保留 1 条 Starlette TestClient / httpx 弃用警告。它与前端共享块警告均已披露，没有作为测试失败隐藏，也没有将跳过项计为通过。

真实测试文件：`backend/tests/test_safe_zip.py`、`test_upload.py`、`test_parser.py`、`test_static.py`、`test_scans.py`、`test_queue.py`、`test_quality.py`、`test_policy.py`、`test_compare.py`、`test_limits.py`、`test_redaction.py`、`test_health.py`、`test_review.py`、`test_api_types.py`；前端 `frontend/tests/workflow.test.tsx`、`api.test.ts`。逐阶段命令与证据见 [IMPLEMENTATION](docs/IMPLEMENTATION.md)。

## 仍然明确不可用的能力

动态隔离、LLM 语义、真实宿主功能 / 稳定性评测与依赖漏洞数据库没有接入。报告显示 UNAVAILABLE / NOT_RUN；完整质量分为 null，不能把静态子分理解为真实任务成功率。平台不会回退为在主机或普通容器中执行上传脚本。

本版本没有认证 / RBAC / 多租户、人工审核写入流程与生产部署审计；只面向本机单用户。静态规则为 best effort，存在误报 / 漏报，ALLOW 仅代表当前明确门禁条件，不是全面安全保证。

## 下一步

1. 在具备 Docker 的环境运行 `docker compose up --build` 与 `docker compose --profile test run --build --rm test`，补齐 PostgreSQL / Redis / RQ 和容器启动证据。
2. 固定第三方扫描器版本、许可证和结构化输出契约后实现 Adapter；当前不启用未知 CLI。
3. 在专门执行主机实现合格 gVisor / microVM Runner，自检资源、文件、网络和凭据边界，再接入真实宿主评测；不采用不安全的替代运行方式。
