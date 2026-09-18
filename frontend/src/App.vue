<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Icon from './components/Icon.vue'
import RunComposer from './components/RunComposer.vue'
import { workspace, initialize, sourceLabel } from './workspace/store'
const route = useRoute(),
  mobileOpen = ref(false)
const navigation = [
  { path: '/overview', label: '研究总览', icon: 'grid' },
  { path: '/terminal', label: '推演终端', icon: 'monitor' },
  { path: '/lab', label: '实验室', icon: 'flask' },
  { path: '/data', label: '数据中心', icon: 'database' },
  { path: '/archive', label: '研究档案', icon: 'book' },
]
onMounted(initialize)
</script>
<template>
  <div class="workspace-shell">
    <aside class="workspace-rail" :class="{ 'mobile-open': mobileOpen }">
      <RouterLink to="/terminal" class="brand" @click="mobileOpen = false"
        ><img src="/mark.svg" width="25" height="25" alt="" /><span>QuantSandbox</span></RouterLink
      >
      <nav aria-label="主要导航">
        <RouterLink
          v-for="item in navigation"
          :key="item.path"
          :to="item.path"
          @click="mobileOpen = false"
          ><Icon :name="item.icon" :size="19" /><span>{{ item.label }}</span></RouterLink
        >
      </nav>
      <div class="rail-bottom">
        <Icon name="folder" :size="19" /><span>本地研究空间</span
        ><i class="connection-dot" :class="{ ready: workspace.initialized }" />
      </div>
    </aside>
    <button
      v-if="mobileOpen"
      class="nav-overlay"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    />
    <div class="workspace-content">
      <header class="topbar">
        <button
          class="icon-button mobile-menu"
          aria-label="打开导航"
          @click="mobileOpen = !mobileOpen"
        >
          <Icon name="menu" />
        </button>
        <div class="breadcrumb">{{ route.meta.title }}</div>
        <span class="source-indicator"><i />{{ sourceLabel }}</span>
      </header>
      <div v-if="workspace.error" class="global-error" role="alert">
        <Icon name="alert" :size="17" /><span>{{ workspace.error }}</span
        ><button v-if="!workspace.initialized" class="text-button" @click="initialize">
          重试连接</button
        ><button
          class="icon-button borderless"
          aria-label="关闭错误提示"
          @click="workspace.error = ''"
        >
          <Icon name="close" :size="15" />
        </button>
      </div>
      <div v-if="workspace.loading && !workspace.active" class="initial-loading">
        <div class="spinner" />
        <span>连接研究空间…</span>
      </div>
      <RouterView v-else />
    </div>
    <RunComposer
      v-if="workspace.createOpen && workspace.catalog"
      @close="workspace.createOpen = false"
    /><Transition name="toast"
      ><div v-if="workspace.toast" class="toast-message" role="status">
        <Icon name="check" :size="17" />{{ workspace.toast }}
      </div></Transition
    >
  </div>
</template>
