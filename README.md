# AgentForge NightWatch（SQSP）— Agent 工件安全与进化平台

面向个人开发者的本地优先平台：安全导入 Agent Skill ZIP、解析规范、执行确定性静态安全扫描、展示质量覆盖、比较版本并生成可分享报告。API 和扫描 Worker 始终是两个独立进程；上传的脚本只被当作文本和 AST 数据解析，绝不会执行、导入或调用其中命令。

Skill 是当前已实现的首个工件类型。工作流、提示包和连接器是后续可复用同一摄入、证据、策略、版本与进化模型的方向，不会被表述为已实现能力。详见[平台说明](docs/PLATFORM.md)。

## 轻量本地启动

无需 Docker、容器引擎、PostgreSQL、Redis 或任何外部服务。只需 Python 3.12+（已在 3.13 验证）和 Node.js 22：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python -m pip install --no-deps -e .
Set-Location frontend
npm ci
Set-Location ..
.\scripts\start-local.ps1
```

脚本会执行 SQLite 迁移、生成合成样例，并启动 API（`127.0.0.1:8000`）、独立 SQLite Worker 和 Vite（`127.0.0.1:5173`）。它会确认 API `/readyz` 和首页均可访问，再输出链接。打开 <http://127.0.0.1:5173>。

本地数据保存在 `data/sqsp.db` 与 `data/artifacts`。`scripts/stop-local.ps1` 仅停止本脚本记录且经命令行、创建时间、工作区路径三重核验的进程；不会删除数据库、工件、报告或日志。

```powershell
.\.venv\Scripts\python scripts/smoke_test.py
.\scripts\stop-local.ps1
```

本地任务流为 `API -> SQLite scans 记录 -> 独立 Worker -> SQLite / ArtifactStore`。API 只创建 `QUEUED` 记录并立即返回；Worker 以原子领取与租约处理任务，扫描不在 Web 请求或 API 后台线程中运行。

如需手动运行，API 与 Worker 必须使用相同的 `SQSP_DATABASE_URL`（默认 `sqlite:///./data/sqsp.db`）和 `SQSP_ARTIFACT_ROOT`（默认 `./data/artifacts`）：

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python scripts/seed_examples.py
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
# 另开终端
.\.venv\Scripts\python -m worker.worker_main
# 再开终端
Set-Location frontend; npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## 报告看板与静态分享

扫描报告包含真实数据驱动的 SVG 风险分布、静态质量检查覆盖环图、阶段状态矩阵、耗时条和 Top 风险文件表；风险图例可筛选下方证据。质量页会覆盖规范符合性、可维护性、功能正确性和稳定性/效率四个维度的静态可验证性：功能/正反向/边界用例、可观察断言、重复用例、时限、恢复、幂等和依赖失败约定均会逐项显示。完整运行时质量分不会补零。

`/viewer` 可在浏览器内存读取已有 JSON，不调用扫描 API。可构建完全独立的静态报告查看器或经脱敏的聚合摘要，用于公开静态托管：

```powershell
Set-Location frontend; npm run build:report; Set-Location ..
.\.venv\Scripts\python scripts/build_report_site.py --output release/my-report-viewer
.\.venv\Scripts\python scripts/build_report_site.py --report path/to/report.json --output release/my-public-report
```

聚合摘要默认剔除名称、标识、路径、hash、证据、权限与日志；发布前仍须复核披露范围。静态报告可无需后端，但本机扫描平台不应直接向不可信公网开放。详见[报告设计](docs/REPORT_DESIGN.md)、[分享指南](docs/SHARING_GUIDE.md)、[上线与成本评估](docs/PUBLIC_DEPLOYMENT_ASSESSMENT.md)。

## 给其他 Agent 的开箱即用包装

可安装的 [`skillforge-nightwatch`](agent_skills/skillforge-nightwatch/SKILL.md) 包装器会将本地 ZIP 以数据方式上传到已启动的可信实例、等待真实报告并写出新的 JSON。默认拒绝非本机地址，远程地址需调用者显式传入 `--allow-remote`；包装器不会执行上传的脚本、依赖或指令。

```powershell
.\.venv\Scripts\python scripts\package_agent_skill.py --output release\skillforge-nightwatch-skill.zip
```

## 创作思路：让低峰算力服务于安全演进

产品对外品牌为 **SkillForge NightWatch**。可并行、非交互的静态审计可安排在低峰时段；先用风险与成本分层筛选候选，再把高成本评测留给受控环境。这样能更好利用空闲算力，也不会为了吞吐执行不可信代码。见[创作思路与产品演进](docs/CREATIVE_RATIONALE.md)。

## 演示与验证

样例位于 [examples/zips](examples/zips)：良性、疑似风险及修复 v2；它们只含合成数据，平台不会执行样例脚本。Smoke 会通过真实 HTTP、SQLite 队列和独立 Worker 验证上传、报告、比较、目录遍历拒绝、完整质量分为空与动态沙箱不可用。

```powershell
.\.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python -m pytest backend/tests -q --basetemp=.pytest-tmp
.\.venv\Scripts\python -m ruff check backend worker scripts
Set-Location frontend; npm test; npm run build; npm run build:report
```

## 安全与能力边界

- S001–S016 是确定性静态规则，存在误报和漏报；AST 数据流仅限局部分析。
- 四个质量维度均有静态可验证性检查，`quality_coverage` 表示这些确定性检查的覆盖权重；`runtime_coverage` 仍为 0，缺少真实功能正确性和稳定性数据时，`quality_score` 必须保持 `null`。
- 动态 Runner、模型语义分析、真实宿主评测和漏洞库未接入，始终返回 `UNAVAILABLE` / `NOT_RUN`；绝不以本机 `subprocess`、浏览器或普通容器作为不安全替代。
- `BLOCK > INCOMPLETE > REVIEW > ALLOW`；静态门禁 `ALLOW` 不是全面安全保证。
- MVP 是本机单用户工具，没有认证、RBAC 或多租户；不要上传生产凭据或客户数据。

更多信息：[交付清单](DELIVERY.md)、[架构](docs/ARCHITECTURE.md)、[安全边界](docs/SECURITY.md)、[API](docs/API.md)、[实现决策](docs/DECISIONS.md)、[阶段报告](docs/IMPLEMENTATION.md)。
