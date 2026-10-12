/* 前端入口。 */
import { createApp } from 'vue';

import App from './App.js';
import { router } from './router.js';
import { store } from './store.js';

const app = createApp(App);

/*
 * 全局错误兜底。
 *
 * 组件渲染或事件处理里抛出的异常若没人接，Vue 默认只在控制台打印，
 * 用户看到的是"点了没反应"。这里统一转成界面上的提示。
 */
app.config.errorHandler = (err, _instance, info) => {
  console.error('[未捕获的前端异常]', info, err);
  store.notify(err?.message || '页面出现异常，请刷新后重试', 'err');
};

// 接口层已经处理过的错误不再重复弹提示，这里只兜住漏网的 promise 拒绝
window.addEventListener('unhandledrejection', (ev) => {
  console.error('[未处理的 Promise 拒绝]', ev.reason);
});

app.use(router);

/*
 * 等首次路由解析完再挂载。
 *
 * 直接 mount 会让深链先渲染一次空内容再跳到目标页；等 router.isReady()
 * 之后挂载，则首帧就是正确的页面。
 */
router.isReady().then(() => {
  app.mount('#app');
});
