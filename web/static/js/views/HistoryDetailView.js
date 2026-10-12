/* 历史报告详情：只读回放一份已保存的结果。
 *
 * 复用 ResultPanel —— 与刚分析完的结果结构完全一致，
 * 差别只在动作按钮（返回/删除）而非（保存）。
 */
import { onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import ResultPanel from '../components/ResultPanel.js';
import { store } from '../store.js';

export default {
  name: 'HistoryDetailView',
  components: { ResultPanel },

  setup() {
    const route = useRoute();
    const router = useRouter();

    const loading = ref(true);
    const error = ref('');
    const missing = ref(false);

    async function load(id) {
      loading.value = true;
      error.value = '';
      missing.value = false;
      try {
        await store.openHistory(id);
      } catch (err) {
        // 记录不存在（或不属于本会话）时后端返回 404，文案为"记录不存在"
        missing.value = /不存在/.test(err.message);
        error.value = err.message;
      } finally {
        loading.value = false;
      }
    }

    async function remove() {
      if (!store.result) return;
      if (!window.confirm('确定删除这份报告？此操作不可撤销。')) return;
      try {
        await store.deleteHistory(store.savedId);
        store.notify('已删除该报告', 'ok');
        router.push('/history');
      } catch (err) {
        store.notify(err.message, 'err');
      }
    }

    onMounted(() => load(route.params.id));
    watch(() => route.params.id, (id) => { if (id) load(id); });

    return { store, loading, error, missing, remove };
  },

  template: `
    <div>
      <div class="card" v-if="loading">
        <div class="loading">
          <div class="spinner"></div>
          <div>正在读取报告…</div>
        </div>
      </div>

      <div class="card" v-else-if="error">
        <div class="alert alert-err mb0">
          <span class="ic">⚠️</span>
          <span>
            <strong>{{ missing ? '报告不存在。' : '读取失败。' }}</strong>{{ error }}
            <br><span class="small">
              报告可能已被删除；也可能它属于其他浏览器——历史记录按会话隔离，
              每个浏览器只能看到自己的记录。
            </span>
          </span>
        </div>
        <p style="margin-top:16px">
          <RouterLink class="btn btn-primary" to="/history">返回历史列表</RouterLink>
        </p>
      </div>

      <ResultPanel v-else-if="store.result"
                   :result="store.result"
                   :from-history="true"
                   :saved-at="store.savedAt"
                   :saved-id="store.savedId"
                   @delete="remove"
                   @back="$router.push('/history')" />
    </div>
  `,
};
