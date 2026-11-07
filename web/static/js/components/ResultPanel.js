/* 分析结果面板。
 *
 * 分析页与历史详情页共用同一个组件：两者的数据结构完全一致，
 * 差别只在"可保存"与"可删除"这两个动作的有无。
 * 桌面版也是这么做的（ResultPage 以 readonly 参数实例化两次）。
 */
import { computed, ref, watch } from 'vue';

import { num, pct, riskClass } from '../format.js';
import BeatChart from './BeatChart.js';
import BeatTable from './BeatTable.js';
import { ClassBadge, ClassStackBar, DisclaimerNote, ProbRows, RhythmInfo } from './common.js';
import EcgStrip from './EcgStrip.js';

export default {
  name: 'ResultPanel',
  components: {
    BeatChart, BeatTable, ClassBadge, ClassStackBar,
    DisclaimerNote, ProbRows, RhythmInfo, EcgStrip,
  },
  props: {
    result: { type: Object, required: true },
    fromHistory: { type: Boolean, default: false },
    savedAt: { type: String, default: '' },
    savedId: { type: Number, default: null },
    saving: { type: Boolean, default: false },
    saved: { type: Boolean, default: false },
  },
  emits: ['save', 'delete', 'back'],

  setup(props) {
    const selected = ref(0);
    const strip = ref(null);

    // 换了结果就把选中项复位，否则会指向上一份报告里不存在的下标
    watch(
      () => props.result,
      (r) => {
        selected.value = r && r.beats && r.beats.length ? 0 : -1;
      }
    );

    const beats = computed(() => props.result.beats || []);
    const summary = computed(() => props.result.summary || {});
    const currentBeat = computed(() =>
      selected.value >= 0 ? beats.value[selected.value] || null : null
    );

    const insights = computed(() => {
      const s = summary.value || {};
      const list = beats.value;
      const low = list.filter(b => Math.max(...Object.values(b.probs || {}).map(Number)) < 0.65).length;
      const abnormal = list.filter(b => b.pred && b.pred !== 'N');
      const rr = list.map(b => Number(b.rr_prev_sec)).filter(v => Number.isFinite(v) && v > 0);
      const meanRr = rr.length ? rr.reduce((a, b) => a + b, 0) / rr.length : 0;
      const shortest = rr.length ? Math.min(...rr) : 0;
      const riskText = s.abnormal_count ? `本窗口检测到 ${s.abnormal_count} 个非 N 类搏动，建议重点查看波形标记位置。` : '本窗口未检测到非 N 类搏动，仍请结合原始波形与专家意见理解结果。';
      return { low, abnormal: abnormal.length, meanRr, shortest, riskText };
    });

    const windowText = computed(() => {
      const r = props.result;
      return `记录 ${r.record_id} · ${num(r.start_sec, 1)}s 起 ${num(r.duration_sec, 0)} 秒`;
    });

    /** 该记录属于训练集还是测试集——决定"一致率"能不能当作泛化能力 */
    const splitNote = computed(() => {
      const r = props.result;
      if (r.in_training_set) {
        return {
          kind: 'warn',
          icon: '⚠️',
          title: '该记录属于训练集（DS1）',
          text: '模型在训练时见过这条记录，因此"与专家标注一致率"会明显偏高，'
              + '不能当作模型的泛化能力证据。要看真实水平请选择测试集（DS2）记录。',
        };
      }
      if (r.split) {
        return {
          kind: 'ok',
          icon: '✓',
          title: '该记录属于测试集（DS2）',
          text: '模型训练时未见过这条记录，此处的一致率可以反映模型在未见过数据上的表现。',
        };
      }
      return null;
    });

    function onSelect(i) {
      selected.value = i;
    }

    function focusBeat() {
      if (strip.value && selected.value >= 0) strip.value.zoomToBeat(selected.value);
    }

    function downloadReport() {
      const r = props.result, s = summary.value;
      const text = [`CardioLens ECG 科研分析报告`, `记录：${r.record_id}`, `窗口：${r.start_sec}s / ${r.duration_sec}s`, `心搏数：${s.n_beats}`, `异常搏动：${s.abnormal_count}（${pct(s.abnormal_ratio)}）`, `平均置信度：${pct(s.mean_confidence)}`, `ECE：${s.ece ?? '无专家标注'}`, `Brier Score：${s.brier_score ?? '无专家标注'}`, `高置信度错误：${s.high_confidence_errors ?? '无专家标注'}`, `风险摘要：${insights.value.riskText}`, `模型不确定搏动：${insights.value.low}`, '', '声明：本报告仅用于科研与辅助分析，不构成医疗诊断。'].join('\n');
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type:'text/plain;charset=utf-8'})); a.download = `ECG_report_${r.record_id}.txt`; a.click(); URL.revokeObjectURL(a.href);
    }
    function downloadData(format) {
      const r = props.result;
      let content, type, extension;
      if (format === 'json') {
        content = JSON.stringify(r, null, 2); type = 'application/json;charset=utf-8'; extension = 'json';
      } else {
        const fields = ['index', 'time_sec', 'pred', 'pred_name', 'confidence', 'expert', 'agree'];
        const rows = [fields.join(','), ...beats.value.map((b) => fields.map((f) => JSON.stringify(b[f] ?? '')).join(','))];
        content = rows.join('\n'); type = 'text/csv;charset=utf-8'; extension = 'csv';
      }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([content], { type }));
      a.download = `ECG_${r.record_id}.${extension}`; a.click(); URL.revokeObjectURL(a.href);
    }

    return {
      selected, strip, beats, summary, currentBeat, insights, windowText, splitNote,
      onSelect, focusBeat, downloadReport,
      downloadData,
      pct, num, riskClass,
    };
  },

  template: `
    <div>
      <!-- 概览 -->
      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="mb0">{{ windowText }}</h2>
            <p class="card-sub" v-if="fromHistory && savedAt">
              保存于 {{ savedAt }}
            </p>
            <p class="card-sub" v-else>本次分析结果</p>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button v-if="fromHistory" class="btn btn-ghost btn-sm" @click="$emit('back')">
              ← 返回历史
            </button>
            <button v-if="!fromHistory" class="btn btn-ghost btn-sm" @click="downloadReport">导出科研报告</button>
            <button class="btn btn-ghost btn-sm" @click="downloadData('json')">JSON</button>
            <button class="btn btn-ghost btn-sm" @click="downloadData('csv')">CSV</button>
            <button v-if="!fromHistory" class="btn btn-primary btn-sm"
                    data-test="save-btn"
                    :disabled="saving || saved"
                    @click="$emit('save')">
              {{ saved ? '已保存到历史记录' : (saving ? '保存中…' : '保存报告到历史记录') }}
            </button>
            <button v-if="fromHistory" class="btn btn-danger btn-sm" @click="$emit('delete')">
              删除此报告
            </button>
          </div>
        </div>

        <div class="risk" :class="riskClass(summary.risk_level && summary.risk_level.code)">
          <div class="t">{{ summary.risk_level && summary.risk_level.label }}</div>
          <div class="d">{{ summary.risk_level && summary.risk_level.desc }}</div>
        </div>

        <div class="grid grid-4 mt16">
          <div class="stat"><div class="k">窗口内心搏数</div><div class="v">{{ summary.n_beats }}</div></div>
          <div class="stat"><div class="k">平均置信度</div><div class="v">{{ pct(summary.mean_confidence) }}</div></div>
          <div class="stat" :class="summary.abnormal_count ? 'warn' : 'ok'">
            <div class="k">异常搏动数</div><div class="v">{{ summary.abnormal_count }}</div>
          </div>
          <div class="stat" :class="summary.abnormal_ratio >= 0.3 ? 'danger' : (summary.abnormal_ratio > 0 ? 'warn' : 'ok')">
            <div class="k">异常搏动占比</div><div class="v">{{ pct(summary.abnormal_ratio) }}</div>
          </div>
        </div>

        <div class="grid grid-2 mt16">
          <div class="alert alert-info mb0">
            <span class="ic">🧭</span>
            <span><strong>智能摘要</strong><br>{{ insights.riskText }}<span v-if="insights.low">其中 {{ insights.low }} 个搏动的最高类别概率低于 65%，已标记为“模型不确定”。</span></span>
          </div>
          <div class="alert alert-mute mb0">
            <span class="ic">📈</span>
            <span><strong>节律统计</strong><br>有效 RR 间期 {{ beats.length ? beats.length : 0 }} 个<span v-if="insights.meanRr">，平均 {{ insights.meanRr.toFixed(3) }}s，最短 {{ insights.shortest.toFixed(3) }}s</span>。可点击下方搏动定位异常片段。</span>
          </div>
        </div>
        <div class="grid grid-3 mt16" v-if="summary.ece != null">
          <div class="stat"><div class="k">ECE 校准误差</div><div class="v">{{ summary.ece.toFixed(4) }}</div></div>
          <div class="stat"><div class="k">Brier Score</div><div class="v">{{ summary.brier_score.toFixed(4) }}</div></div>
          <div class="stat" :class="summary.high_confidence_errors ? 'warn' : 'ok'"><div class="k">高置信度错误</div><div class="v">{{ summary.high_confidence_errors }}</div></div>
        </div>

        <div class="grid grid-2 mt16">
          <div>
            <h3>类别构成</h3>
            <ClassStackBar :counts="summary.counts" />
            <div class="wave-legend">
              <span class="item" v-for="c in (result.classes || [])" :key="c.code">
                <span class="badge" :class="'badge-' + c.code">{{ c.code }}</span>
                <span class="muted small">{{ c.name }} × {{ (summary.counts || {})[c.code] || 0 }}</span>
              </span>
            </div>
          </div>
          <div>
            <h3>与专家标注的一致率</h3>
            <div class="stat" style="margin-bottom:8px">
              <div class="k">逐搏一致率</div>
              <div class="v">{{ pct(summary.agreement) }}</div>
            </div>
            <p class="muted small mb0">
              一致率受"该记录是否属于训练集"影响极大，请结合下方提示理解。
            </p>
          </div>
        </div>

        <div v-if="splitNote" class="alert mt16" :class="'alert-' + (splitNote.kind === 'ok' ? 'ok' : 'warn')"
             data-test="split-note">
          <span class="ic">{{ splitNote.icon }}</span>
          <span><strong>{{ splitNote.title }}</strong><br>{{ splitNote.text }}</span>
        </div>

        <DisclaimerNote :text="result.disclaimer" />
      </div>

      <!-- 波形 -->
      <div class="card">
        <div class="card-head">
          <h2>心电波形</h2>
          <p class="card-sub mb0">
            绿色折线为心电信号，顶部圆点为逐搏判定（颜色对应类别），
            橙色区域为该搏的 Grad-CAM 显著性。
          </p>
        </div>
        <EcgStrip ref="strip"
                  :signal="result.signal"
                  :fs="result.fs"
                  :start-sec="result.start_sec"
                  :beats="beats"
                  :selected="selected"
                  :show-cam="true"
                  :height="340"
                  @select="onSelect" />
      </div>

      <!-- 逐搏明细 -->
      <div class="card">
        <div class="card-head">
          <h2>逐搏结果</h2>
          <p class="card-sub mb0">点击任意一行查看该搏的波形、五类概率与节律特征。</p>
        </div>
        <BeatTable :beats="beats" :selected="selected"
                   :start-sec="result.start_sec" :fs="result.fs"
                   @select="onSelect" />
      </div>

      <!-- 单搏详情 -->
      <div class="card" v-if="currentBeat">
        <div class="card-head">
          <h2>
            第 {{ currentBeat.index }} 搏 ·
            {{ currentBeat.pred }} {{ currentBeat.pred_name }}
          </h2>
          <button class="btn btn-ghost btn-sm" @click="focusBeat">在波形上聚焦此搏</button>
        </div>

        <div class="grid grid-2">
          <div>
            <BeatChart :beat="currentBeat" :signal="result.signal" :height="210" />
            <p class="muted small" style="margin-top:8px">
              <template v-if="currentBeat.cam">
                Grad-CAM 长度 {{ currentBeat.cam.length }} 点，与该搏采样点严格对齐；
                颜色越亮表示模型判定这一搏时越关注该时刻。
              </template>
              <template v-else>
                该搏未生成 Grad-CAM（本次分析关闭了可解释性，或生成过程出错）。
                这不影响分类结果本身。
              </template>
            </p>
          </div>
          <div>
            <h3>五类概率</h3>
            <ProbRows :probs="currentBeat.probs" :pred="currentBeat.pred" />
            <h3 style="margin-top:18px">节律特征（RR 间期）</h3>
            <RhythmInfo :beat="currentBeat" />
          </div>
        </div>

        <div class="alert alert-mute" style="background:var(--surface-alt);border-color:var(--border)">
          <span>
            专家标注：<strong>{{ currentBeat.expert }} · {{ currentBeat.expert_name }}</strong>
            ——
            <span v-if="currentBeat.agree">模型判定与专家标注一致。</span>
            <span v-else>模型判定与专家标注不一致。</span>
            <span class="muted small">（专家标注仅用于课程演示中的对照评估，实际使用时不参与判定。）</span>
          </span>
        </div>
      </div>
    </div>
  `,
};
