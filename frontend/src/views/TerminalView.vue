<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import MarketChart from '../components/MarketChart.vue'
import MetricStrip from '../components/MetricStrip.vue'
import PlaybackControls from '../components/PlaybackControls.vue'
import TradeLedger from '../components/TradeLedger.vue'
import DecisionInspector from '../components/DecisionInspector.vue'
import ModalFrame from '../components/ModalFrame.vue'
import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import {
  workspace,
  currentResult,
  tickerName,
  runMetrics,
  chooseRun,
  exportRun,
  createBranch,
  startSession,
  revealSession,
} from '../workspace/store'
import { money, percent, signClass } from '../utils/format'
import type { Metrics, Trade, Run } from '../types'
const ticker = ref(''),
  tab = ref('chart'),
  selectedTrade = ref<Trade | null>(null),
  branchOpen = ref(false),
  branchName = ref('仓位调整'),
  branchDate = ref(''),
  branchPosition = ref(0.5),
  branchError = ref(''),
  revealOpen = ref(false),
  sessionBusy = ref(false)
const chartPanel = ref<HTMLElement>()
const result = currentResult
const currentDate = computed(
  () => workspace.session?.date || result.value?.series?.[workspace.cursor]?.date,
)
const visibleSeries = computed(() =>
  workspace.session
    ? result.value?.series || []
    : result.value?.series?.slice(0, workspace.cursor + 1) || [],
)
const visibleBars = computed(() =>
  (result.value?.bars?.[ticker.value] || []).filter(
    (bar) => !currentDate.value || bar.date <= currentDate.value,
  ),
)
const visibleTrades = computed(() =>
  (result.value?.trades || []).filter(
    (trade) => !currentDate.value || trade.date <= currentDate.value,
  ),
)
const chartTrades = computed(() =>
  visibleTrades.value.filter((trade) => trade.ticker === ticker.value),
)
const lastDecision = computed(() =>
  [...(result.value?.decisions || [])]
    .reverse()
    .find(
      (decision) =>
        decision.ticker === ticker.value &&
        (!currentDate.value || decision.date <= currentDate.value),
    ),
)
const initial = computed(() => workspace.active?.config.account.initial_cash || 1)
const metrics = computed<Metrics>(() => {
  if (workspace.session) return result.value?.metrics || {}
  let peak = initial.value,
    drawdown = 0
  visibleSeries.value.forEach((point) => {
    peak = Math.max(peak, point.equity)
    drawdown = Math.min(drawdown, (point.equity / peak - 1) * 100)
  })
  return {
    total_return: ((visibleSeries.value.at(-1)?.equity || initial.value) / initial.value - 1) * 100,
    max_drawdown: drawdown,
    closed_trade_count: visibleTrades.value.filter((trade) => trade.round_trip_closed).length,
  }
})
const related = computed(() => {
  const run = workspace.active
  if (!run) return []
  const root = run.parent_id || run.id
  return workspace.runs
    .filter((item) => item.id === root || item.parent_id === root)
    .filter((item) => item.status === 'completed' && ['backtest', 'branch'].includes(item.kind))
    .slice(0, 4)
    .reverse()
})
function forkPosition(run: Run) {
  const start = Date.parse(run.config.start_date)
  const end = Date.parse(run.config.end_date)
  const fork = Date.parse(run.branch?.fork_date || run.config.start_date)
  return `${Math.max(0, Math.min(100, ((fork - start) / Math.max(1, end - start)) * 100))}%`
}
watch(
  () => workspace.active?.id,
  () => {
    ticker.value = workspace.active?.config.tickers[0] || ''
    selectedTrade.value = null
    tab.value = 'chart'
  },
  { immediate: true },
)
watch([currentDate, ticker], () => {
  selectedTrade.value = chartTrades.value.at(-1) || null
})
watch(
  () => visibleTrades.value.length,
  () => {
    if (!selectedTrade.value) selectedTrade.value = chartTrades.value.at(-1) || null
  },
  { immediate: true },
)
watch(branchOpen, (value) => {
  if (value) branchDate.value = currentDate.value || ''
})
async function selectTrade(trade: Trade) {
  ticker.value = trade.ticker
  await nextTick()
  selectedTrade.value = trade
}
function selectDate(date: string) {
  selectedTrade.value = [...chartTrades.value].reverse().find((trade) => trade.date <= date) || null
}
async function branch() {
  if (!currentDate.value) return
  branchError.value = ''
  try {
    await createBranch(branchName.value, branchDate.value, branchPosition.value)
    branchOpen.value = false
  } catch (error) {
    branchError.value = (error as Error).message
  }
}
async function blind() {
  sessionBusy.value = true
  try {
    await startSession()
    selectedTrade.value = null
  } catch (error) {
    workspace.error = (error as Error).message
  } finally {
    sessionBusy.value = false
  }
}
async function reveal() {
  sessionBusy.value = true
  try {
    await revealSession()
    revealOpen.value = false
  } catch (error) {
    workspace.error = (error as Error).message
  } finally {
    sessionBusy.value = false
  }
}
</script>
<template>
  <div class="page terminal-page">
    <header class="page-heading">
      <div class="heading-name">
        <select
          v-if="workspace.active"
          class="run-title-select"
          :value="workspace.active.id"
          aria-label="选择研究"
          @change="chooseRun(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="run in workspace.runs.filter((item) =>
              ['backtest', 'branch'].includes(item.kind),
            )"
            :key="run.id"
            :value="run.id"
          >
            {{ run.name }}
          </option>
        </select>
        <h1 v-else>推演终端</h1>
      </div>
      <div class="page-actions">
        <span
          v-if="result?.replay_verification && !workspace.session"
          class="verification-status"
          :class="{ warning: !result.replay_verification.matched }"
          :title="String(result.replay_verification.different_fields || '')"
          ><Icon :name="result.replay_verification.matched ? 'check' : 'alert'" :size="14" />{{
            result.replay_verification.matched ? '重放一致' : '重放有差异'
          }}</span
        >
        <button
          class="button primary"
          :disabled="!workspace.catalog || workspace.busy"
          @click="workspace.createOpen = true"
        >
          <Icon name="plus" :size="16" />新建回测</button
        ><button
          class="button secondary"
          :disabled="
            workspace.active?.status !== 'completed' ||
            (!!workspace.session && !workspace.session.revealed)
          "
          @click="exportRun()"
        >
          <Icon name="download" :size="16" />导出研究
        </button>
      </div>
    </header>
    <template
      v-if="result?.series?.length && ['backtest', 'branch'].includes(workspace.active?.kind || '')"
    >
      <MetricStrip :metrics="metrics" :equity="visibleSeries.at(-1)?.equity" />
      <div v-if="workspace.session" class="session-banner">
        <Icon :name="workspace.session.revealed ? 'eye' : 'lock'" :size="16" /><span>{{
          workspace.session.revealed ? '已揭晓 · 记录已保存' : '盲测 · 未来行情已隐藏'
        }}</span
        ><button
          v-if="!workspace.session.revealed"
          class="text-button"
          :disabled="sessionBusy"
          @click="revealOpen = true"
        >
          揭晓结果</button
        ><button v-else class="text-button" @click="workspace.session = null">返回研究</button>
      </div>
      <div class="terminal-grid">
        <div class="terminal-main">
          <section ref="chartPanel" class="panel chart-panel">
            <div class="chart-toolbar">
              <label class="instrument-select"
                ><span class="sr-only">行情标的</span
                ><select v-model="ticker">
                  <option
                    v-for="code in workspace.active?.config.tickers"
                    :key="code"
                    :value="code"
                  >
                    {{ tickerName(code) }} {{ code }}
                  </option>
                </select></label
              >
              <div class="segmented">
                <button :class="{ active: tab === 'chart' }" @click="tab = 'chart'">
                  行情与净值</button
                ><button :class="{ active: tab === 'trades' }" @click="tab = 'trades'">
                  交易记录
                </button>
              </div>
              <div class="chart-utilities">
                <span class="timeframe">日线</span
                ><button
                  v-if="!workspace.session"
                  class="icon-button borderless"
                  title="开始盲测"
                  aria-label="开始盲测"
                  :disabled="sessionBusy"
                  @click="blind"
                >
                  <Icon name="lock" :size="16" /></button
                ><button
                  class="icon-button borderless"
                  aria-label="全屏图表"
                  @click="chartPanel?.requestFullscreen?.()"
                >
                  <Icon name="expand" :size="16" />
                </button>
              </div>
            </div>
            <MarketChart
              v-if="tab === 'chart'"
              :key="workspace.session?.id || workspace.active?.id"
              :bars="visibleBars"
              :series="visibleSeries"
              :trades="chartTrades"
              :initial-cash="initial"
              :fast-period="workspace.active?.config.strategy.parameters.fast_period || 5"
              :slow-period="
                workspace.active?.config.strategy.parameters.slow_period ||
                workspace.active?.config.strategy.parameters.window ||
                20
              "
              :selected-date="selectedTrade?.date"
              @select="selectDate"
            />
            <div v-else class="chart-table">
              <TradeLedger
                :trades="visibleTrades"
                :selected="selectedTrade"
                @select="selectTrade"
              />
            </div>
            <PlaybackControls
              :total="result.series.length"
              :date="currentDate"
              @branch="branchOpen = true"
            />
          </section>
          <section v-if="!workspace.session" class="panel branch-panel">
            <header>
              <h2>分支对比</h2>
              <Icon name="branch" :size="15" />
            </header>
            <div class="branch-rows">
              <button
                v-for="(run, index) in related"
                :key="run.id"
                class="branch-row"
                :class="{ active: run.id === workspace.active?.id, violet: index % 2 === 1 }"
                @click="chooseRun(run.id)"
              >
                <span class="branch-label"><i />{{ run.parent_id ? run.name : '原始路径' }}</span
                ><span class="branch-line"
                  ><i
                    v-if="run.branch?.fork_date"
                    :title="`分叉于 ${run.branch.fork_date}`"
                    :style="{ left: forkPosition(run) }" /></span
                ><span class="branch-equity"
                  ><span class="muted">期末 </span>{{ money(runMetrics(run).final_equity) }}</span
                ><span class="branch-return" :class="signClass(runMetrics(run).total_return)">{{
                  percent(runMetrics(run).total_return)
                }}</span></button
              ><button
                v-if="related.length < 2"
                class="text-button branch-add"
                @click="branchOpen = true"
              >
                <Icon name="plus" :size="14" />创建对照分支
              </button>
            </div>
          </section>
        </div>
        <DecisionInspector :trade="selectedTrade || chartTrades.at(-1)" :decision="lastDecision" />
      </div>
      <TradeLedger
        v-if="tab !== 'trades'"
        :trades="visibleTrades"
        :selected="selectedTrade"
        compact
        @select="selectTrade"
      />
      <details v-if="result.assumptions?.length" class="assumptions">
        <summary>撮合假设与研究口径</summary>
        <ul>
          <li v-for="assumption in result.assumptions" :key="assumption">{{ assumption }}</li>
        </ul>
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer"
          >Charts by TradingView</a
        >
      </details>
    </template>
    <div
      v-else-if="workspace.active && ['queued', 'running'].includes(workspace.active.status)"
      class="task-progress panel"
    >
      <div class="spinner" />
      <h2>{{ workspace.active.status === 'queued' ? '等待执行' : '正在计算回测' }}</h2>
      <progress :value="workspace.active.progress" max="100" /><span
        >{{ workspace.active.progress }}%</span
      >
    </div>
    <EmptyState
      v-else-if="!workspace.loading"
      title="开始一项研究"
      :text="workspace.active?.error?.message"
      ><button
        class="button primary"
        :disabled="!workspace.catalog"
        @click="workspace.createOpen = true"
      >
        新建回测
      </button></EmptyState
    >
  </div>
  <ModalFrame v-if="branchOpen" title="创建历史分支" @close="branchOpen = false"
    ><form class="form-body" @submit.prevent="branch">
      <label class="field">分支名称<input v-model="branchName" required maxlength="100" /></label
      ><label class="field"
        >分叉日期<input
          v-model="branchDate"
          type="date"
          :min="workspace.active?.branch?.fork_date || workspace.active?.config.start_date"
          :max="workspace.active?.config.end_date"
          required /></label
      ><label class="field"
        >单标的目标仓位<span class="range-value">{{ Math.round(branchPosition * 100) }}%</span
        ><input v-model.number="branchPosition" type="range" min="0.05" max="1" step="0.05"
      /></label>
      <div v-if="branchError" class="inline-error">{{ branchError }}</div>
      <footer class="modal-footer">
        <button type="button" class="button secondary" @click="branchOpen = false">取消</button
        ><button class="button primary" :disabled="workspace.busy">
          <Icon name="branch" :size="16" />{{ workspace.busy ? '创建中…' : '创建分支' }}
        </button>
      </footer>
    </form></ModalFrame
  >
  <ModalFrame v-if="revealOpen" title="揭晓完整结果" @close="revealOpen = false"
    ><div class="form-body">
      <p>这将显示未来行情和最终绩效，并永久记录本次揭晓。</p>
      <footer class="modal-footer">
        <button class="button secondary" @click="revealOpen = false">继续盲测</button
        ><button class="button primary" :disabled="sessionBusy" @click="reveal">揭晓结果</button>
      </footer>
    </div></ModalFrame
  >
</template>
