<script setup lang="ts">
import Icon from './Icon.vue'
defineProps<{ title: string; text?: string; icon?: string }>()
</script>
<template>
  <div class="empty-state">
    <Icon :name="icon || 'flask'" :size="30" />
    <h3>{{ title }}</h3>
    <p v-if="text">{{ text }}</p>
    <slot />
  </div>
</template>
