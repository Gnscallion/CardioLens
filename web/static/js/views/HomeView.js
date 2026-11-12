/* 首页：项目介绍、系统状态、模型指标、数据集概览、免责声明。 */
import { computed, onMounted } from 'vue';

import { ClassStackBar, DisclaimerNote, StatCard } from '../components/common.js';
import { int, num, pct } from '../format.js';
import { store } from '../store.js';

export default {
  name: 'HomeView',
  components: { ClassStackBar, DisclaimerNote, StatCard },

  setup() {
    const metrics = computed(() => store.metrics || {});
    const test = computed(() => metrics.value.test || {});
    const meta = computed(() => store.meta || {});

    const hasMetrics = computed(() => !!store.metrics);

    /**
     * 主指标用四类 Macro-F1（metrics.json 里的 test.macro_f1）。
     *
     * 原因：按 AAMI 惯例剔除起搏搏动记录后，测试集中 Q 类只剩个位数样本，
     * 不具统计意义。项目同时保留五类 Macro-F1（test.macro_f1_5class）供对照，
     * 界面上两个都展示，不隐藏任何一项。
     */
    const mainF1 = computed(() => test.value.macro_f1);
    const f1Five = computed(() => test.value.macro_f1_5class);

    const classTotals = computed(() => meta.value.class_totals || {});
    const totalBeats = computed(() => meta.value.total_beats || 0);

    const historyStats = computed(() => store.historyStats || {});

    onMounted(() => {
      // 首页只读展示，若首屏没带上指标（例如就绪检查未过），再补取一次
      if (!store.metrics) {
        import('../api.js').then(({ api }) =>
          api.get('/api/metrics')
            .then((d) => { store.metrics = d; })
            .catch(() => { /* 指标缺失不阻断首页 */ })
        );
      }
    });

    return {
      store, metrics, test, meta, hasMetrics, mainF1, f1Five,
      classTotals, totalBeats, historyStats,
      int, num, pct,
    };
  },

  template: `
    <div class="home-view">
      <section class="hero">
        <div class="hero-copy">
          <p class="hero-kicker">CARDIAC SIGNAL INTELLIGENCE</p>
          <h1>{{ store.brand.name }} · {{ store.brand.name_zh }}</h1>
          <p class="hero-sub">{{ store.brand.name_en }}</p>
          <p class="lead">{{ store.brand.tagline }}</p>
          <div class="tagrow">
            <span class="tag">MIT-BIH 心律失常数据库</span>
            <span class="tag">AAMI EC57 五分类</span>
            <span class="tag">1D-CNN + RR 节律分支</span>
            <span class="tag">Grad-CAM 可解释性</span>
            <span class="tag">纯 CPU 推理</span>
          </div>
          <div class="hero-actions">
            <RouterLink class="btn btn-primary btn-lg" to="/analyze">开始分析</RouterLink>
            <RouterLink class="btn btn-light btn-lg" to="/about">了解技术原理</RouterLink>
          </div>
        </div>
        <div class="hero-art" aria-hidden="true">
          <div class="hero-art-glow"></div>
          <img src="/static/img/heart-hero.png" alt="" />
        </div>
      </section>

      <!--
        免责声明放在首屏显眼处，而不是页面末尾：页脚已有一份，放在末尾会
        与页脚紧邻重复；放在顶部则既显著，又不会让人误以为可以跳过。
      -->
      <DisclaimerNote :text="store.disclaimer" />

      <div class="alert alert-err" v-if="!store.ready" data-test="not-ready">
        <span class="ic">⚠️</span>
        <span><strong>服务尚未就绪。</strong>{{ store.readyMessage }}</span>
      </div>

      <div class="grid grid-4">
        <StatCard label="测试集准确率" :value="hasMetrics ? pct(test.accuracy) : '—'" tone="ok" />
        <StatCard label="Macro-F1（四类）" :value="hasMetrics ? num(mainF1, 3) : '—'" />
        <StatCard label="模型参数量" :value="metrics.n_params ? int(metrics.n_params) : '—'" unit="个" />
        <StatCard label="训练耗时" :value="metrics.train_seconds ? num(metrics.train_seconds / 60, 1) : '—'" unit="分钟" tone="accent" />      </div>

      <div class="card mt16">
        <div class="card-head">
          <h2>系统状态</h2>
          <span class="badge" :class="store.ready ? 'badge-ok' : 'badge-warn'">
            {{ store.ready ? '就绪' : '不可用' }}
          </span>
        </div>
        <dl class="kv">
          <dt>数据与模型</dt>
          <dd>{{ store.ready ? '已加载' : store.readyMessage }}</dd>
          <dt>可用记录数</dt>
          <dd>{{ store.records.length }} 条</dd>
          <dt>本浏览器的分析记录</dt>
          <dd>{{ historyStats.total_analyses || 0 }} 份</dd>
        </dl>
        <p class="muted small" style="margin-top:10px">
          登录后分析历史与账号绑定，可跨设备访问；未登录时仅与当前浏览器绑定，不与其他使用者共享。
          <RouterLink to="/history">查看历史记录 →</RouterLink>
        </p>
      </div>

      <div class="grid grid-2">
        <div class="card">
          <h2>数据集概览</h2>
          <p class="card-sub">
            MIT-BIH 心律失常数据库（PhysioNet mitdb），按 AAMI EC57 归并为五类。
            共 {{ meta.n_records || '—' }} 条记录、{{ int(totalBeats) }} 次心搏。
          </p>
          <ClassStackBar :counts="classTotals" />
          <div class="wave-legend">
            <span class="item" v-for="c in store.classes" :key="c.code">
              <span class="badge" :class="'badge-' + c.code">{{ c.code }}</span>
              <span class="muted small">{{ c.name }} × {{ classTotals[c.code] || 0 }}</span>
            </span>
          </div>
          <p class="muted small" style="margin-top:12px">
            采用<b>跨患者划分</b>（inter-patient）：训练集 {{ meta.n_train || '—' }} 搏、
            测试集 {{ meta.n_test || '—' }} 搏，同一患者不会同时出现在两侧，
            避免因记忆患者特征而虚高。
          </p>
        </div>

        <div class="card">
          <h2>五分类定义（AAMI EC57）</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>类别</th><th>名称</th><th>说明</th></tr>
              </thead>
              <tbody>
                <tr v-for="c in store.classes" :key="c.code">
                  <td><span class="badge" :class="'badge-' + c.code">{{ c.code }}</span></td>
                  <td class="nowrap">{{ c.name }}</td>
                  <td class="small muted">{{ c.desc }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="muted small" style="margin-top:10px">
            主指标按 <b>N/S/V/F 四类</b>计算 Macro-F1（{{ num(mainF1, 3) }}）。
            五类 Macro-F1（{{ f1Five != null ? num(f1Five, 3) : '—' }}）同样列出供对照——
            Q 类在测试集中样本极少，不具统计意义，相关说明见"关于"页。
          </p>
        </div>
      </div>
    </div>
  `,
};
