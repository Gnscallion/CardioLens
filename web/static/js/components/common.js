/* 小型展示组件。
 *
 * 这几个都很薄（统计卡、类别徽标、概率条、构成条、节律信息），
 * 放在一个文件里比拆成五个十几行的模块更好维护。
 */
import { CLASS_COLOR, CLASS_NAME_FALLBACK, CLASS_ORDER, num, pct } from '../format.js';

export const StatCard = {
  name: 'StatCard',
  props: {
    label: String,
    value: [String, Number],
    unit: String,
    tone: { type: String, default: '' },   // '' | accent | ok | warn | danger
  },
  template: `
    <div class="stat" :class="tone">
      <div class="k">{{ label }}</div>
      <div class="v">{{ value }}<span class="u" v-if="unit"> {{ unit }}</span></div>
    </div>
  `,
};

export const ClassBadge = {
  name: 'ClassBadge',
  props: {
    code: String,
    name: String,
  },
  computed: {
    text() {
      return this.name || CLASS_NAME_FALLBACK[this.code] || this.code;
    },
    color() {
      return CLASS_COLOR[this.code] || '#94a3b8';
    },
  },
  template: `
    <span class="badge" :class="'badge-' + code">
      <span class="dot" :style="{ background: color }"></span>{{ code }} · {{ text }}
    </span>
  `,
};

/** 五类概率条。按 AAMI 固定顺序展示，预测类加粗。 */
export const ProbRows = {
  name: 'ProbRows',
  props: {
    probs: { type: Object, default: () => ({}) },
    pred: { type: String, default: '' },
  },
  computed: {
    rows() {
      return CLASS_ORDER.map((code) => ({
        code,
        name: CLASS_NAME_FALLBACK[code],
        value: this.probs[code] ?? 0,
        isPred: code === this.pred,
        color: CLASS_COLOR[code],
      }));
    },
  },
  template: `
    <div>
      <div class="prob-row" v-for="r in rows" :key="r.code">
        <span class="lbl" :style="{ fontWeight: r.isPred ? 700 : 400 }">{{ r.code }} · {{ r.name }}</span>
        <span class="bar"><i :style="{ width: (r.value * 100).toFixed(1) + '%', background: r.color }"></i></span>
        <span class="val" :style="{ fontWeight: r.isPred ? 700 : 400 }">{{ pct(r.value) }}</span>
      </div>
    </div>
  `,
  setup() {
    return { pct };
  },
};

/** 类别构成条：把五类计数画成一条按比例分段的横条。 */
export const ClassStackBar = {
  name: 'ClassStackBar',
  props: {
    counts: { type: Object, default: () => ({}) },
  },
  computed: {
    segments() {
      const total = CLASS_ORDER.reduce((s, c) => s + (this.counts[c] || 0), 0);
      if (!total) return [];
      return CLASS_ORDER
        .map((code) => ({
          code,
          n: this.counts[code] || 0,
          ratio: (this.counts[code] || 0) / total,
          color: CLASS_COLOR[code],
        }))
        .filter((s) => s.n > 0);
    },
  },
  template: `
    <div class="stack" v-if="segments.length">
      <span v-for="s in segments" :key="s.code"
            :style="{ width: (s.ratio * 100) + '%', background: s.color }"
            :title="s.code + ' × ' + s.n">
        {{ s.ratio > 0.07 ? s.n : '' }}
      </span>
    </div>
  `,
};

/**
 * 单搏的节律（RR 间期）信息。
 *
 * 这一段是模型能区分"室上性早搏"与"正常搏动"的关键——单看形态两者几乎
 * 同形，真正区分开的是"提前出现"这一节律信息。因此界面上把它显式列出来。
 */
export const RhythmInfo = {
  name: 'RhythmInfo',
  props: {
    beat: { type: Object, default: () => ({}) },
  },
  computed: {
    // 相对基线明显缩短（早搏特征）时标红
    prevEarly() {
      return this.beat.rr_prev_ratio != null && this.beat.rr_prev_ratio < 0.85;
    },
    nextEarly() {
      return this.beat.rr_next_ratio != null && this.beat.rr_next_ratio < 0.85;
    },
  },
  template: `
    <dl class="kv" v-if="beat.index">
      <dt>前一个 RR 间期</dt>
      <dd :class="{ 'rr-early': prevEarly }">{{ num(beat.rr_prev_sec, 3) }} s
        <span class="muted small">（基线 {{ num(beat.rr_baseline_sec, 3) }} s 的
        {{ num(beat.rr_prev_ratio, 2) }} 倍）</span></dd>
      <dt>后一个 RR 间期</dt>
      <dd :class="{ 'rr-early': nextEarly }">{{ num(beat.rr_next_sec, 3) }} s
        <span class="muted small">（基线的 {{ num(beat.rr_next_ratio, 2) }} 倍）</span></dd>
      <dt>本记录 RR 基线</dt>
      <dd>{{ num(beat.rr_baseline_sec, 3) }} s</dd>
    </dl>
  `,
  setup() {
    return { num };
  },
};

/** 免责声明条。在结果区紧邻展示，避免用户只看结论不看声明。 */
export const DisclaimerNote = {
  name: 'DisclaimerNote',
  props: {
    text: { type: String, default: '' },
  },
  template: `
    <div class="alert alert-warn" v-if="text" data-test="disclaimer">
      <span class="ic">⚕️</span>
      <span>{{ text }}</span>
    </div>
  `,
};
