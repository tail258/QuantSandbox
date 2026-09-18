<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { request, post } from '../api/http'
import {
  workspace,
  chooseRun,
  exportRun,
  refreshRuns,
  pollRun,
  notify,
  runMetrics,
} from '../workspace/store'
import { dateLabel, percent, signClass, statusLabel } from '../utils/format'
import type { Note, Run } from '../types'
import Icon from '../components/Icon.vue'
import EmptyState from '../components/EmptyState.vue'
const router = useRouter()
function editNote(note: Note) {
  title.value = note.title
  body.value = note.body
  noteId.value = note.id
}
const search = ref(''),
  selected = ref(workspace.active?.id || ''),
  notes = ref<Note[]>([]),
  title = ref(''),
  body = ref(''),
  error = ref(''),
  busy = ref(false),
  fileInput = ref<HTMLInputElement>(),
  noteId = ref('')
let noteToken = 0
const filtered = computed(() => workspace.runs.filter((run) => run.name.includes(search.value)))
const selectedRun = computed(() => workspace.runs.find((run) => run.id === selected.value))
async function loadNotes() {
  const token = ++noteToken
  title.value = ''
  body.value = ''
  noteId.value = ''
  try {
    const response = await request<{ notes: Note[] }>(
      `/notes?run_id=${encodeURIComponent(selected.value)}`,
    )
    if (token === noteToken) notes.value = response.notes
  } catch (err) {
    error.value = (err as Error).message
  }
}
watch(selected, loadNotes)
onMounted(() => {
  if (selected.value) void loadNotes()
  void refreshRuns().catch((err) => {
    error.value = err.message
  })
})
async function open(run: Run) {
  if (['backtest', 'branch'].includes(run.kind)) {
    await chooseRun(run.id)
    await router.push('/terminal')
  } else await router.push({ path: '/lab', query: { run: run.id } })
}
async function saveNote() {
  busy.value = true
  error.value = ''
  try {
    const payload = { run_id: selected.value, title: title.value, body: body.value }
    if (noteId.value)
      await request(`/notes/${noteId.value}`, { method: 'PUT', body: JSON.stringify(payload) })
    else await post('/notes', payload)
    await loadNotes()
    notify('研究笔记已保存')
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}
async function importEvidence(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    if (file.size > 50 * 1024 * 1024) throw new Error('证据包不能超过 50 MB。')
    const contents = await file.text()
    JSON.parse(contents)
    const run = await request<Run>('/import', { method: 'POST', body: contents })
    await refreshRuns()
    selected.value = run.id
    const replay = await pollRun(run.id)
    notify(
      replay.result?.replay_verification?.matched
        ? '证据包已导入 · 重放一致'
        : '证据包已导入 · 重放有差异',
    )
  } catch (err) {
    error.value =
      err instanceof SyntaxError ? '文件不是有效的 JSON 证据包。' : (err as Error).message
  } finally {
    busy.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}
async function cancel(run: Run) {
  try {
    await post(`/runs/${run.id}/cancel`)
    await refreshRuns()
  } catch (err) {
    error.value = (err as Error).message
  }
}
</script>
<template>
  <div class="page">
    <header class="page-heading">
      <h1>研究档案</h1>
      <button class="button secondary" :disabled="busy" @click="fileInput?.click()">
        <Icon name="download" :size="16" />{{ busy ? '处理中…' : '导入证据包' }}</button
      ><input
        ref="fileInput"
        class="sr-only"
        type="file"
        accept=".json,application/json"
        aria-label="导入研究证据包"
        @change="importEvidence"
      />
    </header>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <div class="archive-layout">
      <section class="panel archive-list">
        <header class="panel-heading">
          <h2>
            研究记录 <span class="count">{{ filtered.length }}</span>
          </h2>
          <label class="search-input"
            ><Icon name="search" :size="16" /><input
              v-model="search"
              placeholder="搜索研究"
              aria-label="搜索研究"
          /></label>
        </header>
        <div class="archive-rows">
          <article
            v-for="run in filtered"
            :key="run.id"
            class="archive-row"
            :class="{ selected: selected === run.id }"
          >
            <button class="archive-select" @click="selected = run.id">
              <div>
                <strong>{{ run.name }}</strong
                ><span class="status" :class="run.status">{{ statusLabel(run.status) }}</span>
              </div>
              <div class="archive-meta">
                <time>{{ dateLabel(run.created_at) }}</time
                ><span>{{ run.synthetic ? '合成数据' : '行情数据' }}</span
                ><span :class="signClass(runMetrics(run).total_return)">{{
                  percent(runMetrics(run).total_return)
                }}</span>
              </div>
            </button>
            <div class="archive-actions">
              <button
                v-if="['queued', 'running'].includes(run.status)"
                class="text-button"
                @click="cancel(run)"
              >
                取消任务</button
              ><button
                v-else
                class="icon-button borderless"
                :disabled="run.status !== 'completed'"
                aria-label="导出研究"
                @click="exportRun(run.id)"
              >
                <Icon name="download" :size="16" /></button
              ><button class="icon-button borderless" aria-label="打开研究" @click="open(run)">
                <Icon name="arrow" :size="16" />
              </button>
            </div>
          </article>
          <EmptyState v-if="!filtered.length" title="没有匹配的研究" />
        </div>
      </section>
      <section class="panel notes-panel">
        <header class="panel-heading">
          <h2>研究笔记</h2>
          <Icon name="book" :size="16" />
        </header>
        <form v-if="selectedRun" class="form-body" @submit.prevent="saveNote">
          <span class="muted small note-run-name">{{ selectedRun.name }}</span
          ><label class="field"
            ><span class="sr-only">笔记标题</span
            ><input v-model="title" placeholder="笔记标题" required maxlength="150" /></label
          ><label class="field"
            ><span class="sr-only">研究笔记</span
            ><textarea
              v-model="body"
              placeholder="记录观察、假设和下一步实验…"
              rows="7"
              required
              maxlength="20000"
            /></label
          ><button
            class="button secondary full-width"
            :disabled="busy || !body.trim() || !title.trim()"
          >
            {{ noteId ? '更新笔记' : '保存笔记' }}
          </button>
          <div v-if="notes.length" class="saved-notes">
            <button v-for="note in notes" :key="note.id" type="button" @click="editNote(note)">
              <strong>{{ note.title }}</strong>
              <p>{{ note.body }}</p>
              <time>{{ dateLabel(note.updated_at) }}</time>
            </button>
          </div>
        </form>
        <EmptyState v-else title="选择一项研究" icon="book" />
      </section>
    </div>
  </div>
</template>
