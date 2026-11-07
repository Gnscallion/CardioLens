import { computed, onMounted, ref } from 'vue';
import { num, pct } from '../format.js';
import { store } from '../store.js';

export default {
  name: 'ResearchView',
  setup() {
    const confidenceThreshold = ref(0.65);
    const experiments = ref([]);
    const experimentName = ref('');
    const runningId = ref(null);
    const jobStatus = ref({});
    async function loadExperiments() { const r = await fetch('/api/research/experiments'); const d = await r.json(); experiments.value = d.items || []; }
    async function createExperiment() { if (!experimentName.value.trim()) return; await fetch('/api/research/experiments', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:experimentName.value, config:{dataset:'MIT-BIH', threshold:confidenceThreshold.value, split:'DS1/DS2'}})}); experimentName.value=''; await loadExperiments(); }
    async function runExperiment(item) {
      runningId.value = item.id;
      try {
        const response = await fetch(`/api/research/experiments/${item.id}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '实验运行失败');
        jobStatus.value[item.id] = data.job_id;
        let job;
        do { await new Promise((resolve) => setTimeout(resolve, 400)); const r = await fetch(`/api/research/jobs/${data.job_id}`); job = await r.json(); }
        while (job.status === 'queued' || job.status === 'running');
        if (job.status === 'failed') throw new Error(job.error || '实验运行失败');
        await loadExperiments();
      } catch (err) { store.notify(err.message, 'err'); }
      finally { runningId.value = null; }
    }
    onMounted(loadExperiments);
    const report = computed(() => {
      const t = store.metrics?.test || {};
      return `CardioLens 科研实验摘要\n\n数据集：MIT-BIH Arrhythmia Database\n划分：跨患者 DS1/DS2\n准确率：${pct(t.accuracy)}\nMacro-F1（四类）：${num(t.macro_f1, 3)}\nMacro-F1（五类）：${num(t.macro_f1_5class, 3)}\n\n说明：本页用于记录研究设计与实验指标，新增实验结果需在后端实际运行后写入，页面不生成虚假指标。`;
    });
    function downloadReport() {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([report.value], { type: 'text/plain;charset=utf-8' }));
      a.download = 'cardiolens-research-summary.txt'; a.click(); URL.revokeObjectURL(a.href);
    }
    return { store, confidenceThreshold, experiments, experimentName, runningId, jobStatus, report, downloadReport, createExperiment, runExperiment, pct, num };
  },
  template: `
    <div>
      <div class="hero"><h1>科研实验与可靠性评估</h1><p class="lead">围绕跨患者泛化、特征消融、置信度校准与错误案例开展可复现实验。</p><div class="tagrow"><span class="tag">Inter-patient validation</span><span class="tag">Ablation study</span><span class="tag">Uncertainty analysis</span></div></div>
      <div class="alert alert-info"><span class="ic">🔬</span><span><strong>研究定位</strong><br>本模块展示真实已有指标，并提供后续实验的配置入口；未运行的实验不会被伪造为结果。</span></div>
      <div class="grid grid-2">
        <div class="card"><h2>当前基线模型</h2><div class="grid grid-3"><div class="stat"><div class="k">Accuracy</div><div class="v">{{ pct(store.metrics?.test?.accuracy) }}</div></div><div class="stat"><div class="k">Macro-F1</div><div class="v">{{ num(store.metrics?.test?.macro_f1, 3) }}</div></div><div class="stat"><div class="k">最佳轮次</div><div class="v">{{ store.metrics?.best_epoch ?? '—' }}</div></div></div><p class="muted small mt16">当前基线：形态分支 + 4 维 RR 节律特征，采用 DS1/DS2 跨患者划分。</p></div>
        <div class="card"><h2>拒识阈值配置</h2><p class="muted small">低于阈值的预测将在结果页标记为“模型不确定”，实际覆盖率与性能需运行批量实验后统计。</p><input type="range" min="0.5" max="0.95" step="0.01" v-model.number="confidenceThreshold"><div class="range-val">当前阈值 {{ (confidenceThreshold * 100).toFixed(0) }}%</div></div>
      </div>
      <div class="card"><div class="card-head"><div><h2>公开数据集使用效果</h2><p class="card-sub">MIT-BIH Arrhythmia Database · PhysioNet · 跨患者 DS1/DS2 划分</p></div><a class="btn btn-ghost btn-sm" href="https://www.physionet.org/content/mitdb/1.0.0/" target="_blank" rel="noreferrer">查看数据源</a></div><div class="grid grid-4"><div class="stat"><div class="k">公开记录数</div><div class="v">{{ store.meta.n_records || '—' }}</div></div><div class="stat"><div class="k">总心搏数</div><div class="v">{{ store.meta.total_beats || '—' }}</div></div><div class="stat ok"><div class="k">测试集准确率</div><div class="v">{{ pct(store.metrics?.test?.accuracy) }}</div></div><div class="stat accent"><div class="k">测试集 Macro-F1</div><div class="v">{{ num(store.metrics?.test?.macro_f1, 3) }}</div></div></div><div class="table-wrap mt16"><table><thead><tr><th>类别</th><th>名称</th><th>精确率</th><th>召回率</th><th>F1</th><th>测试样本</th></tr></thead><tbody><tr v-for="c in store.classes" :key="c.code"><td><span class="badge" :class="'badge-' + c.code">{{ c.code }}</span></td><td>{{ c.name }}</td><td>{{ num(store.metrics?.test?.per_class?.[c.code]?.precision, 3) }}</td><td>{{ num(store.metrics?.test?.per_class?.[c.code]?.recall, 3) }}</td><td>{{ num(store.metrics?.test?.per_class?.[c.code]?.f1, 3) }}</td><td>{{ store.metrics?.test?.per_class?.[c.code]?.support || '—' }}</td></tr></tbody></table></div><p class="muted small mt16 mb0">以上指标来自公开 MIT-BIH 数据集的独立测试集，不是上传数据的演示结果。当前模型在 N、V 类表现较好，但 S 类召回率较低，F/Q 类样本不足或识别能力有限；这些限制保留用于科研分析。</p></div>
      <div class="card"><div class="card-head"><div><h2>公开数据集代表性记录</h2><p class="card-sub">下表来自当前服务实际加载的 MIT-BIH 公开记录，可进入 ECG 分析页查看波形和逐搏预测。</p></div><RouterLink class="btn btn-primary btn-sm" to="/analyze">进入公开数据分析</RouterLink></div><div class="table-wrap"><table><thead><tr><th>记录</th><th>数据划分</th><th>总心搏</th><th>N</th><th>S</th><th>V</th><th>F</th><th>Q</th><th>特点</th></tr></thead><tbody><tr v-for="r in store.records.filter(x => x.recommended)" :key="r.id"><td><b>{{ r.id }}</b></td><td><span class="badge" :class="r.split && r.split.includes('DS2') ? 'badge-ok' : 'badge-info'">{{ r.split }}</span></td><td>{{ r.n_beats }}</td><td>{{ r.class_counts?.N || 0 }}</td><td>{{ r.class_counts?.S || 0 }}</td><td>{{ r.class_counts?.V || 0 }}</td><td>{{ r.class_counts?.F || 0 }}</td><td>{{ r.class_counts?.Q || 0 }}</td><td class="small muted">{{ r.note || '公开记录' }}</td></tr></tbody></table></div></div>
      <div class="card"><h2>计划中的消融实验</h2><div class="table-wrap"><table><thead><tr><th>实验组</th><th>变化</th><th>研究问题</th><th>状态</th></tr></thead><tbody><tr><td>Baseline CNN</td><td>仅形态特征</td><td>单搏波形本身的分类能力</td><td><span class="badge badge-mute">待运行</span></td></tr><tr><td>CNN + RR</td><td>加入相对 RR 特征</td><td>节律特征是否改善 S/V 识别</td><td><span class="badge badge-ok">当前基线</span></td></tr><tr><td>No Augmentation</td><td>关闭数据增强</td><td>增强对跨患者泛化的影响</td><td><span class="badge badge-mute">待运行</span></td></tr><tr><td>Robustness</td><td>注入不同强度噪声</td><td>模型对采集噪声是否稳定</td><td><span class="badge badge-mute">待运行</span></td></tr></tbody></table></div></div>
      <div class="card"><div class="card-head"><h2>实验记录库</h2><div style="display:flex;gap:8px"><input v-model="experimentName" placeholder="实验名称"><button class="btn btn-primary btn-sm" @click="createExperiment">保存配置</button></div></div><div v-if="!experiments.length" class="muted small">暂无实验记录。</div><div v-else class="table-wrap"><table><thead><tr><th>ID</th><th>实验名称</th><th>状态</th><th>真实指标</th><th>创建时间</th><th></th></tr></thead><tbody><tr v-for="e in experiments" :key="e.id"><td>{{ e.id }}</td><td>{{ e.name }}</td><td>{{ e.status }}</td><td class="small">{{ e.metrics ? (e.metrics.n_records + ' 条记录 · ' + e.metrics.n_beats + ' 搏 · 低置信度 ' + e.metrics.low_confidence_count) : '尚未运行' }}</td><td>{{ e.created_at }}</td><td><button class="btn btn-ghost btn-sm" :disabled="runningId === e.id" @click="runExperiment(e)">{{ runningId === e.id ? '运行中…' : '运行实验' }}</button></td></tr></tbody></table></div></div>
      <div class="card"><h2>可靠性与错误分析指标</h2><div class="grid grid-4"><div class="stat"><div class="k">平均置信度</div><div class="v">{{ experiments[0]?.metrics?.mean_confidence ?? '待实验' }}</div></div><div class="stat"><div class="k">置信度标准差</div><div class="v">{{ experiments[0]?.metrics?.confidence_std ?? '待实验' }}</div></div><div class="stat"><div class="k">95% 置信区间半宽</div><div class="v">{{ experiments[0]?.metrics?.confidence_95_ci ?? '待实验' }}</div></div><div class="stat"><div class="k">低置信度搏动</div><div class="v">{{ experiments[0]?.metrics?.low_confidence_count ?? '待实验' }}</div></div></div><div class="grid grid-2 mt16"><div class="stat accent"><div class="k">ECE（期望校准误差）</div><div class="v">{{ experiments[0]?.metrics?.calibration?.ece ?? '无标注' }}</div></div><div class="stat accent"><div class="k">Brier Score</div><div class="v">{{ experiments[0]?.metrics?.calibration?.brier_score ?? '无标注' }}</div></div></div><p class="muted small mt16">ECE 越低表示置信度越接近实际准确率；Brier Score 越低越好。指标仅在存在专家标注时计算。</p></div>
      <div class="card"><div class="card-head"><h2>导出科研摘要</h2><button class="btn btn-primary btn-sm" @click="downloadReport">下载实验摘要</button></div><p class="muted mb0">导出的文本包含当前真实基线指标、数据划分和实验边界，可作为实验记录的起点。</p></div>
    </div>`
};
