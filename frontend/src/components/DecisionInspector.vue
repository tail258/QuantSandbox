<script setup lang="ts">
import { ref } from 'vue'
import type { Decision, Trade } from '../types'
import { dateLabel, money, number } from '../utils/format'
import { tickerName } from '../workspace/store'
import Icon from './Icon.vue'
defineProps<{ trade?: Trade | null; decision?: Decision | null }>()
const expanded = ref(false)
const indicatorLabels: Record<string, string> = {
  fast_ma: '快线',
  slow_ma: '慢线',
  fast: '快线',
  slow: '慢线',
  rsi: 'RSI',
  momentum: '动量',
  upper: '上轨',
  lower: '下轨',
  middle: '中轨',
  close: '收盘价',
}
</script>
<template>
  <aside class="panel inspector">
    <header class="panel-heading">
      <h2>决策显微镜</h2>
      <Icon name="search" :size="16" />
    </header>
    <template v-if="trade"
      ><div class="inspector-intro">
        <h3>
          <span :class="trade.action === 'buy' ? 'positive' : 'negative'">{{
            trade.action === 'buy' ? '买入' : '卖出'
          }}</span
          ><span class="dot-divider">·</span>{{ dateLabel(trade.date) }}
        </h3>
        <span class="muted"
          >{{ tickerName(trade.ticker) }} <span class="mono">{{ trade.ticker }}</span></span
        >
      </div>
      <ol class="evidence-timeline">
        <li>
          <div class="evidence-title">
            <h4>信号触发</h4>
            <time>{{ dateLabel(trade.signal_date) }}</time>
          </div>
          <dl>
            <template v-for="(value, key) in trade.evidence?.indicators || {}" :key="key"
              ><dt>{{ indicatorLabels[key] || key }}</dt>
              <dd>{{ typeof value === 'number' ? number(value) : value }}</dd></template
            >
          </dl>
          <p class="condition">{{ trade.reason }}</p>
        </li>
        <li>
          <div class="evidence-title">
            <h4>成交执行</h4>
            <time>{{ dateLabel(trade.date) }}</time>
          </div>
          <dl>
            <dt>成交价格</dt>
            <dd>{{ money(trade.price) }}</dd>
            <dt>执行时点</dt>
            <dd>后续可成交日开盘</dd>
          </dl>
        </li>
        <li>
          <div class="evidence-title"><h4>资金变化</h4></div>
          <dl>
            <dt>{{ trade.action === 'buy' ? '买入数量' : '卖出数量' }}</dt>
            <dd>{{ number(trade.shares, 0) }} 股</dd>
            <dt>成交金额</dt>
            <dd>{{ money(trade.value ?? trade.price * trade.shares) }}</dd>
            <dt>交易费用</dt>
            <dd>{{ money(trade.fee) }}</dd>
            <template v-if="trade.realized_pnl != null"
              ><dt>已实现盈亏</dt>
              <dd>{{ money(trade.realized_pnl) }}</dd></template
            >
          </dl>
        </li>
      </ol>
      <button class="text-button evidence-toggle" @click="expanded = !expanded">
        {{ expanded ? '收起证据' : '查看完整证据'
        }}<Icon :name="expanded ? 'chevron' : 'arrow'" :size="16" />
      </button>
      <pre v-if="expanded" class="evidence-json">{{ JSON.stringify(trade.evidence, null, 2) }}</pre>
    </template>
    <div v-else-if="decision" class="inspector-intro">
      <h3>
        {{
          decision.action === 'buy'
            ? '买入信号'
            : decision.action === 'sell'
              ? '卖出信号'
              : '观察中'
        }}
      </h3>
      <span class="muted">{{ dateLabel(decision.date) }} · {{ tickerName(decision.ticker) }}</span>
      <p class="condition">{{ decision.reason }}</p>
      <dl>
        <template v-for="(value, key) in decision.evidence?.indicators || {}" :key="key"
          ><dt>{{ indicatorLabels[key] || key }}</dt>
          <dd>{{ typeof value === 'number' ? number(value) : value }}</dd></template
        >
      </dl>
    </div>
    <div v-else class="inspector-empty">
      <Icon name="search" :size="28" />
      <p>选择一笔交易，查看决策证据</p>
    </div>
  </aside>
</template>
