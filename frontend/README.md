# QuantSandbox 研究工作台

Vue 3、TypeScript、Vite 8 与 Lightweight Charts 5。要求 Node.js 22.12+。

```powershell
npm ci
npm run dev
```

默认地址 http://127.0.0.1:5173，/api 代理到本地 8000 端口。
使用 QUANT_API_PORT 环境变量覆盖 API 端口。根目录 scripts/dev.ps1 可同时启动前后端。

```powershell
npm run typecheck
npm run build
npm run format
```

- src/workspace/：任务选择、初始化、轮询、来源标记及回放会话。
- src/api/、src/types.ts：HTTP 边界与 API 类型。
- src/views/：推演终端、总览、实验室、数据中心、研究档案。
- src/components/：图表、账本、决策证据、回放控制、配置表单。
- src/style.css：设计变量、交互状态及响应式布局。
- DESIGN.md：设计参考、文字约束及实现差异。

首个空工作区会创建一项明确标识的合成数据演示研究。行情服务失败时显示错误。
普通回放在浏览器按游标计算；盲测视图只消费服务器会话投影。
