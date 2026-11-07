/* 路由表。
 *
 * 用 history 模式（而非 hash），URL 与更早的版本保持一致：
 * / 、/analyze 、/history 、/history/12 、/about
 * 这样文档、截图脚本与旧链接都能直接沿用，深链也可以分享。
 *
 * 服务端对应地把这些路径都返回 SPA 壳（见 web/views/pages.py 与 web/errors.py）。
 */
import { createRouter, createWebHistory } from 'vue-router';

import AboutView from './views/AboutView.js';
import AnalyzeView from './views/AnalyzeView.js';
import HistoryDetailView from './views/HistoryDetailView.js';
import HistoryView from './views/HistoryView.js';
import HomeView from './views/HomeView.js';
import ResearchView from './views/ResearchView.js';
import AuthView from './views/AuthView.js';

const NotFound = {
  name: 'NotFound',
  template: `
    <div class="card">
      <div class="empty">
        <div class="big">🧭</div>
        <h2>页面不存在</h2>
        <p>你访问的地址没有对应的页面。</p>
        <RouterLink class="btn btn-primary" to="/">返回首页</RouterLink>
      </div>
    </div>
  `,
};

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { nav: 'home' } },
    { path: '/analyze', name: 'analyze', component: AnalyzeView, meta: { nav: 'analyze' } },
    { path: '/history', name: 'history', component: HistoryView, meta: { nav: 'history' } },
    {
      path: '/history/:id(\\d+)',
      name: 'history-detail',
      component: HistoryDetailView,
      meta: { nav: 'history' },
    },
    { path: '/about', name: 'about', component: AboutView, meta: { nav: 'about' } },
    { path: '/research', name: 'research', component: ResearchView, meta: { nav: 'research' } },
    { path: '/auth', name: 'auth', component: AuthView, meta: { nav: 'auth' } },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFound },
  ],
  scrollBehavior(to, from, saved) {
    return saved || { top: 0 };
  },
});

export const NAV_ITEMS = [
  { key: 'home', to: '/', label: '首页' },
  { key: 'analyze', to: '/analyze', label: 'ECG 分析' },
  { key: 'history', to: '/history', label: '分析历史' },
  { key: 'about', to: '/about', label: '关于' },
  { key: 'research', to: '/research', label: '科研实验' },
  { key: 'auth', to: '/auth', label: '登录 / 注册' },
];
