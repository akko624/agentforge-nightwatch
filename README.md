# AgentForge NightWatch（SQSP）— Agent 工件安全与进化平台

面向个人开发者的可运行 Agent 工件安全与进化平台。当前已支持 Agent Skill ZIP 的安全导入、规范解析、静态安全扫描、质量覆盖、版本比较和改进简报；API 与扫描 Worker 独立进程。所有结果来自上传内容，没有模拟业务数据。未可信脚本只作数据解析，平台不执行其中的命令。

Skill 是第一个已上线的工件类型，不等于平台边界。工作流、提示包和连接器将复用同一工件摄入、证据、策略、版本和进化模型，但目前不能上传或评测；不将路线图写成已实现能力。产品定位、能力边界与自演进闭环见[平台说明](docs/PLATFORM.md)。

## 报告看板与静态分享

扫描报告已加入真实数据驱动的 SVG 风险分布、质量覆盖环图、阶段状态矩阵、耗时条和 Top 风险文件表；点击风险图例可筛选下方证据。未测维度继续保持 `NOT_RUN`，完整质量分不补零。

平台的 `/viewer` 页面可在浏览器内存读取已有 JSON，不调用扫描 API。也提供完全独立的静态构建，用于公开部署报告工具或经过复核的聚合摘要：

```powershell
Set-Location frontend
npm run build:report
Set-Location ..
# 仅报告工具；输出目录必须是新目录
.\.venv\Scripts\python scripts/build_report_site.py --output release/my-report-viewer
# 同一链接直接展示聚合报告；不会复制完整源报告或自动发布
.\.venv\Scripts\python scripts/build_report_site.py --report path/to/report.json --output release/my-public-report
```

聚合摘要默认剔除原始名称、标识、路径、hash、证据、权限与日志。数值和执行来源未验签，公开前仍须确认披露范围。公共页面可以无需业务后端；直接分享同一份报告仍需要托管摘要副本。现有无认证扫描 API 不适合直接向不可信公网用户开放。

详见[设计与实现](docs/REPORT_DESIGN.md)、[可分享产物指南](docs/SHARING_GUIDE.md)、[上线与成本评估](docs/PUBLIC_DEPLOYMENT_ASSESSMENT.md)、[公共访问边界审查](docs/PUBLIC_READINESS_REVIEW.md)。

## 给其他 Agent 的开箱即用包装

仓库含有可安装的 [`skillforge-nightwatch`](agent_skills/skillforge-nightwatch/SKILL.md) Agent Skill：Agent 读取该 Skill 后可将一个本地 `.zip` 交给已启动的本机 SQSP API/独立 Worker，等待真实报告并保存为新 JSON 文件。包装器仅以数据方式上传 ZIP，不执行其中的脚本、依赖或指令；默认拒绝向非本机地址传输，远程 API 必须由调用者显式传入 `--allow-remote`。

打包为可分发 ZIP（不包含平台数据库、报告、上传 Skill 或构建产物）：

```powershell
.\.venv\Scripts\python scripts\package_agent_skill.py --output release\skillforge-nightwatch-skill.zip
```

收件人在可信 SQSP 实例已就绪后，将解压得到的 `skillforge-nightwatch` 目录放到其 Agent 的 Skills 目录即可。也可以直接调用其内置包装器：

```powershell
python .\skillforge-nightwatch\scripts\scan_skill.py `
  --skill-zip C:\path\to\candidate-skill.zip `
  --output C:\path\to\new-report.json
```

这是对可信 SQSP 服务的 Agent 接入层，不是把 API、Worker、数据库和依赖压缩进一个不透明插件；完整平台仍按本 README 的本地或 Compose 流程安装。动态/模型能力没有被该包装器替代或伪造。

## 夜间算力大赛

产品对外品牌为 **SkillForge NightWatch**，寓意“夜间守护，白天进化”；SQSP 仍是内部协议/实现简称。参赛应强调低峰异步批处理、风险/成本分层、证据驱动改进与不执行未可信 Skill 的安全边界。完整演示脚本、已实现能力、不能虚构的指标及后续路线见[参赛叙事与路线](docs/COMPETITION_NARRATIVE.md)。

## 一键容器启动

需要 Docker Engine + Compose v2，首次构建需要访问依赖与镜像仓库。在仓库根目录运行：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- Web UI：<http://localhost:8080>
- API 文档：<http://localhost:8000/docs>；OpenAPI：<http://localhost:8000/api/v1/openapi.json>
- 存活 / 就绪：`/healthz`、`/readyz`
- Compose 包括 PostgreSQL、Redis、迁移、API、独立 RQ Worker 和 nginx 前端。数据库和队列不公开端口；应用仅绑定本机回环地址。
- API / Worker 为非 root，根文件系统只读、移除 capabilities、禁止提权；没有 Docker socket 或宿主 HOME 挂载。持久数据保存在命名卷中。

当前实现环境没有 Docker，**Compose 与 PostgreSQL / Redis 容器集成尚未实跑**。本机验证采用 Python 3.13、SQLite 和独立轮询 Worker；Compose 使用 Python 3.12。两者的验证证据不能混同。

## Windows 本地启动

需要 Python 3.12 / 3.13、Node.js 22。先安装锁定依赖；启动脚本不会自动安装软件或修改用户配置。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python -m pip install --no-deps -e .
Set-Location frontend
npm ci
Set-Location ..
```

方式一：从仓库根目录启动三项真实服务：

```powershell
.\scripts\start-local.ps1
```

脚本检查端口和依赖，执行迁移、生成示例 ZIP，然后以隐藏窗口启动 API（8000）、独立 Worker、Vite（5173），并同时确认 API 就绪与前端首页 HTTP 200。它将 PID、真实命令行和进程创建时间写入 `data/local-processes.json`，日志写入 `data/local-*.log`。打开 <http://127.0.0.1:5173>。

```powershell
.\scripts\stop-local.ps1
```

停止脚本只操作已记录、且命令行 / 创建时间 / 工作区路径检查均匹配的进程；不删除数据库、工件、记录或日志，不终止占用端口的其他进程。

方式二：在三个终端手动运行。第一个终端先设置本地开发环境并迁移：

```powershell
$env:SQSP_DATABASE_URL='sqlite:///./data/sqsp.db'
$env:SQSP_QUEUE_BACKEND='database'
$env:SQSP_ARTIFACT_ROOT='./data/artifacts'
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python scripts/seed_examples.py
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

第二个终端设置相同三个环境变量，再运行：

```powershell
.\.venv\Scripts\python -m worker.worker_main
```

第三个终端：

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

本地 `database` 队列仍由独立 Worker 领取任务；API 不在线程中代跑扫描。Vite 将 `/api` 请求代理到 8000。

Windows 原生 Worker **仅支持 `database` 模式**。Redis / RQ Worker 要求 Linux，使用上述 Compose 部署；当前 RQ 版本的进程启动机制不能作为 Windows 可运行能力宣称。

## 演示真实扫描闭环

生成的上传样例位于 [examples/zips](examples/zips)：[良性](examples/zips/benign-skill.zip)、[疑似风险](examples/zips/suspicious-skill.zip)、[修复一项风险的 v2](examples/zips/suspicious-skill-v2.zip)。也可运行 `python scripts/seed_examples.py` 重建确定性 ZIP。样例只含合成数据和虚构目标，所有脚本均不会被平台执行。

1. 在 `/upload` 上传良性包，查看规范、质量维度、阶段状态和局部静态分。
2. 上传疑似风险包，按等级 / 引擎筛选，展开文件行号、证据、修复建议和误报语境。
3. 上传 v2，在 `/compare` 选择同名 Skill 的两次扫描，查看 S003 已解决、其他持续问题和策略 / 规则变化。
4. 从报告页下载完整 JSON；核对 hash、文件清单、规则版本、覆盖和门禁原因。

API 与独立 Worker 启动后，运行真实 HTTP smoke；它会新增三次扫描记录：

```powershell
.\.venv\Scripts\python scripts/smoke_test.py
# 其他地址可传 --base-url http://127.0.0.1:8000
```

Smoke 上传两个样例及 v2，经真实队列 / Worker 轮询完成报告与版本比较，并验证目录遍历 ZIP 拒绝、完整质量分为空、动态沙箱不可用。它不导入应用、不自行调用扫描函数。

## 测试与构建

开发测试依赖同样锁定（`requirements-dev.lock` 包含开发依赖）：

```powershell
.\.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python -m pytest backend/tests -q --basetemp=.pytest-tmp
.\.venv\Scripts\python -m pytest backend/tests --cov=backend/app --cov-report=term-missing --basetemp=.pytest-tmp-coverage
.\.venv\Scripts\python -m ruff check backend worker scripts
```

在 `frontend` 中运行 `npm test`、`npm run build`。前端构建包含 TypeScript 检查。

独立 PostgreSQL / Redis 集成测试 profile（需要 Docker，当前环境未实跑）：

```powershell
docker compose --profile test run --build --rm test
```

该 profile 只连接名为 `sqsp_test` 的测试库和专用 Redis，不连接应用持久数据。测试 fixture 对数据库名称作强校验；测试容器使用临时可写目录。完整测试证据和各阶段状态见 [IMPLEMENTATION.md](docs/IMPLEMENTATION.md)。

## 结果边界

- S001–S016 为自定义确定性静态规则，具有误报 / 漏报；AST 只做有限的局部数据流分析。详见 [规则说明](docs/RULES.md)。
- 质量覆盖最多 40%（规范与可维护性启发式）；缺少真实功能正确性和稳定性数据时，`quality_score = null`，不把局部静态分重归一化为完整质量分。
- 动态 Runner、模型语义分析、真实宿主质量评测和漏洞库默认没有启用，显示 `UNAVAILABLE` / `NOT_RUN`；不会用本机 subprocess 或普通容器运行上传 Skill。
- `BLOCK > INCOMPLETE > REVIEW > ALLOW`。默认请求质量评测时因真实功能维度缺失可返回 `INCOMPLETE`；即使静态配置门禁 `ALLOW` 也不是全面安全保证。
- MVP 是本机单用户工具，没有认证 / RBAC / 多租户；`owner_label` 只是标签，不是可信身份。不要直接公开到公网，不要上传生产凭据或客户数据。

## 常见问题

| 现象 | 排查 |
|---|---|
| `QUEUED` 不变 | 独立 Worker 是否启动；API 与 Worker 的数据库、队列、工件路径是否相同 |
| `/readyz` 返回 503 | 迁移是否完成；Redis 模式下队列是否可连接 |
| 本地启动提示端口占用 | 先确认占用方；脚本不会终止其他进程 |
| ZIP 被拒绝 | 检查根 Skill、路径、链接、重复名称、条目数、大小和压缩比 |
| 报告显示 PARTIAL / INCOMPLETE | 查看各阶段原因和未评测维度；该状态不会被改成虚假的全面通过 |
| 依赖扫描覆盖不足 | 补齐固定版本与锁文件；当前未查询漏洞数据库，不能解释为没有漏洞 |

本机最终验证：后端 200 passed / 1 skipped（真实 Redis 未配置）、覆盖率 94%；前端 14/14、TypeScript / build 通过，真实 HTTP 与 Edge UI 流程通过。Compose / PostgreSQL / Redis 容器验证仍待具备 Docker 的环境执行。

更多信息：[交付清单](DELIVERY.md)、[架构](docs/ARCHITECTURE.md)、[安全边界](docs/SECURITY.md)、[API](docs/API.md)、[实现决策](docs/DECISIONS.md)、[阶段报告](docs/IMPLEMENTATION.md)。
