# AgentForge NightWatch — Skill 质量与安全验证平台

AgentForge NightWatch 当前只处理 **Skill ZIP**：一个包含 `SKILL.md`、参考资料、可选脚本和评测声明的技能包，供 Agent 在需要时按宿主规则使用。它不是通用 Agent 应用导入器，也不会运行完整 Agent。

平台以本地优先方式安全读取这类 Skill 包：在**不执行上传代码**的前提下完成规范校验、静态安全审计、质量可验证性检查、版本比较，并把结果转成可行动的改进闭环。

| 核心亮点 | 带来的价值 |
|---|---|
| **零执行摄入** | ZIP 只作为文本、元数据和 AST 分析对象；不会 import、运行或调用其中命令。 |
| **证据驱动看板** | 风险分布、定位到文件行号的证据、中文修复方案、质量覆盖与阶段状态在同一份报告中联动。 |
| **质量不伪装** | 四维静态可验证性检查完整呈现；真实运行时数据缺失时保留 `null` / `UNAVAILABLE`，不编造成功率。 |
| **可比较的进化闭环** | P0/P1/P2 改进建议、版本差异和重新扫描，让“修了什么、改善了什么”都有依据。 |
| **轻量且可分享** | SQLite + 独立 Worker 本地启动；可构建脱敏的静态报告查看器，安全分享审查结论。 |

## 当前范围

- 已支持：符合当前规范、根目录含 `SKILL.md` 的 Skill ZIP。
- 不支持：完整 Agent 项目、Agent 运行时、工作流、MCP/连接器配置、提示包和知识库导入。
- 不会做：执行、`import`、安装依赖或调用上传 ZIP 中的脚本/命令。

工作流、提示包和连接器是后续可能复用同一套证据与版本模型的方向，并非当前能力。详见[平台说明](docs/PLATFORM.md)。

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

## 核心设计：先证据，后决策

**SkillForge NightWatch** 的价值不在于堆叠扫描数量，而在于让风险、质量、版本变化和修复动作形成可追溯的工程闭环：先用零执行检查建立证据，再把需要深入验证的候选交给未来的受控隔离环境。见[创作思路与产品演进](docs/CREATIVE_RATIONALE.md)。

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
