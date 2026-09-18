# QuantSandbox workbench design system

Production reference: `../docs/design/terminal-concept.png`, viewed before implementation.

The primary screen is a research terminal: 200 px left rail, slim breadcrumb bar,
open heading/action band, four inline metrics, 70/30 chart/decision inspector,
playback inside the chart container, branch comparison strip, and a trading ledger.
Other requested research workspaces extend these same components and density.

Color lock: graphite `#101217`, rail `#14171d`, panel `#191d25`, border `#2a303b`,
primary text `#e8ebf2`, secondary `#8893a7`, periwinkle `#8ea9ff`, price rise
`#ec7682`, price decline `#60c4a4`. No decorative gradients or imagery.

Typography: system sans with Chinese system fonts, 28 px primary heading,
24 px inline numeric metrics, 14 px UI, 12 px annotation. Numeric content uses
tabular lining figures. Outline icons: consistent 1.7 px strokes, 18 px UI size.
Geometry: 6 px panel radius, 5 px controls, 1 px borders, 20–28 px page gutters.
Motion is limited to disclosure/hover/playback and respects reduced motion.

Code-native component families: workspace shell, navigation rows, inline metrics,
chart toolbar, candlestick/net-value charts, transport, branch timeline, decision
timeline, ledger, form drawer, confirmation dialog, errors/empty states.

Allowed primary-screen copy: QuantSandbox; 研究总览 / 推演终端 / 实验室 / 数据中心 /
研究档案; 研究空间; 合成数据;
新建回测; 导出研究; 当前权益; 累计收益; 最大回撤; 完成交易; 行情与净值;
交易记录; 决策显微镜; 推进 1 日; 推进 20 日; 从此刻分叉; 分支对比.

Intentional functional deviations: prices, dates, branch count and statistics use
real API computations rather than concept sample values; actual run names are
shown; source is explicitly marked synthetic; run selector and secure session
controls are added for required persisted-run/partial-history behavior. Responsive
layouts collapse the rail and stack the inspector; accessible text labels and
working form states extend the reference as required by functioning workflows.

The user's subsequent explicit copy reduction supersedes the original screenshot:
the slogan is removed, the primary title is the selected run name, strategy/date
subtitle is removed, and visible explanatory prose is kept in disclosures. Source
labels, functional section names, field names, and errors remain.

All graph marks are data-driven. The concept image is never rendered as UI.
