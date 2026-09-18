<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { workspace, advanceSession } from '../workspace/store'
import { dateLabel } from '../utils/format'
import Icon from './Icon.vue'
const props = defineProps<{ total: number; date?: string }>()
const emit = defineEmits<{ branch: [] }>()
const playing = ref(false),
  stepping = ref(false)
let timer: number
const cursor = computed(() => workspace.session?.cursor ?? workspace.cursor)
const total = computed(() => workspace.session?.total_steps || props.total)
async function step(count: number) {
  if (stepping.value) return
  stepping.value = true
  try {
    if (workspace.session) await advanceSession(count)
    else workspace.cursor = Math.min(total.value - 1, workspace.cursor + count)
    if (cursor.value >= total.value - 1) stop()
  } catch (error) {
    workspace.error = (error as Error).message
    stop()
  } finally {
    stepping.value = false
  }
}
function stop() {
  playing.value = false
  window.clearInterval(timer)
}
function seek(index: number) {
  stop()
  workspace.cursor = index
}
function toggle() {
  if (playing.value) return stop()
  if (cursor.value >= total.value - 1) {
    if (workspace.session) return
    workspace.cursor = 0
  }
  playing.value = true
  timer = window.setInterval(() => {
    void step(1)
  }, 700)
}
watch(() => workspace.active?.id, stop)
watch(() => workspace.session?.id, stop)
onUnmounted(stop)
</script>
<template>
  <div class="playback-controls">
    <div class="transport">
      <button
        class="icon-button"
        aria-label="回到起点"
        :disabled="!!workspace.session || cursor === 0"
        @click="seek(0)"
      >
        <Icon name="reset" :size="16" /></button
      ><button
        class="icon-button play-button"
        :aria-label="playing ? '暂停推演' : '播放推演'"
        :disabled="total < 2 || (!!workspace.session && cursor >= total - 1)"
        @click="toggle"
      >
        <Icon :name="playing ? 'pause' : 'play'" :size="16" /></button
      ><button
        class="icon-button"
        aria-label="跳至结尾"
        :disabled="!!workspace.session || cursor >= total - 1"
        @click="seek(total - 1)"
      >
        <Icon name="next" :size="16" />
      </button>
    </div>
    <button
      class="button secondary small-button"
      :disabled="stepping || cursor >= total - 1"
      @click="step(1)"
    >
      推进 1 日</button
    ><button
      class="button secondary small-button step-many"
      :disabled="stepping || cursor >= total - 1"
      @click="step(20)"
    >
      推进 20 日
    </button>
    <div class="time-slider">
      <input
        v-if="!workspace.session"
        v-model.number="workspace.cursor"
        type="range"
        :min="0"
        :max="Math.max(0, total - 1)"
        aria-label="推演交易日"
        @input="stop"
      /><progress v-else :value="cursor + 1" :max="total" aria-label="盲测进度" /><span>{{
        dateLabel(date)
      }}</span>
    </div>
    <span class="timeline-count mono">{{ cursor + 1 }} / {{ total }}</span
    ><button
      class="button outline small-button branch-button"
      :disabled="!!workspace.session || workspace.busy || !date"
      @click="emit('branch')"
    >
      <Icon name="branch" :size="16" />从此刻分叉
    </button>
  </div>
</template>
