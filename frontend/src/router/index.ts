import { createRouter, createWebHashHistory } from 'vue-router'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/terminal' },
    {
      path: '/terminal',
      name: 'terminal',
      component: () => import('../views/TerminalView.vue'),
      meta: { title: '推演终端' },
    },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('../views/OverviewView.vue'),
      meta: { title: '研究总览' },
    },
    {
      path: '/lab',
      name: 'lab',
      component: () => import('../views/LabView.vue'),
      meta: { title: '实验室' },
    },
    {
      path: '/data',
      name: 'data',
      component: () => import('../views/DataView.vue'),
      meta: { title: '数据中心' },
    },
    {
      path: '/archive',
      name: 'archive',
      component: () => import('../views/ArchiveView.vue'),
      meta: { title: '研究档案' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/terminal' },
  ],
})
