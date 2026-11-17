<p align="center"><img src="docs/images/readme-header.svg" alt="QuantSandbox · 可追溯、可检验、可复现的投资研究" width="100%" /></p>
<h1 align="center">QuantSandbox</h1>
<p align="center"><strong>本地投资研究与量化分析工作台</strong></p>
<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong> · <a href="#工作台预览">工作台预览</a> · <a href="#打开与安装">快速开始</a> · <a href="CONTRIBUTING.md">参与贡献</a> · <a href="https://github.com/tail258/QuantSandbox/releases">下载发布</a></p>
<p align="center"><a href="https://github.com/tail258/QuantSandbox/actions/workflows/check.yml"><img src="https://github.com/tail258/QuantSandbox/actions/workflows/check.yml/badge.svg" alt="自动检查" /></a> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-959DA7?style=flat-square" alt="MIT" /></a> <img src="https://img.shields.io/badge/markets-read--only-F5C542?style=flat-square" alt="市场只读" /></p>

在同一个本地工作台完成公司研究、产业观察、统计分析与策略验证。浏览器用于交互，Python 负责数据、计算和证据；Codex 可通过 CLI 与 API 调用同一套逻辑。市场操作只读，没有券商连接或实盘下单。

## 工作台预览

![金融终端主题：合成双均线回测、行情图、成交证据与重放控件](docs/images/replay-synthetic-zh.png)

*金融终端主题下的策略重放。截图里即使出现真实证券代码，示例价格也是合成的，用于演示如何复核，不代表实盘或历史业绩。*

可以先跑[离线示例](#离线复现)，无需行情账户就能生成并校验同一份证据。

## 美股公司研究 · 首期范围

独立美股研究模块从 **麦当劳（NYSE: MCD）** 开始：手动刷新公开 SEC 年度财务与申报索引，导入附来源 URL 的美元未复权日线 OHLCV CSV，并将研究证据保存到本地项目。界面支持中英文。美股行情不进入 A 股回测引擎。访问 SEC 需自行配置带真实联系信息的 User-Agent；SEC 与手动导入不要求付费数据订阅。配置、来源和限制见[美股研究指南](docs/us-equities.md)。

## 打开与安装

下面的命令克隆当前公开 main；需要固定版本，可下载 [v3.2.0 源码包](https://github.com/tail258/QuantSandbox/releases/tag/v3.2.0)。新版标的研究、日线缠论重放和策略更新可从 main 获取。

已有环境双击 `start.cmd`，打开 **http://127.0.0.1:8766**。只监听本机；ETF资金观察支持“立即刷新”，默认每天北京时间15:30自动取数，可关闭或修改时间。自动取数仅在工作区服务运行时执行，保留实际数据日期、来源和失败原因；不自动写入笔记库。详见[ETF方法说明](docs/etf-methodology.md)。

界面默认英文，可在顶部切换 English / 中文。主题提供原有经典浅色与黑灰金色的金融终端主题；语言和主题选择保存在当前浏览器，刷新后保留。切换只影响界面展示，研究原文、用户输入和归档证据保留原样。

ETF页面还提供轻量盘中报价及完整5分钟时点的成交额比较，报价与历史基准分开更新，显示来源时间、有效样本和缺口；详见[盘中方法说明](docs/etf-intraday.zh-CN.md)。

<details>
<summary><strong>预览离线合成ETF演示</strong></summary>

![合成ETF示例：固定人工输入、来源精度、20个样本和1.5倍成交额比值](docs/images/etf-demo-zh.png)

进入 **ETF资金 → 查看合成演示**。示例使用人工数据与固定时钟，不下载行情，也不替换本机研究数据。

</details>

```powershell
git clone https://github.com/tail258/QuantSandbox.git QuantSandbox
Set-Location QuantSandbox
.\setup.cmd
.\start.cmd
```

Windows 需要 Python 3.12+、Node.js 22.12+ 和 PowerShell 7。安装包括公开行情依赖与前端构建；生产运行只需要 Python。停止：`pwsh -NoProfile -File stop.ps1`。Codex 启动使用 `pwsh -NoProfile -File start.ps1 -NoBrowser`。

**让 Codex 驱动研究：** Windows 安装会写入本项目的 MCP 配置。Codex 可以查项目和固定快照、预检并提交回测、查证据及保存项目结论。已装好环境时，直接运行 `pwsh -File scripts/enable-codex.ps1`。详见 [Codex 工作流](docs/codex-workflow.zh-CN.md)。

在**研究项目**首页选择**打开离线策略演示**。从一个日线均线问题出发，先运行基准策略，再在同一份合成快照上调整窗口并重放证据。演示需要本机服务，不改动真实研究项目、记录或缓存。

在研究项目打开**缠论结构**，用固定日线快照或离线示例逐根查看分型、笔、线段和中枢。时间轴保留结构首次出现、确认和撤销，支持导出原始证据并重放。见[日线缠论使用说明](docs/chan-replay.zh-CN.md)和[项目交接](HANDOFF.md)。

首次使用可按[上手指南](docs/getting-started.zh-CN.md)体验离线策略与 ETF 演示、区分刷新按钮，再保存第一个研究项目。维护者见[发行验收清单](docs/release-readiness.zh-CN.md)和[策略研究开发计划](docs/strategy-development-plan.zh-CN.md)。

首页可直接打开沪深股票或 ETF，看到已完成日线、周线、可定位的结构依据和观察条件。详见[个股与 ETF 研究](docs/stock-decision.zh-CN.md)。

## 页面与研究流程

导航按研究、市场观察、验证、数据与归档组织导航。首页采用项目列表与当前详情并排的布局，提供概览、证据、实验和结论；创建项目按需打开。当前项目贯穿页面，已保存的公司比较、统计和策略实验保留项目关联。

财务和统计优先展示结果，参数及公司配置按需展开。策略终端联动行情与成交证据，账本和决策分栏查看；实验室先展示已有结果，再创建对照。手机采用研究、市场、验证、更多四类入口。

Obsidian 默认显示排版笔记，可切换 Markdown 源码；本机路径设置按需打开。

### 从观察到归档

1. 在数据中心获取行情、财报或公告，检查来源、实际截止日与口径。
2. 按公司配置比较单季度财务，观察产业指标或 ETF 资金，保存统计分析。
3. 新建研究项目，关联研究问题和分析记录；将固定的未复权股票行情送入策略实验。
4. 在策略实验中核对资金、成交与信号，创建历史分叉，检验费用、参数和滚动样本外表现。
5. 保存证据，选择导出 Markdown、附件或完整可复算研究包。

| 模块 | 能力 |
| --- | --- |
| 研究项目 | 统一研究问题与股票池，关联研究分析、回测和后续实验 |
| 数据中心 | 沪深日线、估值字段、三大财报、公告、股东户数、RU0、带来源 CSV 导入 |
| 财务与公司配置 | 自动拆单季度；一般工商、周期、银行、保险模板；同行、指标和观察重点 |
| 产业周期 | 橡胶价格与行业指标观察，缺失数据保留导入与检索入口 |
| ETF 与国家队足迹 | 交易所份额、净值估算申赎、历史分位、融资对照、原文持仓和公告时间线 |
| 统计实验 | 变换、领先滞后、条件概率、样本量、基准与 Wilson 区间 |
| 策略实验 | 双均线、成交量确认、波动率入场控制、布林带、RSI、动量、预算内买入持有。支持共享账户、成交解释和对照实验 |
| 逐日推演 | 按游标推进，盲测与揭晓，保留成交、决策和账户审计 |
| 证据归档 | 原始快照、参数、引擎指纹、结果导出与重放校验 |
| Obsidian | 可选 Markdown 与附件包；本机配置笔记库，预览后手动写入 |

## 数据与证据

研究快照存于 `data/workbench/workbench.sqlite`，策略任务与行情快照存于 `data/`；数据与代码分开。桥接实验会引用指定的研究行情快照，保留来源与哈希，不因后续更新而改变。前后复权行情不能作为当前账户模型的成交价格。

真实行情依赖公开上游，失败会明确报告；不会静默替换成演示行情。演示来源为合成数据。新克隆仓库没有本机缓存或个人研究档案，可先运行合成示例，再手动获取真实数据。

财报接口可能返回当前修订版本。国家队持仓以原文实体证据为准，ETF 申赎与融资只是市场代理。固定当前成分名单回看历史不作为时点选股证据。策略采用未复权日线撮合，含公告证据的快照可记账税前现金红利。停牌、涨跌停价及分红字段随快照和证据包保存并参与哈希，未知字段留空。分红税、非现金公司行动和完整退市收益尚未建模。

方法见 [统计与财务](docs/methodology.md)、[ETF](docs/etf-methodology.md)、[国家队足迹](docs/national-methodology.md)、[回测口径](docs/RESEARCH_NOTES.md)。

## 可选 Obsidian 模块

工作台不依赖任何特定笔记库。默认下载通用 Markdown 与附件包，无需配置或读取笔记库。需要直接保存时，由用户在 Obsidian 页面配置本机目录，预览内容，再手动执行单次写入。配置仅保存在本机，不上传 GitHub；不扫描私人笔记、不自动同步、不覆盖已有文件。

详见 [Obsidian 模块](docs/obsidian.md)。

## 离线复现

安装依赖后，无需启动服务、下载行情或读取个人缓存，即可运行固定的合成示例：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/reproduce.py
```

示例在两个独立临时目录中计算基线、导出证据、导入并重放，核对固定快照与结果哈希；不一致时返回失败。想在页面打开截图中的示例，运行时加上 `--output exports/repro-demo`，目标须为新目录或空目录。启动工作台，在「验证 → 策略与推演」中打开「记录操作 → 导入证据包」，选择原始的 `exports/repro-demo/evidence.json`。完整说明见 [离线复现](docs/reproducibility.md)（英文）。

[Release](https://github.com/tail258/QuantSandbox/releases) 提供固定提交的源码 ZIP、发布清单及 SHA256SUMS。源码包不含个人数据、依赖或预构建前端；按安装步骤构建即可使用。[发布说明](docs/releases.md)（英文）介绍校验与重新打包方法。

## 迁移与备份

原有策略数据位置保持兼容。旧研究工作区的数据可以只读复制到本工作区：

```powershell
.\.venv\Scripts\python.exe scripts/import_research.py --source '旧研究工作区的绝对路径'
```

工具使用 SQLite 在线备份保留已提交 WAL 数据，并拒绝覆盖已有目标。复制研究附件时排除外部交接文件和可执行辅助脚本；不复制私人笔记库。原工作区保持独立。迁移细节见 [融合与迁移](docs/MIGRATION.md)。

备份时先停止本工作台，再备份整个 `data/`、`exports/`，以及按需保存 `data/.local/obsidian.json`。GitHub 只同步代码、依赖与方法文档；这些本地数据、笔记库配置、虚拟环境与构建产物均被忽略。

## 开发与 Codex

先读 [AGENTS.md](AGENTS.md)。研究 CLI：`python -m backend.workbench.cli status`；策略 API 保持 `/api/runs` 等路径，研究 API 为 `/api/research/*`，统一文档为 `/docs`。

```powershell
pwsh -File scripts/dev.ps1
pwsh -File scripts/check.ps1
```

开发前端默认 http://127.0.0.1:5174，API 默认 8000；生产默认 8766。支持通过脚本参数改端口。架构见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)，接口见 [API_CONTRACT.md](docs/API_CONTRACT.md)。

## 反馈与贡献

[贡献指南](CONTRIBUTING.md)介绍环境、测试和计算边界；问题请使用 [Bug 模板](https://github.com/tail258/QuantSandbox/issues/new?template=bug_report.yml) 或 [功能建议](https://github.com/tail258/QuantSandbox/issues/new?template=feature_request.yml)。安全问题使用 [私密漏洞报告](https://github.com/tail258/QuantSandbox/security/advisories/new)，详见 [安全政策](SECURITY.md)。公开反馈使用合成样例或脱敏步骤，不上传个人研究缓存或笔记。

当前计划见 [路线图](docs/ROADMAP.md)，变更见 [CHANGELOG](CHANGELOG.md)。软件采用 [MIT 许可证](LICENSE)；第三方市场数据的使用和再分发仍遵循其来源条款。
