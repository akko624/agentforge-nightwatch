# SQSP Web

```powershell
npm ci
npm run dev
npm test
npm run build
```

使用 Node 22.12+。Vite 将 `/api`、`/healthz` 与 `/readyz` 代理至本地 8000 端口。

## API 契约

从仓库根目录先运行 `python scripts/export_openapi.py`，然后在此目录运行：

```powershell
npm run generate:api
npm run build
```

`src/api/generated.ts` 由后端 OpenAPI 生成，勿手动修改。扫描摘要、Finding、阶段、上传结果等核心 DTO 直接引用生成类型；报告中尚为无类型字典的嵌套数据在 `src/types/index.ts` 细化。后端未来为这些字典加入 Pydantic 模型后，应同步替换为生成类型。

类型由仓库内 Python 标准库脚本生成，不需要额外 npm 代码生成依赖。脚本只支持本项目 OpenAPI 使用的类型组合；不支持的结构必须明确失败，不能静默退化为 `any`。它读取仓库内可信规范，不加载上传的 Skill 或远程文档。
