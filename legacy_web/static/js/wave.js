/* ==========================================================================
   心电波形渲染引擎（纯 Canvas 实现，无第三方依赖）
   两种模式：
     renderStrip —— 连续心电条带，叠加逐搏分类标注与 Grad-CAM 热区
     renderBeat  —— 单心搏放大视图，叠加 Grad-CAM 曲线与五类概率
   ========================================================================== */
(function (global) {
  'use strict';

  const CLASS_COLOR = {
    N: '#059669', S: '#d97706', V: '#dc2626', F: '#7c3aed', Q: '#64748b'
  };

  const THEME = {
    bg:       '#0d1b2e',
    grid:     'rgba(90,130,190,.16)',
    gridMajor:'rgba(110,155,215,.30)',
    axis:     'rgba(150,180,220,.45)',
    text:     '#8ea8c8',
    signal:   '#3ddc97',
    cam:      '61,220,151',      // 备用
    camColor: '245,158,11',
    select:   'rgba(96,165,250,.16)'
  };

  function setupCanvas(canvas, cssHeight) {
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.parentElement.clientWidth - 24 || 800;
    const cssH = cssHeight;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    return { ctx, W: cssW, H: cssH };
  }

  function niceStep(range, target) {
    const raw = range / target;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
    return step * mag;
  }

  /* ------------------------------------------------------------------ 连续条带 */
  function renderStrip(canvas, opts) {
    const {
      signal, fs, beats = [], selected = -1,
      showCam = false, onHover = null, onSelect = null
    } = opts;

    const { ctx, W, H } = setupCanvas(canvas, opts.height || 340);
    const padL = 48, padR = 14, padT = 30, padB = 26;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const n = signal.length;
    if (!n) return null;

    // 值域
    let vMin = Math.min.apply(null, signal), vMax = Math.max.apply(null, signal);
    const span = (vMax - vMin) || 1;
    vMin -= span * 0.12; vMax += span * 0.12;

    const X = i => padL + (i / (n - 1)) * plotW;
    const Y = v => padT + (1 - (v - vMin) / (vMax - vMin)) * plotH;

    // 背景
    ctx.fillStyle = THEME.bg;
    ctx.fillRect(0, 0, W, H);

    // 网格：纵向按时间
    const totalSec = n / fs;
    const secStep = niceStep(totalSec, 10);
    ctx.lineWidth = 1;
    ctx.font = '11px ui-monospace, Consolas, monospace';
    ctx.textAlign = 'center';
    for (let t = 0; t <= totalSec + 1e-6; t += secStep) {
      const x = X(Math.min(t * fs, n - 1));
      ctx.strokeStyle = THEME.grid;
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
      ctx.fillStyle = THEME.text;
      ctx.fillText(t.toFixed(secStep < 1 ? 1 : 0) + 's', x, H - 9);
    }
    // 横向按幅值
    const mVStep = niceStep(vMax - vMin, 5);
    ctx.textAlign = 'right';
    for (let v = Math.ceil(vMin / mVStep) * mVStep; v <= vMax; v += mVStep) {
      const y = Y(v);
      ctx.strokeStyle = Math.abs(v) < 1e-9 ? THEME.gridMajor : THEME.grid;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
      ctx.fillStyle = THEME.text;
      ctx.fillText(v.toFixed(1), padL - 7, y + 4);
    }

    // Grad-CAM 热区（曲线下方琥珀色带，透明度随显著性变化）
    if (showCam && beats.length && beats[0].cam) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(padL, padT, plotW, plotH);
      ctx.clip();
      for (let px = 0; px < plotW; px++) {
        const idx = Math.round((px / plotW) * (n - 1));
        let bestCam = 0;
        for (let b = 0; b < beats.length; b++) {
          const cam = beats[b].cam;
          if (!cam) continue;
          const local = idx - (beats[b].sample - 90);
          if (local >= 0 && local < cam.length && cam[local] > bestCam) bestCam = cam[local];
        }
        if (bestCam > 0.12) {
          const x = padL + px;
          const yv = Y(signal[idx]);
          ctx.fillStyle = 'rgba(' + THEME.camColor + ',' + (bestCam * 0.42).toFixed(3) + ')';
          ctx.fillRect(x, yv, 1, padT + plotH - yv);
        }
      }
      ctx.restore();
    }

    // 选中搏动高亮带
    if (selected >= 0 && beats[selected]) {
      const b = beats[selected];
      const half = 130;
      const x0 = X(Math.max(0, b.sample - half));
      const x1 = X(Math.min(n - 1, b.sample + half));
      ctx.fillStyle = THEME.select;
      ctx.fillRect(x0, padT, x1 - x0, plotH);
    }

    // 基线
    ctx.strokeStyle = THEME.axis;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, Y(0)); ctx.lineTo(padL + plotW, Y(0)); ctx.stroke();

    // 心电波形
    ctx.strokeStyle = THEME.signal;
    ctx.lineWidth = 1.6;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = X(i), y = Y(signal[i]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 逐搏标注：顶部标记 + 竖直虚线
    beats.forEach(function (b, i) {
      const x = X(b.sample);
      const color = CLASS_COLOR[b.pred] || '#94a3b8';
      const isSel = i === selected;

      ctx.strokeStyle = color;
      ctx.globalAlpha = isSel ? 0.95 : 0.42;
      ctx.lineWidth = isSel ? 1.8 : 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      // 顶部圆点 + 类别字母
      const r = isSel ? 9 : 7;
      ctx.beginPath();
      ctx.arc(x, padT - 13, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      if (isSel) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke(); }

      ctx.fillStyle = '#fff';
      ctx.font = 'bold ' + (isSel ? 10 : 9) + 'px ui-monospace, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(b.pred, x, padT - 12);
      ctx.textBaseline = 'alphabetic';
    });

    /* ---------------------------------------------------- 交互 */
    const hitTest = function (ev) {
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      let best = -1, bestD = 22;
      beats.forEach(function (b, i) {
        const d = Math.abs(X(b.sample) - mx);
        if (d < bestD) { bestD = d; best = i; }
      });
      return best;
    };

    if (onSelect) {
      canvas.style.cursor = 'pointer';
      canvas.onclick = function (ev) {
        const i = hitTest(ev);
        if (i >= 0) onSelect(i);
      };
    }
    if (onHover) {
      canvas.onmousemove = function (ev) {
        const i = hitTest(ev);
        onHover(i, ev);
        canvas.style.cursor = i >= 0 ? 'pointer' : 'default';
      };
      canvas.onmouseleave = function () { onHover(-1, null); };
    }

    return { X: X, Y: Y, padL: padL, padT: padT, plotW: plotW, plotH: plotH };
  }

  /* ------------------------------------------------------------------ 单心搏 */
  function renderBeat(canvas, opts) {
    const { beat, cam, classes, predIdx, preSamples = 90 } = opts;
    const { ctx, W, H } = setupCanvas(canvas, opts.height || 200);
    const padL = 14, padR = 14, padT = 16, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const n = beat.length;

    let vMin = Math.min.apply(null, beat), vMax = Math.max.apply(null, beat);
    const span = (vMax - vMin) || 1;
    vMin -= span * 0.15; vMax += span * 0.15;

    const X = i => padL + (i / (n - 1)) * plotW;
    const Y = v => padT + (1 - (v - vMin) / (vMax - vMin)) * plotH;

    ctx.fillStyle = THEME.bg;
    ctx.fillRect(0, 0, W, H);

    // 网格
    ctx.strokeStyle = THEME.grid;
    ctx.lineWidth = 1;
    for (let i = 0; i < n; i += 25) {
      const x = X(i);
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
    }
    ctx.beginPath(); ctx.moveTo(padL, Y(0)); ctx.lineTo(padL + plotW, Y(0)); ctx.stroke();

    // R 峰参考线
    ctx.strokeStyle = 'rgba(248,113,113,.55)';
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(X(preSamples), padT); ctx.lineTo(X(preSamples), padT + plotH); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#f87171';
    ctx.font = '10px ui-monospace, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('R', X(preSamples), padT - 4);

    // Grad-CAM 热区
    if (cam && cam.length === n) {
      for (let px = 0; px < plotW; px++) {
        const idx = Math.round((px / plotW) * (n - 1));
        const c = cam[idx] || 0;
        if (c > 0.1) {
          const yv = Y(beat[idx]);
          ctx.fillStyle = 'rgba(' + THEME.camColor + ',' + (c * 0.45).toFixed(3) + ')';
          ctx.fillRect(padL + px, yv, 1, padT + plotH - yv);
        }
      }
    }

    // 波形
    const color = CLASS_COLOR[(classes[predIdx] || {}).code] || THEME.signal;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = X(i), y = Y(beat[i]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 时间轴刻度
    ctx.fillStyle = THEME.text;
    ctx.font = '10px ui-monospace, monospace';
    ctx.textAlign = 'left';
    ctx.fillText('-0.25s', padL, H - 7);
    ctx.textAlign = 'right';
    ctx.fillText('+0.45s', padL + plotW, H - 7);
  }

  global.ECGWave = {
    renderStrip: renderStrip,
    renderBeat: renderBeat,
    CLASS_COLOR: CLASS_COLOR
  };
})(window);
