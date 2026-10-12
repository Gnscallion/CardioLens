/* 全局状态。
 *
 * 刻意只用 Vue 的 reactive()，不引入 Pinia：需要在视图间共享的只有
 * 状态、记录列表、指标、历史、当前结果与当前选中搏动这几项，
 * 多一层状态库带来的只有额外的依赖与心智负担。
 */
import { reactive } from 'vue';

import { api } from './api.js';

const boot = window.__BOOT__ || {};

export const store = reactive({
  // 首屏由服务端内联，避免深链白屏
  brand: boot.brand || { name: 'CardioLens', name_zh: '', name_en: '', tagline: '' },
  disclaimer: boot.disclaimer || '',
  ready: !!boot.ready,
  readyMessage: boot.ready_message || '',
  classes: boot.classes || [],
  metrics: boot.metrics || null,
  meta: boot.meta || {},
  records: boot.records || [],
  historyStats: boot.history || null,

  history: [],
  historyLoaded: false,

  // 当前分析结果（分析页与历史详情页共用同一份结构）
  result: null,
  resultFromHistory: false,
  savedAt: '',
  savedId: null,

  selectedBeat: -1,

  // 预览波形与它对应的窗口（窗口值一律以响应为准，见下）
  preview: null,

  analyzing: false,
  loadingHistory: false,
  toast: null,

  _analyzeAbort: null,
  _toastTimer: null,

  // ------------------------------------------------------------ 提示
  notify(message, kind = 'info') {
    this.toast = { message, kind };
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this.toast = null;
    }, kind === 'err' ? 8000 : 5000);
  },

  // ------------------------------------------------------------ 记录
  async loadRecords() {
    const data = await api.records();
    this.records = data.records || [];
    return this.records;
  },

  // ------------------------------------------------------------ 预览
  async loadPreview(recordId, start, duration) {
    this.preview = await api.preview(recordId, start, duration);
    return this.preview;
  },

  // ------------------------------------------------------------ 分析
  /**
   * 发起分析。
   *
   * 注意：窗口的**真实取值以响应为准**。后端在 start+duration 超出记录
   * 末尾时会向左回退对齐，若前端回显自己传的滑块值，波形标题与十字线
   * 读数就会整体偏移。因此这里保存响应里的 start_sec / duration_sec。
   */
  async runAnalysis({ recordId, startSec, durationSec, withCam, save, title }) {
    this._analyzeAbort = new AbortController();
    this.analyzing = true;
    try {
      const data = await api.analyze(
        {
          record_id: recordId,
          start_sec: startSec,
          duration_sec: durationSec,
          with_cam: withCam,
          save: !!save,
          title: title || undefined,
        },
        this._analyzeAbort.signal
      );
      this.result = data;
      this.resultFromHistory = false;
      this.savedId = data.saved_id ?? null;
      this.savedAt = '';
      this.selectedBeat = data.beats && data.beats.length ? 0 : -1;
      return data;
    } finally {
      this.analyzing = false;
      this._analyzeAbort = null;
    }
  },

  cancelAnalysis() {
    if (this._analyzeAbort) this._analyzeAbort.abort();
  },

  // ------------------------------------------------------------ 历史
  async loadHistory() {
    this.loadingHistory = true;
    try {
      const data = await api.historyList();
      this.history = data.items || [];
      this.historyStats = data.stats || null;
      this.historyLoaded = true;
      return this.history;
    } finally {
      this.loadingHistory = false;
    }
  },

  async openHistory(id) {
    const data = await api.historyDetail(id);
    this.result = data.payload;
    this.resultFromHistory = true;
    this.savedAt = data.created_at || '';
    this.savedId = data.id;
    this.selectedBeat = data.payload && data.payload.beats?.length ? 0 : -1;
    return data;
  },

  async deleteHistory(id) {
    const data = await api.historyDelete(id);
    this.historyStats = data.stats || this.historyStats;
    this.history = this.history.filter((x) => x.id !== id);
    return data;
  },

  async clearHistory() {
    const data = await api.historyClear();
    this.history = [];
    this.historyStats = data.stats || this.historyStats;
    return data;
  },

  /** 清空当前结果（切换页面时用，避免"结果页"显示上一次的残留） */
  clearResult() {
    this.result = null;
    this.resultFromHistory = false;
    this.savedAt = '';
    this.savedId = null;
    this.selectedBeat = -1;
    this.preview = null;
  },
});
