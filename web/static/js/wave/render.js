/* 心电图绘制（Canvas 2D，无第三方依赖）。
 *
 * 分两层画：
 *   base    —— 网格、标注、Grad-CAM、波形。只在"数据/视图/选中"变化时重绘。
 *   overlay —— 悬停十字线与读数。跟随指针高频重绘。
 *
 * 为什么分两层：单层方案在 pointermove（可达 120Hz）下每次都要重画上万个
 * 采样点，会明显掉帧。桌面版没有这个问题（Qt 的重绘代价与事件频率不同），
 * 这是 Web 端必须额外处理的点。
 */
import { CLASS_COLOR } from '../format.js';
import { decimationStep, makeYScale, viewBounds, xOf } from './viewport.js';

export const THEME = {
  bg: '#0d1b2e',
  grid: 'rgba(90,130,190,.16)',
  gridMajor: 'rgba(110,155,215,.30)',
  axis: 'rgba(150,180,220,.45)',
  text: '#8ea8c8',
  signal: '#3ddc97',
  camColor: '245,158,11',
  select: 'rgba(96,165,250,.16)',
};

/** CAM 面积图的最高处占绘图区高度的比例（与桌面版一致） */
export const CAM_MAX_RATIO = 0.42;

/** 前后采样点数：与后端 PRE_SAMPLES / POST_SAMPLES 对应 */
export const PRE_SAMPLES = 90;
export const POST_SAMPLES = 162;
export const BEAT_LEN = PRE_SAMPLES + POST_SAMPLES;

export function makeGeom(W, H, opts = {}) {
  const padL = opts.padL ?? 54;
  const padR = opts.padR ?? 16;
  const padT = opts.padT ?? 34;
  const padB = opts.padB ?? 28;
  return { padL, padR, padT, padB, plotW: W - padL - padR, plotH: H - padT - padB };
}

/** 按 DPR 调整画布尺寸并重置变换。返回 CSS 像素下的尺寸。 */
export function setupCanvas(canvas, cssW, cssH) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(cssW));
  const h = Math.max(1, Math.round(cssH));
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  // 注意：给 canvas.width 赋值会清空画布并重置变换，
  // 因此 setTransform 必须放在尺寸设定之后、每次绘制之前。
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, W: w, H: h };
}

/** 取 1 / 2 / 5 × 10ⁿ 中不小于目标值的"好看"刻度 */
export function niceStep(range, target) {
  if (!(range > 0) || !(target > 0)) return 1;
  const raw = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * mag;
}

function drawGrid(ctx, geom, state, yOf) {
  const { padL, padT, plotW, plotH } = geom;
  const { vp, signal, fs } = state;

  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT, plotW, plotH);
  ctx.clip();

  ctx.lineWidth = 1;
  ctx.font = '11px ui-monospace, Consolas, monospace';

  // 纵向：按时间。刻度值取绝对时间（窗口起点 + 窗口内偏移），
  // 与十字线读数保持同一坐标系。
  const startSec = state.startSec || 0;
  const secStep = niceStep((vp.b - vp.a) / fs, Math.max(4, plotW / 110));
  const digits = secStep < 1 ? 1 : 0;

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const firstTick = Math.ceil((startSec + vp.a / fs) / secStep) * secStep;
  const lastTick = startSec + vp.b / fs;
  for (let t = firstTick; t <= lastTick + 1e-9; t += secStep) {
    const idx = (t - startSec) * fs;
    const x = xOf(vp, idx, geom);
    if (x < padL - 0.5 || x > padL + plotW + 0.5) continue;
    ctx.strokeStyle = THEME.grid;
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, padT + plotH);
    ctx.stroke();
    ctx.fillStyle = THEME.text;
    ctx.fillText(t.toFixed(digits) + 's', x, padT + plotH + 6);
  }

  // 横向：按幅值
  const { lo, hi } = viewBounds(vp, signal);
  const mvStep = niceStep(hi - lo, 5);
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let v = Math.ceil(lo / mvStep) * mvStep; v <= hi; v += mvStep) {
    const y = yOf(v);
    if (y < padT - 0.5 || y > padT + plotH + 0.5) continue;
    ctx.strokeStyle = Math.abs(v) < 1e-9 ? THEME.gridMajor : THEME.grid;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + plotW, y);
    ctx.stroke();
    ctx.fillStyle = THEME.text;
    ctx.fillText(v.toFixed(Math.abs(mvStep) < 1 ? 2 : 1), padL - 8, y);
  }
  ctx.restore();
}

/**
 * 异常搏动底纹与选中高亮。
 * 非 N 类铺一层很淡的类别色——用于一眼看出"这一段异常搏动密集"。
 */
function drawBeatBands(ctx, geom, state, xOfIdx) {
  const { padL, padT, plotW, plotH } = geom;
  const { beats, selected } = state;

  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT, plotW, plotH);
  ctx.clip();

  beats.forEach((b, i) => {
    if (i === selected) return;
    if (b.pred === 'N') return;
    const x0 = xOfIdx(Math.max(b.sample - PRE_SAMPLES, 0));
    const x1 = xOfIdx(b.sample + POST_SAMPLES);
    if (x1 < padL || x0 > padL + plotW) return;
    ctx.fillStyle = (CLASS_COLOR[b.pred] || '#94a3b8') + '14';   // 约 8% 不透明
    ctx.fillRect(x0, padT, Math.max(x1 - x0, 1), plotH);
  });

  if (selected >= 0 && beats[selected]) {
    const b = beats[selected];
    const x0 = xOfIdx(Math.max(b.sample - PRE_SAMPLES, 0));
    const x1 = xOfIdx(b.sample + POST_SAMPLES);
    ctx.fillStyle = THEME.select;
    ctx.fillRect(x0, padT, Math.max(x1 - x0, 1), plotH);
  }
  ctx.restore();
}

/**
 * Grad-CAM 热区。
 *
 * 只画**当前选中搏动**的显著性，并以填充面积图的形式呈现（从绘图区底部
 * 向上生长，高度正比于该点的显著性）。上一版 Web 版用的是"逐像素 1px 竖条
 * 取全窗并集"，既看不出属于哪一搏，也在缩放时丢失对应关系。
 *
 * cam 与该搏自身的 252 个采样点严格对齐，因此横坐标按
 * [sample - PRE_SAMPLES, sample + POST_SAMPLES] 映射。
 */
function drawCam(ctx, geom, state, xOfIdx) {
  const { padL, padT, plotW, plotH } = geom;
  const { beats, selected, showCam } = state;
  if (!showCam || selected < 0) return;

  const beat = beats[selected];
  const cam = beat && beat.cam;
  if (!cam || !cam.length) return;

  const base = Math.max(beat.sample - PRE_SAMPLES, 0);
  const span = beat.sample + POST_SAMPLES - base;

  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT, plotW, plotH);
  ctx.clip();

  const bottom = padT + plotH;
  ctx.beginPath();
  ctx.moveTo(xOfIdx(base), bottom);
  for (let i = 0; i < cam.length; i++) {
    const x = xOfIdx(base + i);
    const h = plotH * CAM_MAX_RATIO * Math.max(0, Math.min(1, cam[i]));
    ctx.lineTo(x, bottom - h);
  }
  ctx.lineTo(xOfIdx(base + span), bottom);
  ctx.closePath();
  ctx.fillStyle = `rgba(${THEME.camColor},.20)`;
  ctx.fill();
  ctx.strokeStyle = `rgba(${THEME.camColor},.75)`;
  ctx.lineWidth = 1.4;
  ctx.stroke();

  ctx.restore();
}

function drawSignal(ctx, geom, state, xOfIdx, yOf) {
  const { padL, padT, plotW, plotH } = geom;
  const { vp, signal } = state;
  const n = signal.length;

  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT, plotW, plotH);
  ctx.clip();

  // 基线（0 mV）
  const y0 = yOf(0);
  if (y0 >= padT && y0 <= padT + plotH) {
    ctx.strokeStyle = THEME.axis;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, y0);
    ctx.lineTo(padL + plotW, y0);
    ctx.stroke();
  }

  const i0 = Math.max(0, Math.floor(vp.a) - 1);
  const i1 = Math.min(n - 1, Math.ceil(vp.b) + 1);
  const step = decimationStep(vp, plotW);

  ctx.strokeStyle = THEME.signal;
  ctx.lineWidth = 1.6;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  let started = false;
  for (let i = i0; i <= i1; i += step) {
    const x = xOfIdx(i);
    const y = yOf(signal[i]);
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  }
  // 抽稀可能跳过最后一个可见点，补上以免右端提前收线
  if (started && (i1 - i0) % step !== 0) {
    ctx.lineTo(xOfIdx(i1), yOf(signal[i1]));
  }
  ctx.stroke();
  ctx.restore();
}

function drawBeatMarks(ctx, geom, state, xOfIdx) {
  const { padL, padT, plotW, plotH } = geom;
  const { beats, selected } = state;

  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT - 20, plotW, plotH + 20);
  ctx.clip();

  beats.forEach((b, i) => {
    const x = xOfIdx(b.sample);
    if (x < padL - 10 || x > padL + plotW + 10) return;
    const color = CLASS_COLOR[b.pred] || '#94a3b8';
    const isSel = i === selected;

    ctx.strokeStyle = color;
    ctx.globalAlpha = isSel ? 0.95 : 0.4;
    ctx.lineWidth = isSel ? 1.8 : 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, padT + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;

    // 顶部类别标记
    const r = isSel ? 10 : 8;
    ctx.beginPath();
    ctx.arc(x, padT - 14, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    if (isSel) {
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    ctx.fillStyle = '#fff';
    ctx.font = 'bold ' + (isSel ? 10 : 9) + 'px ui-monospace, monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(b.pred, x, padT - 13);
    ctx.textBaseline = 'alphabetic';
  });
  ctx.restore();
}

/** 重绘底层。返回本次使用的几何参数，供交互层做命中测试。 */
export function drawBase(canvas, state) {
  const { ctx, W, H } = setupCanvas(canvas, state.width, state.height);

  const geom = makeGeom(W, H);
  const bounds = viewBounds(state.vp, state.signal);
  const yOf = makeYScale(bounds, geom);
  const xOfIdx = (i) => xOf(state.vp, i, geom);

  ctx.fillStyle = THEME.bg;
  ctx.fillRect(0, 0, W, H);

  if (!state.signal.length) {
    ctx.fillStyle = THEME.text;
    ctx.font = '13px ui-monospace, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('（暂无波形）', W / 2, H / 2);
    return geom;
  }

  drawGrid(ctx, geom, state, yOf);
  drawBeatBands(ctx, geom, state, xOfIdx);
  drawCam(ctx, geom, state, xOfIdx);
  drawSignal(ctx, geom, state, xOfIdx, yOf);
  drawBeatMarks(ctx, geom, state, xOfIdx);

  return geom;
}

/** 重绘顶层十字线与读数。hover 为 null 时只清空。 */
export function drawOverlay(canvas, state, geom, hover) {
  const cssW = state.width;
  const cssH = state.height;
  const { ctx, W, H } = setupCanvas(canvas, cssW, cssH);

  if (!hover || !state.signal.length) return;

  const { padL, padT, plotW, plotH } = geom;
  const { vp, signal, fs } = state;

  const idx = Math.max(0, Math.min(signal.length - 1, Math.round(hover.idx)));
  const x = xOf(vp, idx, geom);
  if (x < padL || x > padL + plotW) return;

  const bounds = viewBounds(vp, signal);
  const yOf = makeYScale(bounds, geom);
  const y = yOf(signal[idx]);

  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT, plotW, plotH);
  ctx.clip();

  ctx.strokeStyle = 'rgba(190,215,245,.5)';
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(x, padT);
  ctx.lineTo(x, padT + plotH);
  ctx.moveTo(padL, y);
  ctx.lineTo(padL + plotW, y);
  ctx.stroke();
  ctx.setLineDash([]);

  // 交点
  ctx.beginPath();
  ctx.arc(x, y, 3.2, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.fill();
  ctx.restore();

  // 读数：时间用绝对时间（窗口起点 + 窗口内偏移），与网格刻度同一坐标系
  const startSec = state.startSec || 0;
  const t = startSec + idx / fs;
  const text = `${t.toFixed(3)}s  ${signal[idx].toFixed(3)} mV`;

  ctx.font = '11px ui-monospace, Consolas, monospace';
  const tw = ctx.measureText(text).width + 16;
  const th = 22;
  // 靠近右边界时把读数框翻到左侧，避免出界
  let bx = x + 12;
  if (bx + tw > W - 6) bx = x - 12 - tw;
  const by = Math.min(Math.max(y - th - 8, padT), padT + plotH - th);

  ctx.fillStyle = 'rgba(13,27,46,.95)';
  ctx.strokeStyle = '#2c4a72';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(bx, by, tw, th, 7);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = '#e8eefc';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, bx + 8, by + th / 2);
  ctx.textBaseline = 'alphabetic';
}
