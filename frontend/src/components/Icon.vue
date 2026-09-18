<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
const paths: Record<string, string[]> = {
  grid: ['M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z'],
  monitor: ['M3 4h18v13H3zM8 21h8M12 17v4'],
  flask: ['M9 3h6M10 3v7L4 20q-.5 1 1 1h14q1.5 0 1-1l-6-10V3M8 15h8M10 18h.01'],
  database: [
    'M20 5c0 2-3.6 3-8 3S4 7 4 5s3.6-3 8-3 8 1 8 3ZM4 5v14c0 2 3.6 3 8 3s8-1 8-3V5M4 12c0 2 3.6 3 8 3s8-1 8-3',
  ],
  book: ['M5 3h14v18H5zM8 7h8M8 11h8M8 15h5'],
  folder: ['M3 6V4h7l2 3h9v14H3V6Z'],
  arrow: ['M4 12h16M14 6l6 6-6 6'],
  download: ['M12 3v12M7 10l5 5 5-5M4 16v5h16v-5'],
  plus: ['M12 4v16M4 12h16'],
  close: ['M6 6l12 12M6 18 18 6'],
  play: ['m8 4 12 8-12 8V4Z'],
  pause: ['M7 4v16M17 4v16'],
  reset: ['M5 5v14M19 5 7 12l12 7V5Z'],
  next: ['M19 5v14M5 5l12 7-12 7V5Z'],
  branch: ['M7 7v10M7 10c9 0 10-2 10-4M5 3h4v4H5zM5 17h4v4H5zM15 2h4v4h-4z'],
  chevron: ['m6 9 6 6 6-6'],
  refresh: ['M20 7V3l-3 3a8 8 0 1 0 3 10M20 7h-5'],
  check: ['m5 12 4 4L19 6'],
  alert: ['M12 3 2 21h20L12 3ZM12 9v5M12 17h.01'],
  eye: ['M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z', 'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0'],
  lock: ['M5 10h14v11H5zM8 10V7a4 4 0 1 1 8 0v3'],
  search: ['M16 16l5 5M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0'],
  clock: ['M12 7v5l3 2M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0'],
  menu: ['M4 6h16M4 12h16M4 18h16'],
  candle: ['M7 2v4M7 15v7M4 6h6v9H4zM17 2v7M17 18v4M14 9h6v9h-6z'],
  expand: ['M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5'],
  settings: ['M4 7h16M4 17h16M8 4v6M16 14v6'],
  info: ['M12 11v6M12 7h.01M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0'],
  globe: ['M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0M2 12h20M12 2c-6 6-6 14 0 20 6-6 6-14 0-20'],
}
</script>

<template>
  <svg
    :width="size || 18"
    :height="size || 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="(d, i) in paths[name] || paths.info" :key="i" :d="d" />
  </svg>
</template>
