/* 根组件：顶栏导航 + 内容区 + 页脚免责声明。 */
import { computed } from 'vue';
import { useRoute } from 'vue-router';

import { NAV_ITEMS } from './router.js';
import { store } from './store.js';

export default {
  name: 'App',
  setup() {
    const route = useRoute();
    const activeNav = computed(() => route.meta?.nav || '');

    return { store, NAV_ITEMS, activeNav };
  },
  template: `
    <header class="topbar">
      <div class="topbar-inner">
        <RouterLink class="brand" to="/">
          <span class="brand-mark">🫀</span>
          <span class="brand-text">
            <strong>{{ store.brand.name }} · {{ store.brand.name_zh }}</strong>
            <em>{{ store.brand.name_en }}</em>
          </span>
        </RouterLink>
        <nav class="nav">
          <RouterLink v-for="item in NAV_ITEMS" :key="item.key"
                      :to="item.to"
                      :class="{ on: activeNav === item.key }">
            {{ item.label }}
          </RouterLink>
        </nav>
      </div>
    </header>

    <main class="page">
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </main>

    <!-- 全局提示 -->
    <div class="toast-wrap" v-if="store.toast">
      <div class="toast" :class="store.toast.kind">{{ store.toast.message }}</div>
    </div>

    <footer class="footer">
      <div class="footer-inner">
        <div class="warn" v-if="store.disclaimer">
          <strong>⚕️ 重要声明：</strong>{{ store.disclaimer }}
        </div>
        <p class="copy">
          数据集来源：MIT-BIH Arrhythmia Database（PhysioNet）·
          本平台为软件工程课程作业演示项目，不构成医疗诊断依据。
        </p>
      </div>
    </footer>
  `,
};
