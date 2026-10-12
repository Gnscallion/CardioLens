/* 波形视图区间的数学部分（纯函数，不碰 DOM、不依赖 Vue）。
 *
 * 核心模型：视图是一个**采样点区间** `{ a, b }`（浮点），而不是像素区间。
 * 所有坐标换算都经过这对函数：
 *
 *     xOf(vp, idx)  : 采样点 -> 画布 x
 *     idxOf(vp, x)  : 画布 x -> 采样点
 *
 * 缩放与平移只改 `{a, b}`，绘图层永远按当前区间重算。
 * 这正是上一版 Web 版缺失的能力——它的横坐标是写死的
 * `padL + i/(n-1)*plotW`，无法表达"只看这一段"。
 */

/** 滚轮缩放系数。与桌面版一致：向上滚一级放大到 0.82 倍跨度。 */
export const ZOOM_FACTOR = 0.82;

/** 值域上下留白比例（与桌面版一致） */
export const VALUE_PADDING = 0.08;

/**
 * 最窄跨度（采样点）。两条约束取较大者：
 *   - 至少 60 点（约 0.17 秒 @360Hz），再窄就没有判读意义；
 *   - 至少占整段的 1/200，避免长记录放大到极限时跨度为 0 导致除零。
 */
export function minSpan(n) {
  return Math.max(60, n / 200);
}

export function createViewport() {
  return { a: 0, b: 0 };
}

export function resetView(vp, n) {
  vp.a = 0;
  vp.b = n;
  return vp;
}

export function isFullView(vp, n) {
  return vp.a <= 1e-6 && vp.b >= n - 1e-6;
}

/** 夹取到合法范围：跨度在 [minSpan, n] 之间，且不越出 [0, n]。 */
export function clampView(vp, n) {
  if (!(n > 0)) {
    vp.a = 0;
    vp.b = 0;
    return vp;
  }
  const span = Math.min(Math.max(vp.b - vp.a, minSpan(n)), n);
  const a = Math.min(Math.max(vp.a, 0), Math.max(0, n - span));
  vp.a = a;
  vp.b = a + span;
  return vp;
}

export function xOf(vp, idx, geom) {
  const span = vp.b - vp.a;
  if (!(span > 0)) return geom.padL;
  return geom.padL + ((idx - vp.a) / span) * geom.plotW;
}

export function idxOf(vp, x, geom) {
  if (!(geom.plotW > 0)) return vp.a;
  return vp.a + ((x - geom.padL) / geom.plotW) * (vp.b - vp.a);
}

/**
 * 以 anchorIdx 为锚点缩放。
 *
 * 锚点保持在原位置不动，是"向鼠标位置缩放"的关键：
 * 先记录锚点与两端的距离，再按比例缩放这两段距离。
 */
export function zoomAt(vp, anchorIdx, factor, n) {
  vp.a = anchorIdx - (anchorIdx - vp.a) * factor;
  vp.b = anchorIdx + (vp.b - anchorIdx) * factor;
  return clampView(vp, n);
}

/** 按像素位移平移。dxPx 为向右的像素数。 */
export function panBy(vp, dxPx, geom, n) {
  const span = vp.b - vp.a;
  const shift = -(dxPx / Math.max(geom.plotW, 1)) * span;
  vp.a += shift;
  vp.b += shift;
  return clampView(vp, n);
}

/**
 * 计算当前可见区间的值域，并留出余量。
 *
 * 只看可见段（而不是整段）——放大之后纵轴会随视野自动重新标定，
 * 否则局部的小幅波动会被整段的极值压成一条直线。
 *
 * 注意这里用显式循环而不是 Math.min(...chunk)：30 秒窗口有上万个采样点，
 * 展开成函数参数会超出调用栈上限而抛 RangeError。
 */
export function viewBounds(vp, signal) {
  const n = signal.length;
  if (!n) return { lo: -1, hi: 1 };

  const i0 = Math.max(0, Math.floor(vp.a));
  const i1 = Math.min(n - 1, Math.ceil(vp.b));
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = i0; i <= i1; i++) {
    const v = signal[i];
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { lo: -1, hi: 1 };
  if (hi - lo < 1e-9) {
    // 完全平直的一段：人为撑开，避免除以零，也避免画成一条贴边的线
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * VALUE_PADDING;
  return { lo: lo - pad, hi: hi + pad };
}

/** 纵坐标换算 */
export function makeYScale(bounds, geom) {
  const span = bounds.hi - bounds.lo || 1;
  return (v) => geom.padT + (1 - (v - bounds.lo) / span) * geom.plotH;
}

/**
 * 可见范围内按目标条数抽稀的步长。
 * 不抽稀的话，30 秒窗口在 DPR=2 下每帧要画两万多个点。
 */
export function decimationStep(vp, plotW) {
  const span = vp.b - vp.a;
  return Math.max(1, Math.floor(span / Math.max(plotW * 2, 1)));
}
