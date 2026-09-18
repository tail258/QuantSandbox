<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import Icon from './Icon.vue'
defineProps<{ title: string; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLElement>()
let previous: HTMLElement | null = null
const keydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') emit('close')
  if (event.key !== 'Tab') return
  const nodes = dialog.value?.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, [tabindex="0"]',
  )
  if (!nodes?.length) return
  const first = nodes[0],
    last = nodes[nodes.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
onMounted(() => {
  previous = document.activeElement as HTMLElement
  dialog.value?.focus()
  document.addEventListener('keydown', keydown)
  document.body.style.overflow = 'hidden'
})
onUnmounted(() => {
  document.removeEventListener('keydown', keydown)
  document.body.style.overflow = ''
  previous?.focus()
})
</script>

<template>
  <Teleport to="body"
    ><div class="modal-backdrop" @mousedown.self="emit('close')">
      <section
        ref="dialog"
        tabindex="-1"
        class="modal"
        :class="{ wide }"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <header class="modal-heading">
          <h2>{{ title }}</h2>
          <button class="icon-button" type="button" aria-label="关闭对话框" @click="emit('close')">
            <Icon name="close" />
          </button>
        </header>
        <slot />
      </section></div
  ></Teleport>
</template>
