/* ==========================================================================
   节律特征渲染 —— 分析页与历史详情页共用

   把模型实际输入的 RR 间期摊开给用户看：单看波形无法解释"为什么判为早搏"，
   把节律依据摆出来，模型的判断才有据可查。

   判定"提前"用的是相对本记录基线（RR 中位数）的比值，而不是某个固定秒数：
   各记录基础心率差异很大（本项目跨度 50–112 bpm），固定阈值在快心率记录上
   会把正常搏动误标为提前，在慢心率记录上又会漏掉真正的早搏。
   ========================================================================== */
(function (global) {
  'use strict';

  const EARLY_RATIO = 0.85;      // 短于基线的 85% 视为"提前出现"

  function cell(sec, ratio) {
    const early = ratio < EARLY_RATIO;
    return '<strong' + (early ? ' class="rr-early"' : '') + '>' +
           Number(sec).toFixed(3) + ' s</strong>' +
           ' <span class="muted">(' + Number(ratio).toFixed(2) + '× 基线' +
           (early ? '，提前' : '') + ')</span>';
  }

  /**
   * 渲染某搏的节律特征区块。
   * @param {object} b 逐搏结果，需含 rr_prev_sec / rr_next_sec / rr_baseline_sec /
   *                   rr_prev_ratio / rr_next_ratio（旧报告可能缺后两项，此时不渲染）
   * @returns {string} HTML 片段；数据不完整时返回空串
   */
  function render(b) {
    if (!b) return '';
    const { rr_prev_sec: prev, rr_next_sec: next, rr_baseline_sec: base,
            rr_prev_ratio: prevRatio, rr_next_ratio: nextRatio } = b;

    // 早期版本保存的报告没有比值字段，此时退回不展示，避免显示 NaN
    if (prev == null || next == null || base == null || prevRatio == null || nextRatio == null) {
      return '';
    }
    if (!(base > 0)) return '';

    const early = prevRatio < EARLY_RATIO;
    const note = early
      ? '该搏前一 RR 间期仅为基线的 ' + Number(prevRatio).toFixed(2) +
        ' 倍，符合"提前出现"的异位搏动特征。'
      : '该搏前后 RR 间期相对基线未见明显缩短，节律较规则。';

    return '<div class="small muted" style="margin-top:10px">节律特征（模型输入）：</div>' +
      '<div class="small" style="margin:6px 0 0">' +
        '前一 RR ' + cell(prev, prevRatio) + ' &nbsp;·&nbsp; ' +
        '后一 RR ' + cell(next, nextRatio) +
      '</div>' +
      '<div class="small muted" style="margin-top:4px">本记录 RR 基线（中位数）' +
        Number(base).toFixed(3) + ' s。' + note + '</div>';
  }

  global.ECGRhythm = { render: render, EARLY_RATIO: EARLY_RATIO };
})(window);
