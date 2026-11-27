import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import PipelineDashboard from '@/views/PipelineDashboard.vue'
import TraceActivationView from '@/views/TraceActivationView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/pipeline', name: 'pipeline', component: PipelineDashboard },
    { path: '/trace-activation', name: 'trace-activation', component: TraceActivationView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router