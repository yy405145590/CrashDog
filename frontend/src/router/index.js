import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'CrashList', component: () => import('../views/CrashList.vue') },
  { path: '/crash/:id', name: 'CrashDetail', component: () => import('../views/CrashDetail.vue') },
  { path: '/symbols', name: 'SymbolList', component: () => import('../views/SymbolList.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
