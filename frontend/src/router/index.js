import { createRouter, createWebHistory } from 'vue-router';
import Dashboard from '../views/Dashboard.vue';
import Detail from '../views/Detail.vue';

const routes = [
  { path: '/', component: Dashboard },
  { path: '/stock/:ticker', component: Detail, props: true },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;