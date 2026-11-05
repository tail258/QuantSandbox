# US company research / 美股公司研究

## English

The initial catalog contains McDonald’s Corporation, NYSE **MCD**, SEC CIK **0000063908**. This is a local research foundation: cached annual SEC financial facts, filing references, manual price imports and project-linked research evidence. It does not provide US strategy backtesting, order placement, automatic live quotes, quarterly financial analysis or full-market coverage.

### Setup and workflow

Before starting the service, set `QUANTSANDBOX_SEC_USER_AGENT` to an identifying application name and your real contact information. It is a public HTTP User-Agent, not an API key. Configure your own value locally; never commit personal contact details. Restart the service after changing its environment.

Open US company research for MCD, select the intended project, then explicitly refresh SEC data when a newer snapshot is needed. Reads reuse the local cache. SEC access and manual CSV imports require no paid subscription. Network restrictions, SEC throttling or failed requests must remain visible; a failed request is not evidence that filings do not exist.

Import a CSV containing `date,open,high,low,close,volume`, with dates as `YYYY-MM-DD`, prices in USD and volume in shares. Supply the original data source URL. Only import unadjusted daily prices: adjusted closes must not be presented as executable prices. The source URL records provenance; an import does not independently certify the supplier’s corporate-action handling. No paid price provider is bundled.

Save research to the selected local project. Preserve its snapshot identifiers and evidence rather than refreshing inputs during reproduction. Local datasets, research records, source attachments, exports and personal settings are excluded from GitHub.

### CLI and export

Read the cached company with `.\.venv\Scripts\python.exe -m backend.workbench.cli us-company`; add `--refresh` for an explicit SEC refresh. Saved research exports include `report.md` (English), `report.zh-CN.md` (Chinese), archived recipe/snapshots and CSV data. Saving through the API requires the displayed `snapshot_ids`, with an optional `project_id`, so saving uses the reviewed inputs rather than whichever cache is newest.

### Interpretation and verification

Financial output uses annual periods from SEC company facts. Balance-sheet values are period-end stocks; income and cash flows are annual flows. Current SEC facts can contain later revisions and are **not historical point-in-time financial statements**. Keep report period, filing date and retrieval time distinct; unknown publication times stay unknown. Missing facts remain missing. USD financial units and per-share units must be read alongside each fact.

Filing links are an index to original documents, not a claim that every filing has been downloaded or reviewed. Inspect the original filing for franchise economics, systemwide sales versus reported revenue, comparable sales, debt, leases and accounting definitions. Reproduce calculations against the same cached inputs and run the module’s fixed-fixture tests plus the repository checks (`pwsh -File scripts/check.ps1`); a live SEC request is an integration check, not a deterministic test.

Official identity and source references: [SEC entity record](https://www.sec.gov/edgar/browse/?CIK=63908), [SEC 2025 10-K](https://www.sec.gov/Archives/edgar/data/63908/000006390826000035/mcd-20251231.htm), [McDonald’s financial information](https://corporate.mcdonalds.com/corpmcd/investors/financial-information.html). These identify the company and source documents; they do not imply the local cache already contains them.

## 中文

首期目录包含麦当劳（NYSE：**MCD**，SEC CIK：**0000063908**）。模块提供本地缓存的 SEC 年度财务、申报索引、手动行情导入与项目研究证据保存；不包含美股策略回测、交易下单、自动实时行情、单季度财务分析或全市场覆盖。

启动服务前，将 `QUANTSANDBOX_SEC_USER_AGENT` 设置为应用名称及自己的真实联系信息。这是公开 HTTP 请求标识，不是 API 密钥；仅在本机配置，不提交个人联系信息。修改后重启服务。页面打开麦当劳研究后选择目标项目，确需新数据时再手动刷新；普通读取复用缓存。SEC 与手动 CSV 导入不要求付费订阅。网络限制、限流与失败应保留，不得将失败解释为没有公告。

行情 CSV 使用 `date,open,high,low,close,volume`，日期为 `YYYY-MM-DD`，价格为美元未复权日线，成交量为股；必须填写原始来源 URL。来源记录不等于独立验证供应商的复权处理；不得将复权收盘价冒充可成交价格。模块没有内置付费行情服务，美股行情不接入 A 股回测。

财务按 SEC 年度口径读取：资产负债为期末时点，利润与现金流为全年流量。当前 company facts 可能包含后续修订，不能视为历史 point-in-time 财报。报告期、申报日期、获取时间分别保留；未知发布时间不推测，缺失不补零，金额与每股单位分别核对。申报链接是原文索引，不表示已经下载或逐份核验。麦当劳研究需结合原文区分系统销售额和报表收入、加盟经济、同店销售、债务和租赁口径。

保存时绑定所选本地项目，复现使用同一快照与证据编号；本地数据、研究档案、原文附件、导出与个人设置不上传 GitHub。固定输入测试及 `pwsh -File scripts/check.ps1` 用于复现检查；实时 SEC 请求只用于连接检查。官方来源见上方 SEC 公司页、10-K 与公司投资者关系链接；链接存在不代表本机已有缓存。

CLI：`.\.venv\Scripts\python.exe -m backend.workbench.cli us-company` 读取缓存，添加 `--refresh` 才刷新 SEC。保存 API 必须提交当前展示的 `snapshot_ids`，可同时指定 `project_id`；导出包含英文 `report.md`、中文 `report.zh-CN.md`、配方、原始快照及 CSV。
