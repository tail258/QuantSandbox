<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request } from '../api/http'
import { tickerName } from '../workspace/store'
import type { Dataset, DataSource } from '../types'
import { dateLabel, number } from '../utils/format'
import Icon from '../components/Icon.vue'
import EmptyState from '../components/EmptyState.vue'
const datasets = ref<Dataset[]>([]),
  sources = ref<DataSource[]>([]),
  loading = ref(true),
  error = ref(''),
  expanded = ref(''),
  search = ref('')
const filtered = computed(() =>
  datasets.value.filter((dataset) =>
    `${dataset.ticker} ${tickerName(dataset.ticker)}`.includes(search.value),
  ),
)
async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await request<{ datasets: Dataset[]; sources: DataSource[] }>('/data/status')
    datasets.value = response.datasets
    sources.value = response.sources
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<template>
  <div class="page">
    <header class="page-heading">
      <h1>数据中心</h1>
      <button class="button secondary" :disabled="loading" @click="load">
        <Icon name="refresh" :size="16" />刷新
      </button>
    </header>
    <div class="data-source-strip">
      <div v-for="source in sources" :key="source.id" class="source-entry">
        <Icon :name="source.synthetic ? 'database' : 'globe'" :size="22" />
        <div>
          <strong>{{ source.name }}</strong
          ><span :class="source.available ? 'available' : 'muted'"
            >{{ source.available ? (source.synthetic ? '可用' : '已安装') : '未安装'
            }}{{ source.synthetic ? ' · 合成数据' : '' }}</span
          >
        </div>
      </div>
    </div>
    <section class="panel">
      <header class="panel-heading">
        <h2>
          数据快照 <span class="count">{{ datasets.length }}</span>
        </h2>
        <label class="search-input"
          ><Icon name="search" :size="16" /><input
            v-model="search"
            aria-label="搜索数据标的"
            placeholder="搜索标的"
        /></label>
      </header>
      <p v-if="error" class="inline-error">{{ error }}</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>来源</th>
              <th>覆盖区间</th>
              <th class="numeric">行情条数</th>
              <th>版本</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <template v-for="dataset in filtered" :key="dataset.sha256"
              ><tr>
                <td>
                  {{ tickerName(dataset.ticker) }}
                  <span class="muted ticker-code">{{ dataset.ticker }}</span>
                </td>
                <td>
                  <span class="source-tag">{{
                    dataset.synthetic ? '合成数据' : dataset.source
                  }}</span>
                </td>
                <td class="mono">
                  {{ dateLabel(dataset.start_date) }} — {{ dateLabel(dataset.end_date) }}
                </td>
                <td class="numeric">{{ number(dataset.rows, 0) }}</td>
                <td class="mono muted">{{ String(dataset.version).slice(0, 12) }}</td>
                <td>
                  <button
                    class="icon-button borderless"
                    :aria-expanded="expanded === dataset.sha256"
                    aria-label="查看快照详情"
                    @click="expanded = expanded === dataset.sha256 ? '' : dataset.sha256"
                  >
                    <Icon name="chevron" :size="16" />
                  </button>
                </td>
              </tr>
              <tr v-if="expanded === dataset.sha256">
                <td colspan="6" class="snapshot-detail">
                  <dl>
                    <dt>内容 SHA256</dt>
                    <dd class="hash">{{ dataset.sha256 }}</dd>
                    <dt>价格口径</dt>
                    <dd>{{ dataset.price_basis }}</dd>
                    <dt>成交量单位</dt>
                    <dd>{{ dataset.volume_unit }}</dd>
                    <dt>创建时间</dt>
                    <dd>{{ dataset.created_at }}</dd>
                    <template v-if="dataset.notice"
                      ><dt>数据说明</dt>
                      <dd>{{ dataset.notice }}</dd></template
                    >
                  </dl>
                </td>
              </tr></template
            >
          </tbody>
        </table>
      </div>
      <EmptyState
        v-if="!loading && !filtered.length"
        :title="search ? '没有匹配的数据' : '暂无数据快照'"
      />
      <div v-if="loading" class="loading-line">加载数据…</div>
    </section>
    <details class="assumptions">
      <summary>数据口径</summary>
      <p v-for="source in sources" :key="source.id">{{ source.name }}：{{ source.notice }}</p>
    </details>
  </div>
</template>
