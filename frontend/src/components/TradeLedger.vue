<script setup lang="ts">
import type { Trade } from '../types'
import { dateLabel, money, number } from '../utils/format'
import { tickerName } from '../workspace/store'
defineProps<{ trades: Trade[]; selected?: Trade | null; compact?: boolean }>()
const emit = defineEmits<{ select: [trade: Trade] }>()
</script>
<template>
  <section class="panel ledger-panel">
    <header class="panel-heading">
      <h2>
        交易记录 <span class="count">{{ trades.length }}</span>
      </h2>
      <span class="muted small">人民币 · 股</span>
    </header>
    <div class="table-scroll" :class="{ 'compact-ledger': compact }">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>标的</th>
            <th>动作</th>
            <th class="numeric">成交价</th>
            <th class="numeric">数量</th>
            <th class="numeric">费用</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(trade, index) in [...trades].reverse()"
            :key="`${trade.date}-${trade.ticker}-${index}`"
            :class="{ selected: selected === trade }"
            tabindex="0"
            @click="emit('select', trade)"
            @keydown.enter="emit('select', trade)"
          >
            <td>{{ dateLabel(trade.date) }}</td>
            <td>
              {{ tickerName(trade.ticker) }}
              <span class="muted ticker-code">{{ trade.ticker }}</span>
            </td>
            <td :class="trade.action === 'buy' ? 'positive' : 'negative'">
              {{ trade.action === 'buy' ? '买入' : '卖出' }}
            </td>
            <td class="numeric">{{ number(trade.price) }}</td>
            <td class="numeric">{{ number(trade.shares, 0) }}</td>
            <td class="numeric">{{ money(trade.fee) }}</td>
          </tr>
          <tr v-if="!trades.length">
            <td colspan="6" class="empty-cell">当前时点暂无成交记录</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
