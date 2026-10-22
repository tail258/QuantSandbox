# QuantSandbox

本地量化研究工作台，把策略回测、成交解释、历史分叉和稳健性实验放在同一条研究流程中。

选择行情与策略，运行共享资金账户；沿时间轴查看信号和成交，在某一天改变策略或仓位，再比较结果。配置、数据快照、成交账本和笔记可保存、导出并重新计算。

![QuantSandbox 研究终端：行情、成交证据与历史分支对照](docs/images/workbench.png)

图中展示合成演示行情。

## 可以做什么

| 工作区 | 用途 |
| --- | --- |
| 研究总览 | 创建回测、选择策略、查看任务进度和研究记录 |
| 推演终端 | 联动查看 K 线、净值、成交账本和决策证据，逐日回放并创建历史分支 |
| 实验室 | 比较费用、滑点、执行延迟和仓位情景，执行参数敏感性与滚动样本外实验 |
| 数据中心 | 查看数据来源、时间范围、价格口径和快照指纹 |
| 研究档案 | 保存笔记、导出证据包、导入后重算并核对结果 |

内置双均线、布林带、RSI 和动量策略。研究指令通过本地规则解析成可检查的配置草稿。

## 快速开始

需要 Python 3.12+、Node.js 22.12+；Windows 启动脚本使用 PowerShell 7。

```powershell
git clone https://github.com/tail258/QuantSandbox.git
cd QuantSandbox
pwsh -File scripts/setup.ps1
pwsh -File scripts/dev.ps1
```

打开 <http://localhost:5173>。首次启动保留空研究空间，点击“运行合成数据示例”体验合成行情，或通过“新建回测”配置自己的研究。合成行情支持离线运行。

按 `Ctrl+C` 停止本次启动的前后端及计算进程。指定其他端口：

```powershell
pwsh -File scripts/dev.ps1 -ApiPort 8001 -WebPort 5174
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt -c requirements-lock.txt
npm ci --prefix frontend
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 在另一个终端启动前端
npm run dev --prefix frontend -- --host 127.0.0.1
```

### 使用真实行情

Windows 安装可选数据依赖：

```powershell
pwsh -File scripts/setup.ps1 -MarketData
```

其他系统使用 `.venv/bin/python -m pip install -r requirements-market.txt -c requirements-lock.txt`。

创建回测时选择 AKShare。行情请求依赖外部服务及本机网络；请求失败会显示错误并保留所选来源。数据中心可检查实际使用的快照。

## 一次研究的流程

1. **建立基线**：选择日期、股票池、策略参数、初始资金和交易成本。
2. **核对交易**：点击成交，查看信号日期、指标、执行价格、费用和现金变化。
3. **提出对照**：在某日收盘后改变策略或仓位，沿用同一份行情创建分支。
4. **检查稳健性**：从基线发起压力、参数或滚动样本外实验。
5. **保存证据**：记录判断，导出研究包；以后导入可重新计算并比较账本与指标。

盲测模式按游标返回可见历史与重新计算的指标，揭晓状态会持久保存。它用于本地练习和复盘；普通研究接口仍能访问完整结果。

## 计算与数据口径

- **执行时间**：收盘信号最早在该标的下一个可交易日开盘执行；多标的共享现金，按代码稳定排序、先卖后买。
- **账户规则**：默认整手 100 股、T+1、最低佣金、卖出税费与双边滑点；费用计入现金和完整平仓损益。
- **仓位含义**：仓位参数是每次入场的资金预算比例；期末持仓按收盘估值，基准为不含费用的等权买入持有。
- **真实价格**：当前使用未复权日线，尚未记账分红送转、退市收益和完整逐日证券规则。日线撮合不包含盘口、成交队列或市场冲击。
- **演示行情**：覆盖 2019-01-01 至 2026-09-18，使用工作日历和明确的合成来源标记。
- **实验含义**：参数比较衡量同一区间敏感性；滚动样本外按训练窗口选参，并在连续账户上执行后续测试窗口。目前没有独立的最终保留测试集，分支结果暂不支持直接运行实验。
- **历史分叉**：复用原快照，从起点确定性重放；检查点用于审计与展示。
- **证据重放**：保存配置、OHLCV、结果、数据指纹和执行时源文件指纹。导入校验完整性，再用当前引擎重算并报告差异。原始 JSON 文件应直接上传，避免数值重新序列化改变校验值。

## 架构

前端使用 Vue、TypeScript、Vite 和 Lightweight Charts；后端使用 FastAPI、Pandas、SQLite 和 Parquet。服务面向本机单用户，默认绑定回环地址；计算任务在独立进程中串行执行，支持取消。

```text
frontend/src/
  views/              页面与研究交互
  components/         图表、成交账本、配置表单
  workspace/          初始化、任务轮询、回放与界面状态
  api/                HTTP 请求边界

backend/
  main.py             应用装配、生命周期与错误映射
  api/routes/         按功能分组的 HTTP 接口
  api/schemas.py      请求校验
  api/responses.py    按研究类型区分的响应契约
  services/           研究、会话、证据包、笔记、任务调度和持久化
  core/               策略、账户、撮合、指标、行情适配和快照
  research.py         压力、参数与滚动样本外实验
```

接口层调用研究服务，回测内核可直接接收行情和配置独立运行。数据源、快照和账户撮合分别维护清晰的职责；策略默认值与编辑元数据集中定义。研究列表只读取摘要，完整行情和账本按需加载。

运行数据默认保存在 `data/`。设置 `QUANT_SANDBOX_DATA_DIR` 可使用独立目录，设置 `QUANT_API_PORT` 可调整前端开发代理的 API 端口。进程中断的活动任务标记为失败，可重新提交；已完成研究和快照保留。

## 开发与验证

```powershell
# 后端测试、前端状态测试、类型检查与生产构建
pwsh -File scripts/check.ps1

# 分别执行
./.venv/Scripts/python.exe -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend

# 合成行情内核基准，不含下载、磁盘和进程启动
./.venv/Scripts/python.exe scripts/benchmark.py --symbols 100
```

测试覆盖信号因果性、现金与费用守恒、分叉历史一致性、盲测截断、缓存缺口、证据包重放、进程取消、响应契约，以及前端轮询和会话竞态。CI 在 Windows / Linux 上执行后端测试，并执行前端测试与构建。

- [架构与扩展约定](docs/ARCHITECTURE.md)
- [API 契约](docs/API_CONTRACT.md)，运行服务后也可访问 <http://127.0.0.1:8000/docs>
- [后续方向](docs/ROADMAP.md)
- [视觉规范](docs/design/SPEC.md)

项目采用 [MIT License](LICENSE)，用于量化研究与教学。
