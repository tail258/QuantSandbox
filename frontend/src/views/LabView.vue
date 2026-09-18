<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request, post } from '../api/http'
import { workspace, pollRun, refreshRuns, exportRun } from '../workspace/store'
import type { Run } from '../types'
import { percent, signClass, dateLabel } from '../utils/format'
import Icon from '../components/Icon.vue'
import EmptyState from '../components/EmptyState.vue'
const route = useRoute()
const kind = ref('pressure'),
  parentId = ref(''),
  parameter = ref('fast_period'),
  values = ref('3, 5, 8, 12'),
  training = ref(120),
  testing = ref(40),
  busy = ref(false),
  error = ref(''),
  experiment = ref<Run | null>(null)
const eligible = computed(() =>
  workspace.runs.filter((run) => run.status === 'completed' && run.kind === 'backtest'),
)
const parent = computed(() => eligible.value.find((run) => run.id === parentId.value))
const parameters = computed(
  () =>
    workspace.catalog?.strategies.find(
      (strategy) => strategy.name === parent.value?.config.strategy.name,
    )?.parameters || [],
)
const variants = computed(
  () => experiment.value?.result?.scenarios || experiment.value?.result?.variants || [],
)
const maxReturn = computed(() =>
  Math.max(1, ...variants.value.map((variant) => Math.abs(variant.metrics.total_return || 0))),
)
const history = computed(() =>
  workspace.runs.filter((run) => ['pressure', 'parameter', 'walk_forward'].includes(run.kind)),
)
watch(
  eligible,
  (list) => {
    if (!parentId.value) parentId.value = list[0]?.id || ''
  },
  { immediate: true },
)
watch(
  parentId,
  () => {
    parameter.value = parameters.value[0]?.key || ''
  },
  { immediate: true },
)
watch(
  [parentId, parameter],
  () => {
    const p = parameters.value.find((item) => item.key === parameter.value)
    if (!p) return
    const current = parent.value?.config.strategy.parameters[p.key] ?? p.default
    const minimum =
      p.key === 'slow_period'
        ? Math.max(p.min, (parent.value?.config.strategy.parameters.fast_period || 0) + 1)
        : p.min
    const maximum =
      p.key === 'fast_period'
        ? Math.min(p.max, (parent.value?.config.strategy.parameters.slow_period || 500) - 1)
        : p.max
    values.value = [
      ...new Set(
        [0.6, 1, 1.4].map((multiplier) =>
          Math.max(
            minimum,
            Math.min(
              maximum,
              Number(
                (Math.round((current * multiplier) / (p.step || 1)) * (p.step || 1)).toFixed(6),
              ),
            ),
          ),
        ),
      ),
    ].join(', ')
  },
  { immediate: true },
)
async function load(id: string) {
  try {
    experiment.value = await request<Run>(`/runs/${id}`)
    kind.value = experiment.value.kind
  } catch (err) {
    error.value = (err as Error).message
  }
}
onMounted(() => {
  if (typeof route.query.run === 'string') void load(route.query.run)
})
async function run() {
  error.value = ''
  busy.value = true
  try {
    const body: Record<string, unknown> = { kind: kind.value }
    if (kind.value === 'parameter') {
      const parsed = values.value
        .split(/[,，\s]+/)
        .filter(Boolean)
        .map(Number)
      if (!parsed.length || parsed.some((value) => !Number.isFinite(value)))
        throw new Error('请输入有效参数，用逗号分隔。')
      body.parameter = parameter.value
      body.values = parsed
    }
    if (kind.value === 'walk_forward') {
      body.training_days = training.value
      body.test_days = testing.value
    }
    const task = await post<Run>(`/runs/${parentId.value}/experiments`, body)
    experiment.value = task
    await refreshRuns()
    experiment.value = await pollRun(task.id)
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="page">
    <header class="page-heading">
      <h1>实验室</h1>
      <button
        class="button secondary"
        :disabled="experiment?.status !== 'completed'"
        @click="exportRun(experiment?.id)"
      >
        <Icon name="download" :size="16" />导出实验
      </button>
    </header>
    <div class="lab-layout">
      <section class="panel lab-config">
        <div class="segmented lab-tabs">
          <button
            v-for="item in [
              { id: 'pressure', label: '压力测试' },
              { id: 'parameter', label: '参数实验' },
              { id: 'walk_forward', label: '样本外验证' },
            ]"
            :key="item.id"
            :class="{ active: kind === item.id }"
            @click="kind = item.id"
          >
            {{ item.label }}
          </button>
        </div>
        <form class="form-body" @submit.prevent="run">
          <label class="field"
            >基线研究<select v-model="parentId" required>
              <option v-for="item in eligible" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
              <option v-if="!eligible.length" value="">请先完成一次基础回测</option>
            </select></label
          ><template v-if="kind === 'parameter'"
            ><label class="field"
              >实验参数<select v-model="parameter">
                <option v-for="p in parameters" :key="p.key" :value="p.key">{{ p.label }}</option>
              </select></label
            ><label class="field"
              >候选值<input v-model="values" required placeholder="3, 5, 8, 12"
            /></label>
            <p class="source-notice">样本内比较</p></template
          >
          <div v-if="kind === 'walk_forward'" class="form-grid">
            <label class="field"
              >训练窗口（交易日）<input
                v-model.number="training"
                type="number"
                min="30"
                max="1000"
                required /></label
            ><label class="field"
              >测试窗口（交易日）<input
                v-model.number="testing"
                type="number"
                min="10"
                max="250"
                required
            /></label>
          </div>
          <div v-if="kind === 'pressure'" class="scenario-list">
            <div><Icon name="settings" :size="16" />费用上升</div>
            <div><Icon name="clock" :size="16" />成交延迟</div>
            <div><Icon name="candle" :size="16" />滑点与仓位</div>
          </div>
          <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
          <button class="button primary full-width" :disabled="busy || !parentId">
            <Icon :name="busy ? 'refresh' : 'play'" :size="16" />{{
              busy ? '实验运行中…' : '运行实验'
            }}
          </button>
        </form>
      </section>
      <section class="panel lab-results">
        <header class="panel-heading">
          <h2>{{ experiment?.name || '实验结果' }}</h2>
          <span v-if="experiment?.synthetic" class="source-tag">合成数据</span>
        </header>
        <div v-if="busy" class="task-progress">
          <div class="spinner" />
          <span>正在计算</span>
        </div>
        <template v-else-if="experiment?.status === 'completed'"
          ><div v-if="variants.length" class="experiment-bars">
            <div v-for="(variant, index) in variants" :key="index" class="experiment-row">
              <div class="experiment-name">
                <strong>{{
                  variant.name || `${experiment.result?.parameter} = ${variant.value}`
                }}</strong
                ><span :class="signClass(variant.metrics.total_return)">{{
                  percent(variant.metrics.total_return)
                }}</span>
              </div>
              <div class="comparison-track">
                <i
                  :class="(variant.metrics.total_return || 0) >= 0 ? 'up' : 'down'"
                  :style="{
                    width: `${Math.max(1, (Math.abs(variant.metrics.total_return || 0) / maxReturn) * 100)}%`,
                  }"
                />
              </div>
              <div class="experiment-detail">
                <span>最大回撤 {{ percent(variant.metrics.max_drawdown) }}</span
                ><span>闭环交易 {{ variant.metrics.closed_trade_count ?? '—' }}</span>
              </div>
            </div>
          </div>
          <template v-if="experiment.result?.folds"
            ><div class="wf-summary">
              <div>
                <span>样本外收益</span
                ><strong :class="signClass(experiment.result.metrics?.total_return)">{{
                  percent(experiment.result.metrics?.total_return)
                }}</strong>
              </div>
              <div>
                <span>最大回撤</span
                ><strong class="negative">{{
                  percent(experiment.result.metrics?.max_drawdown)
                }}</strong>
              </div>
              <div>
                <span>滚动窗口</span><strong>{{ experiment.result.folds.length }}</strong>
              </div>
            </div>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>窗口</th>
                    <th>训练区间</th>
                    <th>测试区间</th>
                    <th>选中参数</th>
                    <th class="numeric">收益</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(fold, index) in experiment.result.folds" :key="index">
                    <td>{{ index + 1 }}</td>
                    <td>{{ fold.train_start }} — {{ fold.train_end }}</td>
                    <td>{{ fold.test_start }} — {{ fold.test_end }}</td>
                    <td>{{ JSON.stringify((fold.selected_strategy as any)?.parameters || {}) }}</td>
                    <td class="numeric">{{ percent((fold.test_metrics as any)?.total_return) }}</td>
                  </tr>
                </tbody>
              </table>
            </div></template
          ></template
        ><EmptyState v-else title="等待实验" icon="flask" />
      </section>
    </div>
    <section v-if="history.length" class="panel lab-history">
      <header class="panel-heading"><h2>实验记录</h2></header>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>实验名称</th>
              <th>创建日期</th>
              <th>状态</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in history" :key="item.id">
              <td>
                <button class="table-link" @click="load(item.id)">{{ item.name }}</button>
              </td>
              <td>{{ dateLabel(item.created_at) }}</td>
              <td>
                {{
                  item.status === 'completed'
                    ? '已完成'
                    : item.status === 'failed'
                      ? '失败'
                      : '运行中'
                }}
              </td>
              <td>
                <button class="icon-button borderless" aria-label="查看实验" @click="load(item.id)">
                  <Icon name="arrow" :size="16" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
