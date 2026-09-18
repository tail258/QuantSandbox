<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { workspace, chooseRun, runMetrics, refreshRuns } from '../workspace/store'
import { dateLabel, percent, signClass, statusLabel } from '../utils/format'
import Icon from '../components/Icon.vue'
import EmptyState from '../components/EmptyState.vue'
import type { StrategySpec } from '../types'
const router = useRouter()
function compose(strategy: StrategySpec) {
  if (!workspace.catalog) return
  workspace.catalog.defaults.strategy = {
    name: strategy.name,
    parameters: Object.fromEntries(strategy.parameters.map((p) => [p.key, p.default])),
  }
  workspace.createOpen = true
}
const completed = computed(() => workspace.runs.filter((run) => run.status === 'completed'))
const running = computed(() =>
  workspace.runs.filter((run) => ['queued', 'running'].includes(run.status)),
)
const branches = computed(() => workspace.runs.filter((run) => run.kind === 'branch'))
async function open(id: string, kind: string) {
  if (['backtest', 'branch'].includes(kind)) {
    await chooseRun(id)
    await router.push('/terminal')
  } else await router.push({ path: '/lab', query: { run: id } })
}
</script>
<template>
  <div class="page">
    <header class="page-heading">
      <h1>研究总览</h1>
      <div class="page-actions">
        <button
          class="button secondary"
          @click="refreshRuns().catch((error) => (workspace.error = error.message))"
        >
          <Icon name="refresh" :size="16" />刷新</button
        ><button
          class="button primary"
          :disabled="!workspace.catalog"
          @click="workspace.createOpen = true"
        >
          <Icon name="plus" :size="16" />新建回测
        </button>
      </div>
    </header>
    <div class="metric-strip overview-metrics">
      <div class="metric">
        <span>已完成研究</span><strong>{{ completed.length }}<small>项</small></strong>
      </div>
      <div class="metric">
        <span>运行中</span><strong>{{ running.length }}<small>项</small></strong>
      </div>
      <div class="metric">
        <span>历史分支</span><strong>{{ branches.length }}<small>条</small></strong>
      </div>
      <div class="metric">
        <span>策略库</span
        ><strong>{{ workspace.catalog?.strategies.length || 0 }}<small>种</small></strong>
      </div>
    </div>
    <section class="panel">
      <header class="panel-heading">
        <h2>最近研究</h2>
        <span class="muted small">{{ workspace.runs.length }} 项</span>
      </header>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>研究名称</th>
              <th>数据</th>
              <th>状态</th>
              <th class="numeric">累计收益</th>
              <th class="numeric">最大回撤</th>
              <th>创建日期</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in workspace.runs.slice(0, 12)" :key="run.id">
              <td>
                <button class="table-link" @click="open(run.id, run.kind)">{{ run.name }}</button>
              </td>
              <td>
                <span class="source-tag">{{ run.synthetic ? '合成数据' : '行情数据' }}</span>
              </td>
              <td>
                <span class="status" :class="run.status">{{ statusLabel(run.status) }}</span>
              </td>
              <td class="numeric" :class="signClass(runMetrics(run).total_return)">
                {{ percent(runMetrics(run).total_return) }}
              </td>
              <td class="numeric negative">{{ percent(runMetrics(run).max_drawdown) }}</td>
              <td class="muted">{{ dateLabel(run.created_at) }}</td>
              <td>
                <button
                  class="icon-button borderless"
                  aria-label="打开研究"
                  @click="open(run.id, run.kind)"
                >
                  <Icon name="arrow" :size="16" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-if="!workspace.runs.length" title="还没有研究记录" />
    </section>
    <section class="strategy-library">
      <header class="section-heading"><h2>策略库</h2></header>
      <div class="strategy-list">
        <button
          v-for="(strategy, index) in workspace.catalog?.strategies"
          :key="strategy.name"
          class="strategy-item"
          @click="compose(strategy)"
        >
          <span class="strategy-number">0{{ index + 1 }}</span
          ><strong>{{ strategy.label }}</strong
          ><span class="strategy-params">{{
            strategy.parameters.map((p) => `${p.label} ${p.default}`).join(' / ')
          }}</span
          ><Icon name="arrow" :size="18" />
        </button>
      </div>
    </section>
  </div>
</template>
