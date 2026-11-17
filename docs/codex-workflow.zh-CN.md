# 用 Codex 操作 QuantSandbox

Windows 的 `setup.cmd` 会安装工作台并配置本项目的 `quantsandbox` MCP。已有环境只需运行 `pwsh -NoProfile -File scripts/enable-codex.ps1`，无需重新装包。重启 Codex，在受信任的 QuantSandbox 工作区打开对话，输入 `/mcp` 可检查是否已加载。首次调用工具会按需在后台启动工作台；桌面快捷方式仍可直接打开界面。

可以直接交代研究目标，例如：

> 在潍柴项目里，用同一份未复权日线快照比较 5/20 日双均线和买入持有。先看预热和数据覆盖；缺数据再补，保留实际截止日。费用和区间保持一致，跑完汇报收益、最大回撤、交易成本和主要局限，把结论与证据编号保存回项目。

| 阶段 | Codex 可调用的工具 |
| --- | --- |
| 找到并接续项目 | `list_projects` 按名称或代码筛选，`get_project` 查问题、证券、结论和关联记录。需要时用 `create_project` 新建。 |
| 核对数据和来源 | `list_cached_research` 查缓存，`get_research_record` 读已关联的统计或财务记录，`list_chan_snapshots` 查项目未复权日线。确实缺数据时用 `fetch_daily_snapshot` 补公开 A 股日线，核对实际观测区间和上游警告。 |
| 预检并执行实验 | `get_strategy_catalog` 查参数及费用；`preview_fixed_backtest` 核对快照完整性、证券归属、观测区间、指标预热和可核验的日历缺口。把返回的 `submission` 交给 `submit_fixed_backtest`，工作台会保存运行并关联到项目。 |
| 复核与归档 | 用 `list_strategy_runs` 按项目找记录，`get_strategy_run` 查状态、结果和证据下载链接。按用户要求用 `save_project_conclusion` 保存结论，附输入快照和运行编号。 |

同一个预检计划重复提交会返回已有运行；需要重试失败记录时，先查失败原因，再明确创建一份新的计划（例如用新的运行名称标记重试）。保存结论会比较最近读到的项目版本；有并发更新时，先重读并保留仍然适用的原有内容。没有源日历时不能从自然日间隔推断缺了哪些交易日。缠论分析用 `analyze_chan_snapshot`；没有真实快照时，`run_strategy_demo` 可单独验证合成数据的计算和重放。

在[个股与 ETF 页面](stock-decision.zh-CN.md)工作时，可以用 `get_stock_decision` 读取该标的的快照、日线条件、周线背景、证据与可选因子。用户确实需要最新公开行情时用 `refresh_stock_decision`，核对返回的交易日、警告与确认日期。可用 `evaluate_stock_decision` 在固定快照上复核历史条件，按用户请求用 `save_stock_factors` 保存同一证券和项目的因子选择。请说明因子为什么适用于该标的，并避免把同一快照内的事件研究写成可成交回测。

MCP 只连接本机工作台。公开行情补数会访问上游，后端仍按项目规则记录真实观测日期、来源和失败。回测不会触发实盘交易。逐日纸面账户仍由用户手动推进，外部笔记库写入仍需要用户明确请求。关闭 MCP 时，只需在项目的 `.codex/config.toml` 内停用 `mcp_servers.quantsandbox`，再重启 Codex。文件使用本机路径，不提交 Git。
