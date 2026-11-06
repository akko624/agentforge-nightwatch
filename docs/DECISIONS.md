# 实现决策

## 2026-11-03：开发环境与验证边界

规格书要求 Compose 中 PostgreSQL + Redis / RQ，交付保留该部署架构。当前主机没有 Docker 命令，原生开发验证使用 SQLite 与独立数据库轮询 Worker。其目的是完成真实 API → 队列 → Worker → 报告闭环，不把静态假数据或 API 线程当作替代实现。

备选方案是等待 Docker 环境再开始全部实现；这样会阻塞不依赖容器的安全导入、静态扫描和报告代码。影响是本地证据不能推导 PostgreSQL / Redis 容器集成已通过；该限制在 README 和阶段报告明确保留。

对当前锁定 RQ 版本的实际源码核对发现，SpawnWorker 的启动路径依赖 `os.posix_spawn`，不能宣称 Windows 可用。Windows 仅运行独立 `database` Worker；Redis / RQ Worker 限 Linux Compose。没有为兼容性改成在 API 进程中执行扫描或运行上传代码。

## 默认禁用动态 / 模型能力

动态沙箱、外部扫描器和真实宿主质量评测采用扩展契约。没有明确版本兼容性、隔离自检和批准的模型环境时，不运行也不返回空 findings 伪装通过；返回 `UNAVAILABLE` / `NOT_RUN`。未实施真实功能和稳定性评测时 `quality_score` 始终为空。

## 归档保持内存解析，不展开到宿主目录

MVP 在有界内存中读取已校验条目，完成所有文件编目与文本 / AST 分析；只保存平台控制 key 下的原始 ZIP 与报告。相比真正的目录解包，该方式消除不可信目标路径写入、链接跟随与 TOCTOU 暴露面。后续外部扫描器若需要目录，应在额外隔离环境中建立只读副本，不在当前 Worker 临时执行脚本。

## 质量阶段与门禁保持部分完成

规范与可维护性分别占完整质量模型 20%，MVP 最多完成 40% 覆盖；功能正确性和稳定性保持未运行。完整评分为空，质量阶段为 PARTIAL。用户请求的阶段也进入门禁必需集，因此请求质量 / 动态而能力不足时可得到 INCOMPLETE；静态 findings 清洁不会掩盖能力缺失。

## 依赖与构建可重复性

Python runtime 与开发测试依赖分别使用带 SHA256 的 `requirements.lock`、`requirements-dev.lock`；容器以 `--require-hashes` 安装。前端使用精确 package 版本及 `npm ci`。第三方外部 CLI 尚未激活；不依赖其未经固定的输出契约。镜像使用明确版本标签，生产化时仍应进行镜像审计并进一步锁定 digest。

## 验证证据分层

Phase 0–3 已有本机自动化、独立进程 HTTP 与 Edge 浏览器操作证据，详见 `IMPLEMENTATION.md`。SQLite、模拟队列测试或 Compose YAML 解析不能替代真实 PostgreSQL / Redis 集成。已交付独立测试 profile，缺少 Docker 的限制保留为未验证项；真实 Redis / RQ 测试因未配置测试 Redis 跳过，不计为通过。

## 入队与完成时校验源码 / 配置漂移

扫描入队记录规则集、策略与后端源码 hash。Worker 开始分析和持久化结果前重新校验；中途部署或修改配置导致签名不一致时，以 `SCAN_CONFIG_CHANGED` 失败并保持 INCOMPLETE，要求创建新扫描，不将新代码结果写成旧版本来源。优先选择明确失败，而不是悄悄更新报告来源并使复用 / 比较语义失真。

## 租约领取与完成使用条件更新

任务领取、完成保存以及租约耗尽清理使用 scan_id / status / lease_token 等条件更新。清理者在 SELECT 后若遇到 Worker 已完成，CAS 更新不再匹配，不覆盖成功结果；持久化前也不能让旧租约拥有者覆盖新 Worker。数据库唯一约束保护同版本和 finding 重试去重。此处保证的是状态一致性，不声称任务处理恰好执行一次。

## 权限交集保守拒绝且 deny 优先

Skill 声明不自动授予权限。平台批准与作者请求求保守交集，deny 优先于 read / write；未知 glob 交集也拒绝，不展开 HOME / WORKSPACE 模板访问宿主。报告保留请求、有效权限与执行层未启用状态；这是声明核对，不能冒充已启用沙箱授权网关。

## OpenAPI 驱动前端类型

实际 FastAPI / Pydantic 结构导出为 `docs/openapi.json`；`scripts/generate_api_types.py` 从组件 schema 生成 `frontend/src/api/generated.ts`。转换器对不支持的 schema 构造明确报错，不悄悄降级为 any；前端构建执行 TypeScript 检查，回归测试检测契约漂移。统一 ErrorEnvelope 同时记录在 OpenAPI，而非保留默认的另一套 422 结构。
