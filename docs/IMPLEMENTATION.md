# Phase 0–3 实现与验证

## 已实现

- Phase 0：FastAPI、SQLAlchemy、Alembic、React / TypeScript / Vite、锁定依赖、SQLite 默认配置与本地启动脚本。
- Phase 1：安全 ZIP 摄入、YAML / 引用检查、内容哈希与本地 ArtifactStore。
- Phase 2：独立 Worker、SQLite 持久化队列、原子领取与租约、确定性静态安全规则、质量覆盖与策略门禁。
- Phase 3：扫描看板、风险 / 覆盖 / 阶段可视化、证据筛选、报告导出、版本比较、静态报告查看器和脱敏聚合报告构建。

## 运行闭环

`scripts/start-local.ps1` 迁移 SQLite、生成合成样例并启动 API、Worker 与 Vite。`scripts/smoke_test.py` 经真实 HTTP 上传样例，等待独立 Worker 处理，验证报告、差异、目录遍历拒绝、完整质量分为空及动态沙箱不可用。`scripts/stop-local.ps1` 只停止经身份核验的记录进程，保留 `data/`。

## 依赖与边界

运行不需要 Docker、外部数据库、缓存或消息队列。依赖锁定在 `requirements.lock` / `requirements-dev.lock`，前端使用 `package-lock.json`。动态、模型和真实宿主评测仍没有可信执行环境，报告保持 `UNAVAILABLE` / `NOT_RUN`，不会以不安全方式替代。

## 本次重构后的验收

本次轻量重构验收（2026-11-11）：后端 **201 passed**，Ruff 与 `alembic check` 通过；前端 **36 passed**，常规与独立报告构建均通过。`start-local.ps1 -> smoke_test.py -> stop-local.ps1` 已真实验证：三份合成 ZIP 经独立 Worker 生成报告、完成版本比较，目录遍历被拒绝，完整质量分保持 null，动态沙箱保持 UNAVAILABLE。前端构建保留超过 500 kB 的 chunk 体积告警；后端有一条 Starlette TestClient/httpx 弃用警告。CI 运行同一套 pytest、Ruff、前端测试与构建，不依赖云资源或外部状态。
