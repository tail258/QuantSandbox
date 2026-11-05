"""Portable bilingual US research exports from archived inputs only."""
import csv
import io
import zipfile
from . import store


def report(result, chinese=False):
    instrument = result['instrument']
    lines = [f"# {instrument['name']} ({instrument['symbol']})", '',
        '年度财务；美元；当前修订口径，不代表历史当时可得数据。' if chinese else
        'Annual financials; USD; current revised filings, not point-in-time history.', '',
        '自由现金流 = 经营现金流 − 资本开支，仅在期间与申报编号一致时计算。' if chinese else
        'Free cash flow = operating cash flow − capital expenditure, only for matching periods and filings.', '',
        '## 财务与来源' if chinese else '## Financials and sources', '']
    for row in result['financials']:
        lines.extend(['### ' + row['period_end'], ''])
        for metric, fact in row['metrics'].items():
            lines.append(f"- {metric}: " + (f"{fact['value']} {fact['unit']}; {fact.get('period_start') or 'instant'} → {fact['period_end']}; filed {fact['filed']}; {fact['accession']}; {fact['source_url']}" if fact else ('缺失' if chinese else 'missing')))
        lines.extend([f"- free_cashflow: {row.get('free_cashflow') if row.get('free_cashflow') is not None else '—'} USD", ''])
    lines.extend(['## 披露' if chinese else '## Filings', ''])
    for filing in result['filings']:
        lines.append(f"- {filing['form']} · {filing.get('filed', '')} · {filing.get('report_date', '')} · {filing.get('source_url', '')}")
    prices = result.get('prices')
    if prices:
        lines.extend(['', '## 日线' if chinese else '## Daily prices', '', f"USD · unadjusted · volume in shares · {prices.get('source_url', '')}", f"Snapshot: {prices['id']}; fetched: {prices['fetched_at']}"])
    lines.extend(['', '## 快照' if chinese else '## Snapshots', '', *result.get('snapshot_ids', [])])
    return '\n'.join(lines) + '\n'


def export_run(run):
    dest = store.ROOT / 'exports' / (run['id'] + '.zip')
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = run['result']
    data = io.StringIO(newline='')
    writer = csv.DictWriter(data, fieldnames=['period_end', 'metric', 'value', 'unit', 'period_start', 'filed', 'accession', 'source_url'])
    writer.writeheader()
    for row in result['financials']:
        for metric, fact in row['metrics'].items():
            if fact:
                writer.writerow({'metric': metric, **{k: fact.get(k) for k in writer.fieldnames if k != 'metric'}})
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('report.md', report(result))
        archive.writestr('report.zh-CN.md', report(result, True))
        archive.writestr('recipe.json', store.encode(run))
        archive.writestr('snapshots.json', store.encode(store.get_snapshots(run['inputs'])))
        archive.writestr('data.csv', '\ufeff' + data.getvalue())
        if result.get('prices'):
            output = io.StringIO(newline='')
            price_writer = csv.DictWriter(output, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
            price_writer.writeheader()
            price_writer.writerows(result['prices']['rows'])
            archive.writestr('prices.csv', output.getvalue())
    return dest
