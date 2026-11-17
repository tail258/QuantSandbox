# 逐日模拟

在已有核验日线的单标的研究项目中，从真实收盘快照生成首份 5/20 日双均线计划。账户从现金开始，每次只接受下一个交易日。开盘用冻结的前一日计划和实际观察到的未复权开盘价重放成交，盘后保存回单、账户及下一份计划。

## 推进一个交易日

1. 打开项目概览的「逐日模拟」，确认当前计划、已保存快照和预期交易日。等待该日收盘且行情源发布完整数据。
2. 查公司在巨潮或交易所公开的 A 股派息实施公告。保存分红核查 JSON，沿用前次的已核对历史，补充截至当日实际取得的实施公告。文件需包含 `schema=quantsandbox.cash-dividend-source.v1`、`symbol`、`exchange=SZSE`、`share_class=A`、`currency=CNY`、`reviewed_from`、`reviewed_through`、带时区的实际 `checked_at`、`query_source_url`、`method` 和 `events`。事件需有 `source_url`、`announced_date`、`record_date`、`ex_date`、`pay_date` 和 `cash_per_share`（人民币元、税前）。日期以实施公告为准。获取失败时保留原错误，并先复核缺口。
3. 查当日适用的深市普通主板限幅规则。确认无特别限幅或豁免后使用 `--ordinary-session`。完整日线、当日交易状态和参考前收盘价由 BaoStock 明确请求，日历也一并冻结。脚本只追加当天的行情，保留前次原始观察。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_daily_paper.py --prior-snapshot PREVIOUS_SNAPSHOT_ID --observation YYYY-MM-DD --dividend-review PATH_TO_REVIEW_JSON --ordinary-session --output PATH_TO_NEW_SNAPSHOT_JSON
.\.venv\Scripts\python.exe -X utf8 -m backend.workbench.cli import-execution-history PATH_TO_NEW_SNAPSHOT_JSON
```

4. 启动服务或重新加载项目页，确认导入日期与预期交易日一致，点击「推进逐日模拟」。收盘完成后、下一次开盘前冻结计划。回单包括模拟成交、未成交或顺延原因、期末账户、发起快照和引擎指纹。已入账日期用同一快照重试会返回原回单。

停牌、价格限制、日期或公告核查不明确时先保留上一条计划。历史观察发生修订，或最新引擎的复算与上一条账户记录不符时，先检查差异。逐日账户以实际到达时间记录观察，历史回测可单独研究修订版数据。

使用[本地 API](API_CONTRACT.md#sourced-execution-history-and-daily-paper-account)也可导入及推进。账户和逐日收据保存在本工作区 `data/daily-paper/`。行情获取和推进由用户手动触发。
