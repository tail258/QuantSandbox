<script setup lang="ts">
import { money, percent, number, signClass } from '../utils/format'
import type { Metrics } from '../types'
defineProps<{ metrics: Metrics; equity?: number }>()
</script>
<template>
  <div class="metric-strip">
    <div class="metric">
      <span>当前权益</span><strong>{{ money(equity ?? metrics.final_equity) }}</strong>
    </div>
    <div class="metric">
      <span>累计收益</span
      ><strong :class="signClass(metrics.total_return)">{{ percent(metrics.total_return) }}</strong>
    </div>
    <div class="metric">
      <span>最大回撤</span><strong class="negative">{{ percent(metrics.max_drawdown) }}</strong>
    </div>
    <div class="metric">
      <span>完成交易</span
      ><strong>{{ number(metrics.closed_trade_count, 0) }}<small>轮</small></strong>
    </div>
  </div>
</template>
