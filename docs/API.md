# API 契约

运行时 OpenAPI 是请求 / 响应结构的事实来源：`GET /api/v1/openapi.json`，交互文档 `/docs`。真实导出保存在 [openapi.json](openapi.json)，前端 DTO 位于 `frontend/src/api/generated.ts`。

所有业务失败采用 Pydantic `ErrorEnvelope` / `ErrorBody`：

```json
{"error":{"code":"INVALID_ARCHIVE","message":"Unsafe or invalid ZIP archive","details":{"reason":"path_traversal"},"request_id":"request-uuid"}}
```

`code/message/request_id` 是字符串，`details` 是对象。API 路由在 OpenAPI 中为 400 / 404 / 409 / 413 / 422 / 500 / 503 声明统一 ErrorEnvelope；并非采用 FastAPI 默认的 `detail` 校验结构。请求校验失败为 422 / VALIDATION_ERROR，details.issues 只包含 location 与 type，不回传可能含凭据的原始 input / ctx。常规响应提供 `X-Request-ID` 便于定位。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 存活与应用版本 |
| GET | `/readyz` | 数据库迁移状态；Redis 模式额外检查队列连接 |
| POST | `/api/v1/skills/upload` | multipart `file` ZIP、`owner_label` 可选；201 返回 skill_id / version_id / sha256 |
| GET | `/api/v1/skills` | q / offset / limit；返回 items / total |
| GET | `/api/v1/skills/{id}/versions` | 同一 Skill 的版本、manifest 与文件清单 |
| POST | `/api/v1/scans` | version_id、modes、force；202 返回 scan_id / status |
| GET | `/api/v1/scans` | q / status / offset / limit；Dashboard 扫描列表 |
| GET | `/api/v1/scans/{id}` | 阶段、质量覆盖、风险、门禁、版本与时间 |
| GET | `/api/v1/scans/{id}/findings` | severity / engine / offset / limit；每页最多 200 |
| GET | `/api/v1/scans/{id}/quality` | dimensions / coverage / score / static_subscore / reasons |
| GET | `/api/v1/scans/{id}/report?format=json` | 完整 JSON，attachment 响应头；未完成返回 409 REPORT_NOT_READY |
| GET | `/api/v1/compare?left={id}&right={id}` | 仅同一 Skill；新增 / 解决 / 持续 / 证据变化，质量与版本可比性 |
| GET | `/api/v1/rules` | category 可选；规则与引擎版本 |

上传只接受本地 ZIP，不接受 URL。所有 ZIP / YAML / 资源限制失败有精确错误码，例如 `INVALID_ARCHIVE`、`ARCHIVE_LIMIT`、`UNSAFE_YAML`、`INVALID_FRONTMATTER`、`INVALID_SKILL_NAME`、`INVALID_SECURITY_DECLARATION`、`INVALID_EVALS`。

入队后源码 / 规则 / 策略签名发生变化时，扫描以 `SCAN_CONFIG_CHANGED` 失败，报告不伪装为原签名运行结果；队列失败、工件 hash 不符、租约耗尽分别保留明确错误码。`permissions` 报告包含声明与平台批准的交集，`execution_enforcement` 仍为 UNAVAILABLE。

扫描模式为 `schema`、`static`、`dependencies`、`semantic`、`dynamic`、`quality`；默认 `schema/static/quality`。同工件、同模式、同规则 / 策略 / 扫描器签名默认复用已有非失败扫描；`force: true` 创建新扫描。API 立即返回，报告由独立 Worker 生成。

```json
{"version_id":"上传接口返回的UUID","modes":["schema","static","quality"],"force":true}
```

扫描生命周期为 `QUEUED/RUNNING/COMPLETED/PARTIAL/FAILED`；每个阶段单独返回 `NOT_RUN/RUNNING/PASSED/FINDINGS/PARTIAL/ERROR/TIMEOUT/UNAVAILABLE` 和原因。动态始终显示默认不可用；请求未配置能力时门禁不会返回虚假的全面通过。

完整质量分 `score` 保持 null，静态子分与覆盖单独展示。风险指数仅用于排序，不能证明安全；发布门禁优先级为 `BLOCK > INCOMPLETE > REVIEW > ALLOW`。比较会提示规则、策略、扫描器与阶段覆盖变化，不把静态差异解释为真实任务成功率变化。

MVP 没有用户认证、人工审核或白名单修改 API。`owner_label` 是不可信标签，所有真实身份授权与审核流程留给后续阶段。

契约再生成：

```powershell
.\.venv\Scripts\python scripts/export_openapi.py
.\.venv\Scripts\python scripts/generate_api_types.py
```

`backend/tests/test_api_types.py` 检查导出与前端生成结果；转换器不支持的 schema 构造会失败，而不是隐式扩大类型。
