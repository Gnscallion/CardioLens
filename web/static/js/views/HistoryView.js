/* 分析历史：列表、查看详情、单条删除、清空全部。
 * 数据范围限于当前浏览器（会话隔离），文案上要讲清楚这一点。 */
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import SessionNotice from '../components/SessionNotice.js';
import { StatCard } from '../components/common.js';
import { num, pct, relTime } from '../format.js';
import { store } from '../store.js';

export default {
  name: 'HistoryView',
  components: { SessionNotice, StatCard },

  setup() {
    const router = useRouter();
    const route = useRoute();
    const busy = ref(false);

    const allItems = computed(() => store.history || []);
    const items = computed(() => {
      const all = allItems.value;
      const q = String(route.query.q || '').trim().toLowerCase();
      if (!q) return all;
      return all.filter((item) => `${item.title || ''} ${item.record_id || ''}`.toLowerCase().includes(q));
    });
    const stats = computed(() => store.historyStats || {});

    async function refresh() {
      busy.value = true;
      try {
        await store.loadHistory();
      } catch (err) {
        store.notify(err.message, 'err');
      } finally {
        busy.value = false;
      }
    }

    async function remove(item) {
      if (!window.confirm(`确定删除「${item.title}」？此操作不可撤销。`)) return;
      try {
        await store.deleteHistory(item.id);
        store.notify('已删除该报告', 'ok');
      } catch (err) {
        store.notify(err.message, 'err');
      }
    }

    async function clearAll() {
      if (!allItems.value.length) return;
      const n = allItems.value.length;
      if (!window.confirm(`确定清空本浏览器的全部 ${n} 份报告？此操作不可撤销。`)) return;
      try {
        const data = await store.clearHistory();
        store.notify(`已清空 ${data.deleted} 份报告`, 'ok');
      } catch (err) {
        store.notify(err.message, 'err');
      }
    }

    function open(id) {
      router.push(`/history/${id}`);
    }

    onMounted(refresh);

    return { store, items, stats, busy, refresh, remove, clearAll, open, relTime, pct, num };
  },

  template: `
    <div>
      <SessionNotice />

      <div class="grid grid-4">
        <StatCard label="保存的报告" :value="stats.total_analyses || 0" unit="份" />
        <StatCard label="累计分析心搏" :value="stats.total_beats || 0" unit="次" tone="accent" />
        <StatCard label="平均异常占比" :value="pct(stats.avg_abnormal_ratio)" tone="warn" />
        <StatCard label="平均一致率" :value="pct(stats.avg_agreement)" tone="ok" />
      </div>

      <div class="card mt16">
        <div class="card-head">
          <h2>分析历史</h2>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" :disabled="busy" @click="refresh">
              {{ busy ? '刷新中…' : '刷新' }}
            </button>
            <button class="btn btn-danger btn-sm" data-test="clear-btn"
                    :disabled="!items.length" @click="clearAll">
              清空全部
            </button>
          </div>
        </div>

        <div class="empty" v-if="!items.length && !busy">
          <div class="big">📋</div>
          <p>本浏览器还没有保存过分析报告。</p>
          <RouterLink class="btn btn-primary" to="/analyze">去做一次分析</RouterLink>
        </div>

        <div class="table-wrap" v-else>
          <table data-test="history-table">
            <thead>
              <tr>
                <th class="num">编号</th>
                <th>标题</th>
                <th>记录</th>
                <th class="num">时间窗</th>
                <th class="num">心搏数</th>
                <th class="num">异常占比</th>
                <th>提示等级</th>
                <th class="num">一致率</th>
                <th>分析时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in items" :key="it.id" class="clickable" @click="open(it.id)">
                <td class="num">{{ it.id }}</td>
                <td>{{ it.title }}</td>
                <td class="mono">{{ it.record_id }}</td>
                <td class="num">{{ num(it.start_sec, 1) }}s · {{ num(it.duration_sec, 0) }}s</td>
                <td class="num">{{ it.n_beats }}</td>
                <td class="num">{{ pct(it.abnormal_ratio) }}</td>
                <td>
                  <span class="badge"
                        :class="it.risk_code === 'high' ? 'badge-V' : (it.risk_code === 'medium' ? 'badge-S' : 'badge-N')">
                    {{ it.risk_label }}
                  </span>
                </td>
                <td class="num">{{ pct(it.agreement) }}</td>
                <td class="nowrap small muted">{{ relTime(it) }}</td>
                <td class="nowrap">
                  <button class="btn btn-ghost btn-sm" @click.stop="open(it.id)">查看</button>
                  <button class="btn btn-danger btn-sm" @click.stop="remove(it)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="muted small" style="margin-top:10px">
          「一致率」是模型判定与专家标注的逐搏一致比例。该指标受记录是否属于训练集影响极大，
          详情页会如实提示。
        </p>
      </div>
    </div>
  `,
};
