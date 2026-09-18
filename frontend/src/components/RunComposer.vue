<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { RunConfig } from '../types'
import { workspace, submitRun } from '../workspace/store'
import { post } from '../api/http'
import ModalFrame from './ModalFrame.vue'
import Icon from './Icon.vue'
const emit = defineEmits<{ close: [] }>()
const router = useRouter()
const draft = reactive<RunConfig>(JSON.parse(JSON.stringify(workspace.catalog!.defaults)))
draft.name = '新的策略研究'
const selectedStrategy = computed(() =>
  workspace.catalog?.strategies.find((strategy) => strategy.name === draft.strategy.name),
)
const error = ref(''),
  prompt = ref(''),
  parsing = ref(false),
  plan = ref<any>(null)
const saving = ref(false)
const selectedSource = computed(() =>
  workspace.catalog?.sources.find((source) => source.id === draft.source),
)
function updateStrategy() {
  draft.strategy.parameters = Object.fromEntries(
    selectedStrategy.value!.parameters.map((parameter) => [parameter.key, parameter.default]),
  )
}
async function parsePrompt() {
  parsing.value = true
  error.value = ''
  try {
    plan.value = await post('/assistant/plan', { prompt: prompt.value, base_config: draft })
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    parsing.value = false
  }
}
function applyPlan() {
  if (plan.value?.config) {
    Object.assign(draft, plan.value.config)
    plan.value = null
    prompt.value = ''
  }
}
async function save() {
  error.value = ''
  if (!draft.tickers.length) {
    error.value = '至少选择一个标的。'
    return
  }
  if (draft.start_date >= draft.end_date) {
    error.value = '结束日期必须晚于开始日期。'
    return
  }
  const p = draft.strategy.parameters
  if (draft.strategy.name === 'dual_ma' && p.fast_period! >= p.slow_period!) {
    error.value = '快线周期必须小于慢线周期。'
    return
  }
  saving.value = true
  try {
    const result = submitRun(JSON.parse(JSON.stringify(draft)))
    emit('close')
    await router.push('/terminal')
    await result
  } catch (err) {
    workspace.error = (err as Error).message
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <ModalFrame title="新建回测" wide @close="emit('close')"
    ><form class="composer form-body" @submit.prevent="save">
      <label class="field"
        >研究名称<input v-model="draft.name" required maxlength="100" autofocus
      /></label>
      <div class="form-grid">
        <label class="field"
          >策略<select v-model="draft.strategy.name" @change="updateStrategy">
            <option
              v-for="strategy in workspace.catalog?.strategies"
              :key="strategy.name"
              :value="strategy.name"
            >
              {{ strategy.label }}
            </option>
          </select></label
        ><label class="field"
          >数据来源<select v-model="draft.source">
            <option
              v-for="source in workspace.catalog?.sources"
              :key="source.id"
              :value="source.id"
              :disabled="!source.available"
            >
              {{ source.name }}
            </option>
          </select></label
        >
      </div>
      <p v-if="selectedSource?.synthetic" class="source-notice">
        <Icon name="info" :size="15" />合成数据，用于验证研究流程
      </p>
      <p v-else-if="selectedSource?.notice" class="source-notice">{{ selectedSource.notice }}</p>
      <fieldset class="ticker-fieldset">
        <legend>研究标的</legend>
        <div class="ticker-options">
          <label
            v-for="ticker in workspace.catalog?.tickers"
            :key="ticker.ticker"
            :class="{ checked: draft.tickers.includes(ticker.ticker) }"
            ><input v-model="draft.tickers" type="checkbox" :value="ticker.ticker" /><span
              >{{ ticker.name }}<small>{{ ticker.ticker }}</small></span
            ></label
          >
        </div>
      </fieldset>
      <div class="form-grid">
        <label class="field"
          >开始日期<input v-model="draft.start_date" type="date" required /></label
        ><label class="field"
          >结束日期<input v-model="draft.end_date" type="date" required
        /></label>
      </div>
      <div class="form-grid">
        <label v-for="parameter in selectedStrategy?.parameters" :key="parameter.key" class="field"
          >{{ parameter.label
          }}<input
            v-model.number="draft.strategy.parameters[parameter.key]"
            type="number"
            :min="parameter.min"
            :max="parameter.max"
            :step="parameter.step || 1"
            required
        /></label>
      </div>
      <div class="form-grid">
        <label class="field"
          >初始资金（元）<input
            v-model.number="draft.account.initial_cash"
            type="number"
            min="1000"
            step="1000"
            required /></label
        ><label class="field"
          >单标的仓位（0–1）<input
            v-model.number="draft.account.position_size"
            type="number"
            min="0.01"
            max="1"
            step="0.01"
            required
        /></label>
      </div>
      <details class="form-details">
        <summary>交易成本</summary>
        <div class="form-grid">
          <label class="field"
            >佣金率<input
              v-model.number="draft.account.commission_rate"
              type="number"
              min="0"
              max="0.1"
              step="0.0001"
              required /></label
          ><label class="field"
            >最低佣金（元）<input
              v-model.number="draft.account.min_commission"
              type="number"
              min="0"
              step="1"
              required /></label
          ><label class="field"
            >卖出税率<input
              v-model.number="draft.account.tax_rate"
              type="number"
              min="0"
              max="0.1"
              step="0.0001"
              required /></label
          ><label class="field"
            >滑点（基点）<input
              v-model.number="draft.account.slippage_bps"
              type="number"
              min="0"
              max="1000"
              step="1"
              required
          /></label>
        </div>
      </details>
      <details class="form-details">
        <summary>研究指令 <span class="muted small">本地规则解析</span></summary>
        <label class="field"
          ><span class="sr-only">研究指令</span
          ><textarea
            v-model="prompt"
            rows="2"
            placeholder="例如：本金 20 万，快线 5 天，慢线 20 天，仓位 50%"
            maxlength="2000"
          /></label
        ><button
          type="button"
          class="button secondary small-button"
          :disabled="!prompt.trim() || parsing"
          @click="parsePrompt"
        >
          {{ parsing ? '解析中…' : '解析指令' }}
        </button>
        <div v-if="plan" class="plan-preview">
          <p>{{ plan.explanation }}</p>
          <ul v-if="plan.changes?.length">
            <li v-for="change in plan.changes" :key="String(change)">
              {{ typeof change === 'string' ? change : JSON.stringify(change) }}
            </li>
          </ul>
          <p v-for="warning in plan.warnings || []" :key="warning" class="warning">{{ warning }}</p>
          <button type="button" class="button secondary small-button" @click="applyPlan">
            应用配置
          </button>
        </div>
      </details>
      <div v-if="error" class="inline-error" role="alert">{{ error }}</div>
      <footer class="modal-footer">
        <button class="button secondary" type="button" @click="emit('close')">取消</button
        ><button class="button primary" :disabled="saving || workspace.busy" type="submit">
          <Icon name="play" :size="15" />{{ saving ? '正在提交…' : '运行回测' }}
        </button>
      </footer>
    </form></ModalFrame
  >
</template>
