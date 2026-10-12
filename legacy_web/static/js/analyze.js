/* ==========================================================================
   智能分析工作台 —— 页面交互逻辑
   流程：选择记录与时间窗 → 预览波形 → 触发分析（带动画步骤）→ 渲染报告 → 保存
   ========================================================================== */
(function () {
  'use strict';

  const RECORDS = JSON.parse(document.getElementById('records-data').textContent);
  const CLASS_ORDER = ['N', 'S', 'V', 'F', 'Q'];
  const CLASS_NAME = {};
  const CLASS_DESC = {};

  const state = { record: null, preview: null, result: null, selected: -1 };

  const $ = id => document.getElementById(id);

  /* ------------------------------------------------------------ 工具 */
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = x => (x * 100).toFixed(1) + '%';
  const num = n => Number(n).toLocaleString('en-US');

  async function api(url, opts) {
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      throw new Error('无法连接后端服务，请确认 Flask 服务正在运行');
    }
    let data;
    try {
      data = await res.json();
    } catch (e) {
      throw new Error('服务器返回了非 JSON 响应（HTTP ' + res.status + '）');
    }
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ('请求失败（HTTP ' + res.status + '）'));
    }
    return data;
  }

  function toast(message, kind) {
    const area = $('resultArea');
    const div = document.createElement('div');
    div.className = 'alert alert-' + (kind || 'err');
    div.innerHTML = '<span>' + (kind === 'info' ? 'ℹ' : '⚠') + '</span><div>' + esc(message) + '</div>';
    area.insertBefore(div, area.firstChild);
    setTimeout(() => div.remove(), 8000);
  }

  /* ------------------------------------------------------------ 记录选择 */
  function initRecords() {
    const sel = $('recSel');
    sel.innerHTML = RECORDS.map(r =>
      '<option value="' + esc(r.id) + '">' + esc(r.label) +
      ' · ' + num(r.n_beats) + ' 搏' +
      (r.recommended ? ' ★' : '') + '</option>'
    ).join('');

    $('quickChips').innerHTML = RECORDS.filter(r => r.recommended).map(r =>
      '<span class="chip" data-id="' + esc(r.id) + '">' + esc(r.id) + '</span>'
    ).join('');

    $('quickChips').addEventListener('click', e => {
      const chip = e.target.closest('.chip');
      if (!chip) return;
      sel.value = chip.dataset.id;
      onRecordChange();
    });
    sel.addEventListener('change', onRecordChange);
  }

  function currentRecord() {
    const id = $('recSel').value;
    return RECORDS.find(r => r.id === id) || null;
  }

  function onRecordChange() {
    state.record = currentRecord();
    state.result = null;
    state.selected = -1;
    $('resultArea').innerHTML = '';

    const r = state.record;
    if (!r) return;

    // 记录信息面板
    $('iId').textContent = r.id;
    $('iDur').textContent = r.duration_sec + ' s';
    $('iBeats').textContent = num(r.n_beats);
    $('iSplit').textContent = r.split;
    $('recNote').textContent = r.note || '';

    const total = Object.values(r.class_counts).reduce((a, b) => a + b, 0) || 1;
    $('iStack').innerHTML = CLASS_ORDER.map(c => {
      const v = r.class_counts[c] || 0;
      if (!v) return '';
      return '<span style="width:' + (v / total * 100).toFixed(2) +
             '%;background:var(--c-' + c + ')" title="' + c + ': ' + v + '">' +
             (v / total > 0.08 ? c : '') + '</span>';
    }).join('');

    // 起始时间滑块上限 = 总时长 - 时长
    const maxStart = Math.max(0, r.duration_sec - Number($('durRange').value));
    $('startRange').max = maxStart.toFixed(1);
    if (Number($('startRange').value) > maxStart) $('startRange').value = maxStart;
    $('startHint').textContent = '该记录总时长 ' + r.duration_sec +
      ' s，可选取 0 ~ ' + maxStart.toFixed(1) + ' s';

    updateLabels();
    $('analyzeBtn').disabled = false;
  }

  function updateLabels() {
    $('startVal').textContent = Number($('startRange').value).toFixed(1) + 's';
    $('durVal').textContent = Number($('durRange').value) + 's';
  }

  /* ------------------------------------------------------------ 波形预览 */
  async function doPreview() {
    const r = state.record;
    if (!r) return;
    const start = Number($('startRange').value);
    const dur = Number($('durRange').value);

    $('previewBtn').disabled = true;
    $('previewBtn').textContent = '加载中…';
    try {
      const data = await api('/api/preview?record_id=' + encodeURIComponent(r.id) +
                             '&start=' + start + '&duration=' + dur);
      state.preview = data;
      state.selected = -1;
      $('waveTitle').textContent = '波形预览 · 记录 ' + data.record_id;
      $('waveSub').textContent = '起始 ' + data.start_sec + ' s · 时长 ' + data.duration_sec +
        ' s · 窗内检出 ' + data.n_beats_in_window + ' 个心搏（虚线为专家标注位置）';
      drawPreviewStrip();
    } catch (e) {
      toast(e.message);
    } finally {
      $('previewBtn').disabled = false;
      $('previewBtn').textContent = '① 预览波形';
    }
  }

  function drawPreviewStrip() {
    const d = state.preview;
    if (!d) return;
    const beats = (d.beat_marks || []).map((m, i) => ({
      sample: m.sample, pred: m.aami, index: i + 1
    }));
    ECGWave.renderStrip($('waveCanvas'), {
      signal: d.signal, fs: d.fs, beats: beats, showCam: false, height: 340
    });
    $('waveFoot').innerHTML =
      '<span class="item"><i class="dot" style="background:#3ddc97"></i>心电波形（已 0.5–45 Hz 带通滤波）</span>' +
      '<span class="item"><i class="dot" style="background:#94a3b8"></i>虚线 = 心电专家标注的 R 峰位置</span>';
  }

  /* ------------------------------------------------------------ 分析步骤动画 */
  const STEPS = [
    ['读取心电信号与专家标注', '按记录编号载入信号，定位窗口内 R 峰'],
    ['带通滤波与心搏切分', '0.5–45 Hz Butterworth 滤波，R 峰前后 0.25s / 0.45s 切分'],
    ['1D-CNN 逐搏前向推理', '对窗口内每个心搏输出 AAMI 五类概率分布'],
    ['Grad-CAM 显著性计算', '反向传播求特征图梯度，加权得到时间重要性曲线'],
    ['生成结构化分析报告', '统计异常搏动占比并给出提示等级']
  ];

  function resetSteps() {
    $('stepList').innerHTML = STEPS.map((s, i) =>
      '<li data-i="' + i + '"><span class="ic">' + (i + 1) + '</span>' +
      '<div class="tx"><strong>' + esc(s[0]) + '</strong>' +
      '<div class="sub">' + esc(s[1]) + '</div></div></li>'
    ).join('');
    $('progressCard').style.display = '';
  }

  function markStep(i, cls) {
    const li = $('stepList').querySelector('li[data-i="' + i + '"]');
    if (li) li.className = cls;
  }

  function animateSteps() {
    return new Promise(resolve => {
      let i = 0;
      const tick = () => {
        if (i > 0) markStep(i - 1, 'done');
        if (i >= STEPS.length) return resolve();
        markStep(i, 'run');
        i++;
        setTimeout(tick, 380);
      };
      tick();
    });
  }

  /* ------------------------------------------------------------ 执行分析 */
  async function doAnalyze() {
    const r = state.record;
    if (!r) return;

    const start = Number($('startRange').value);
    const dur = Number($('durRange').value);
    const withCam = $('camChk').checked;

    $('analyzeBtn').disabled = true;
    $('analyzeBtn').textContent = '分析中…';
    $('resultArea').innerHTML = '';
    resetSteps();

    const stepsPromise = animateSteps();

    try {
      const req = api('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          record_id: r.id, start_sec: start, duration_sec: dur, with_cam: withCam
        })
      });
      const [data] = await Promise.all([req, stepsPromise]);
      STEPS.forEach((_, i) => markStep(i, 'done'));
      state.result = data;
      state.selected = data.beats.length ? 0 : -1;
      renderResult(data);
      setTimeout(() => { $('progressCard').style.display = 'none'; }, 700);
    } catch (e) {
      toast(e.message);
      $('progressCard').style.display = 'none';
    } finally {
      $('analyzeBtn').disabled = false;
      $('analyzeBtn').textContent = '② 开始分析';
    }
  }

  /* ------------------------------------------------------------ 结果渲染 */
  function renderResult(d) {
    d.classes.forEach(c => { CLASS_NAME[c.code] = c.name; CLASS_DESC[c.code] = c.desc; });
    const s = d.summary;
    const risk = s.risk_level;

    const parts = [];

    /* --- 概览 --- */
    parts.push(
      '<div class="card">' +
        '<div class="card-head">' +
          '<div><h2>分析结果</h2><p class="card-sub">记录 ' + esc(d.record_id) +
          ' · 起始 ' + d.start_sec + ' s · 时长 ' + d.duration_sec +
          ' s · 共 ' + s.n_beats + ' 个心搏</p></div>' +
          '<div class="flex-between" style="gap:8px">' +
            '<input type="text" id="saveTitle" placeholder="报告标题（可留空）" style="width:220px">' +
            '<button class="btn btn-primary btn-sm" id="saveBtn">保存报告</button>' +
          '</div>' +
        '</div>' +
        '<div class="risk ' + risk.code + '">' +
          '<div class="t">' + esc(risk.label) + '</div>' +
          '<div class="d">' + esc(risk.desc) +
            ' 本段异常搏动占比 <strong>' + pct(risk.abnormal_ratio) + '</strong>，' +
            '其中室性/融合搏动占比 <strong>' + pct(risk.ventricular_ratio) + '</strong>。' +
          '</div>' +
          // 医学相关结果必须紧邻展示免责声明，避免用户误当作诊断结论
          '<div class="d small" style="margin-top:8px;opacity:.92">' +
            '⚠ 以上结果由机器学习模型自动生成，仅用于课程项目演示与辅助分析，' +
            '不构成医疗诊断依据，不能用于任何临床决策。如有健康问题请及时就医。' +
          '</div>' +
        '</div>' +
        '<div class="grid grid-4" style="margin-top:18px">' +
          stat('分析心搏数', s.n_beats, '') +
          stat('异常搏动数', s.abnormal_count, 'warn') +
          stat('异常搏动占比', pct(s.abnormal_ratio), risk.code === 'low' ? 'ok' : 'danger') +
          stat('平均置信度', pct(s.mean_confidence), 'accent') +
        '</div>' +
        '<div class="alert alert-info small" style="margin:16px 0 0">' +
          '<span>ℹ</span><div>本窗口内模型判定与心电专家标注的一致率为 <strong>' +
          pct(s.agreement) + '</strong>（' +
          d.beats.filter(b => b.agree).length + ' / ' + s.n_beats +
          '）。一致率用于横向对照模型表现，不代表临床准确度。</div>' +
        '</div>' +
        // 训练集记录模型见过，高一致率不能当作泛化能力——必须显式说明
        (d.in_training_set
          ? '<div class="alert alert-warn small" style="margin:10px 0 0">' +
              '<span>⚠</span><div><strong>本记录属于训练集（' + esc(d.split || 'DS1') +
              '），模型在训练时已见过该患者的心搏。</strong>' +
              '因此上方的逐搏一致率<strong>明显偏高，不能作为模型泛化能力的证据</strong>。' +
              '真实泛化水平请参考「关于」页的跨患者测试集指标' +
              '（整体准确率 93.35%，但 Macro-F1 仅 0.504，F 类 F1 为 0）。' +
              '建议同时选择测试集记录（100 / 222 / 233）作对照观察。</div></div>'
          : '<div class="alert alert-ok small" style="margin:10px 0 0">' +
              '<span>✓</span><div>本记录属于<strong>测试集（' + esc(d.split || 'DS2') +
              '）</strong>，训练全程未接触过该患者，此处的对照结果可反映跨患者泛化表现。</div></div>'
        ) +
      '</div>'
    );

    /* --- 标注波形 --- */
    parts.push(
      '<div class="card">' +
        '<div class="card-head">' +
          '<div><h3>逐搏分类标注</h3>' +
          '<p class="card-sub">圆点颜色表示模型对该心搏的分类结果，虚线为 R 峰位置；' +
          '点击任一搏动可查看其详情' + (d.beats[0] && d.beats[0].cam ? '，琥珀色区域为 Grad-CAM 关注区间' : '') +
          '</p></div>' +
        '</div>' +
        '<div class="wave-box"><canvas id="resCanvas"></canvas>' +
        '<div class="wave-tip" id="resTip"></div></div>' +
        '<div class="wave-legend" id="resLegend"></div>' +
      '</div>'
    );

    /* --- 分布 + 单搏详情 --- */
    parts.push(
      '<div class="grid grid-2">' +
        '<div class="card">' +
          '<h3>心律类型构成</h3>' +
          '<div class="stack">' + CLASS_ORDER.map(c => {
            const v = s.counts[c] || 0;
            if (!v) return '';
            return '<span style="width:' + (v / s.n_beats * 100).toFixed(2) +
                   '%;background:var(--c-' + c + ')" title="' + c + ': ' + v + '">' +
                   (v / s.n_beats > 0.09 ? v : '') + '</span>';
          }).join('') + '</div>' +
          CLASS_ORDER.map(c => {
            const v = s.counts[c] || 0;
            const w = (v / s.n_beats * 100);
            return '<div class="prob-row">' +
              '<span class="lbl"><span class="badge badge-' + c + '">' + c + '</span> ' +
              esc(CLASS_NAME[c]) + '</span>' +
              '<span class="bar"><i style="width:' + w.toFixed(1) + '%;background:var(--c-' + c + ')"></i></span>' +
              '<span class="val">' + v + ' 搏</span></div>';
          }).join('') +
        '</div>' +

        '<div class="card">' +
          '<div class="card-head"><h3 style="margin:0">单搏详情</h3>' +
          '<span class="badge badge-mute" id="beatNav">—</span></div>' +
          '<div class="wave-box" style="padding:8px"><canvas id="beatCanvas"></canvas></div>' +
          '<div id="beatInfo" style="margin-top:14px"></div>' +
        '</div>' +
      '</div>'
    );

    /* --- 明细表 --- */
    parts.push(
      '<div class="card">' +
        '<h3>逐搏明细</h3>' +
        '<div class="table-wrap" style="max-height:420px;overflow-y:auto">' +
        '<table><thead><tr>' +
          '<th>#</th><th>时间</th><th>模型判定</th><th>置信度</th>' +
          '<th>专家标注</th><th>是否一致</th><th>五类概率分布</th>' +
        '</tr></thead><tbody id="beatRows">' +
        d.beats.map(b => {
          const rows = CLASS_ORDER.map(c =>
            '<div class="prob-row" style="grid-template-columns:22px 1fr 44px;margin-bottom:2px">' +
            '<span class="lbl mono" style="font-size:.7rem">' + c + '</span>' +
            '<span class="bar" style="height:5px"><i style="width:' + (b.probs[c] * 100).toFixed(1) +
            '%;background:var(--c-' + c + ')"></i></span>' +
            '<span class="val" style="font-size:.68rem">' + (b.probs[c] * 100).toFixed(1) + '%</span></div>'
          ).join('');
          return '<tr data-i="' + (b.index - 1) + '">' +
            '<td class="mono">' + b.index + '</td>' +
            '<td class="mono">' + b.time_sec.toFixed(2) + ' s</td>' +
            '<td><span class="badge badge-' + b.pred + '">' + b.pred + ' ' + esc(b.pred_name) + '</span></td>' +
            '<td class="num">' + pct(b.confidence) + '</td>' +
            '<td><span class="badge badge-' + b.expert + '">' + b.expert + '</span></td>' +
            '<td>' + (b.agree ? '<span class="badge badge-ok">一致</span>'
                              : '<span class="badge badge-warn">不一致</span>') + '</td>' +
            '<td style="min-width:190px">' + rows + '</td></tr>';
        }).join('') +
        '</tbody></table></div>' +
      '</div>'
    );

    $('resultArea').innerHTML = parts.join('');

    // 图例
    const used = CLASS_ORDER.filter(c => s.counts[c] > 0);
    $('resLegend').innerHTML = used.map(c =>
      '<span class="item"><i class="dot" style="background:var(--c-' + c + ')"></i>' +
      c + ' ' + esc(CLASS_NAME[c]) + ' <span class="mono muted">' + s.counts[c] + '</span></span>'
    ).join('') + (d.beats[0] && d.beats[0].cam
      ? '<span class="item"><i class="dot" style="background:#f59e0b"></i>Grad-CAM 关注区间</span>' : '');

    drawResultStrip();
    renderBeatDetail(state.selected);
    bindResultEvents();
  }

  function stat(k, v, cls) {
    return '<div class="stat ' + (cls || '') + '"><div class="k">' + k + '</div>' +
           '<div class="v">' + v + '</div></div>';
  }

  function drawResultStrip() {
    const d = state.result;
    if (!d) return;
    ECGWave.renderStrip($('resCanvas'), {
      signal: d.signal, fs: d.fs, beats: d.beats, selected: state.selected,
      showCam: !!(d.beats[0] && d.beats[0].cam), height: 340,
      onSelect: i => { state.selected = i; drawResultStrip(); renderBeatDetail(i); highlightRow(i); },
      onHover: (i, ev) => {
        const tip = $('resTip');
        if (i < 0) { tip.style.display = 'none'; return; }
        const b = d.beats[i];
        tip.innerHTML = '第 ' + b.index + ' 搏 · ' + b.time_sec.toFixed(2) + ' s<br>' +
          '<span style="color:' + ECGWave.CLASS_COLOR[b.pred] + '">' + b.pred + ' ' +
          esc(b.pred_name) + '</span> · 置信度 ' + pct(b.confidence);
        tip.style.display = 'block';
        const box = $('resCanvas').parentElement.getBoundingClientRect();
        tip.style.left = Math.min(ev.clientX - box.left + 12, box.width - 190) + 'px';
        tip.style.top = (ev.clientY - box.top - 10) + 'px';
      }
    });
  }

  function highlightRow(i) {
    const rows = document.querySelectorAll('#beatRows tr');
    rows.forEach(r => r.classList.remove('sel'));
    if (rows[i]) {
      rows[i].classList.add('sel');
      rows[i].scrollIntoView({ block: 'nearest' });
    }
  }

  function renderBeatDetail(i) {
    const d = state.result;
    if (!d || i < 0 || !d.beats[i]) return;
    const b = d.beats[i];

    $('beatNav').textContent = '第 ' + b.index + ' / ' + d.beats.length + ' 搏';

    // 还原该搏的原始片段：由整段信号按 R 峰位置截取
    const raw = d.signal.slice(b.sample - 90, b.sample + 162);
    if (raw.length === 252) {
      ECGWave.renderBeat($('beatCanvas'), {
        beat: raw, cam: b.cam || null, classes: d.classes, predIdx: CLASS_ORDER.indexOf(b.pred),
        height: 190
      });
    }

    $('beatInfo').innerHTML =
      '<div class="flex-between" style="margin-bottom:12px">' +
        '<span class="badge badge-' + b.pred + '" style="font-size:.9rem;padding:5px 14px">' +
          b.pred + ' · ' + esc(b.pred_name) + '</span>' +
        (b.agree ? '<span class="badge badge-ok">与专家标注一致</span>'
                 : '<span class="badge badge-warn">专家标注为 ' + b.expert + ' · ' + esc(b.expert_name) + '</span>') +
      '</div>' +
      '<p class="small muted">' + esc(CLASS_DESC[b.pred] || '') + '</p>' +
      renderRhythm(b) +
      '<div class="small muted" style="margin:12px 0 8px">模型对该搏的五类概率分布：</div>' +
      CLASS_ORDER.map(c =>
        '<div class="prob-row">' +
          '<span class="lbl"><span class="badge badge-' + c + '">' + c + '</span></span>' +
          '<span class="bar"><i style="width:' + (b.probs[c] * 100).toFixed(1) +
            '%;background:var(--c-' + c + ')"></i></span>' +
          '<span class="val">' + (b.probs[c] * 100).toFixed(1) + '%</span>' +
        '</div>'
      ).join('') +
      (b.cam ? '<div class="alert alert-info small" style="margin-top:14px"><span>🔍</span>' +
        '<div>琥珀色区域为 Grad-CAM 显著性：颜色越深表示该时刻对模型判断的贡献越大。' +
        '通常集中在 QRS 波群附近——与临床依据 QRS 形态判别异位搏动的思路一致。</div></div>' : '');
  }

  /* 节律上下文由 static/js/rhythm.js 提供，分析页与历史详情页共用同一实现 */
  function renderRhythm(b) {
    return window.ECGRhythm ? ECGRhythm.render(b) : '';
  }

  function bindResultEvents() {
    const rows = document.querySelectorAll('#beatRows tr');
    rows.forEach(r => r.addEventListener('click', () => {
      const i = Number(r.dataset.i);
      state.selected = i;
      drawResultStrip();
      renderBeatDetail(i);
      highlightRow(i);
    }));

    const btn = $('saveBtn');
    if (btn) btn.addEventListener('click', async () => {
      const title = ($('saveTitle').value || '').trim();
      btn.disabled = true; btn.textContent = '保存中…';
      try {
        const r = state.record;
        const res = await api('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            record_id: r.id,
            start_sec: Number($('startRange').value),
            duration_sec: Number($('durRange').value),
            with_cam: $('camChk').checked,
            save: true, title: title
          })
        });
        btn.textContent = '✓ 已保存';
        toast('报告已保存到历史记录（编号 #' + res.saved_id + '），可在「历史记录」页查看。', 'ok');
        setTimeout(() => { btn.disabled = false; btn.textContent = '保存报告'; }, 2200);
      } catch (e) {
        toast(e.message);
        btn.disabled = false; btn.textContent = '保存报告';
      }
    });
  }

  /* ------------------------------------------------------------ 事件绑定 */
  function bind() {
    $('startRange').addEventListener('input', updateLabels);
    $('durRange').addEventListener('input', () => {
      updateLabels();
      // 时长变化会影响起始时间上限
      const r = state.record;
      if (!r) return;
      const maxStart = Math.max(0, r.duration_sec - Number($('durRange').value));
      $('startRange').max = maxStart.toFixed(1);
      if (Number($('startRange').value) > maxStart) $('startRange').value = maxStart;
      $('startHint').textContent = '该记录总时长 ' + r.duration_sec +
        ' s，可选取 0 ~ ' + maxStart.toFixed(1) + ' s';
      updateLabels();
    });

    $('previewBtn').addEventListener('click', doPreview);
    $('analyzeBtn').addEventListener('click', doAnalyze);

    let rt;
    window.addEventListener('resize', () => {
      clearTimeout(rt);
      rt = setTimeout(() => {
        if (state.result) { drawResultStrip(); renderBeatDetail(state.selected); }
        else if (state.preview) { drawPreviewStrip(); }
      }, 180);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initRecords();
    bind();
    onRecordChange();
    doPreview();          // 进入页面即自动预览第一段波形
  });
})();
