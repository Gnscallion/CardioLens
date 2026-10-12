/* 波形交互：滚轮缩放 / 拖拽平移 / 双击复位 / 悬停读数 / 点击选中。
 *
 * 这些能力在上一版 Web 版中完全缺失（只有点击与悬停提示），
 * 属于相对桌面版的功能回退，本模块负责补齐。
 *
 * 浏览器比 Qt 多了几个必须处理的坑，逐条写在各处注释里。
 */
import { idxOf, panBy, resetView, xOf, zoomAt, ZOOM_FACTOR } from './viewport.js';

/** 命中搏动的横向容差（像素）。与桌面版一致。 */
export const BEAT_HIT_TOL_PX = 14;

/** 超过这个位移就判定为"拖拽"而不是"点击"。 */
export const DRAG_START_TOL_PX = 4;

/** 两次 pointerdown 间隔小于此值视为同一次双击序列。 */
const DBLCLICK_WINDOW_MS = 400;

/**
 * 绑定交互。返回解绑函数。
 *
 * @param {HTMLCanvasElement} canvas 底层画布（顶层是 pointer-events:none 的覆盖层）
 * @param {() => object} getState 取当前状态：{ vp, geom, signal, beats, selected }
 * @param {object} handlers { onSelect(i), onViewChange(), onHover({idx,x,y}|null) }
 */
export function bindInteractions(canvas, getState, handlers) {
  let drag = null;
  let lastPointerDownAt = 0;
  // 双击序列开始前的选中项。双击会先触发两次 click，若不做记录，
  // 复位视图的同时选中项会被改掉，与"复位"这个动作的语义不符。
  let selBeforeSequence = -1;

  const localX = (ev) => ev.clientX - canvas.getBoundingClientRect().left;

  function hitBeat(state, x) {
    const { beats, vp, geom } = state;
    let best = -1;
    let bestD = BEAT_HIT_TOL_PX;
    for (let i = 0; i < beats.length; i++) {
      const d = Math.abs(xOf(vp, beats[i].sample, geom) - x);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    return best;
  }

  function onWheel(ev) {
    const state = getState();
    if (!state.signal.length) return;

    // 必须阻止默认行为，否则页面会跟着滚，"缩放"完全不可用。
    // 监听时还要显式 { passive: false }，因为 wheel 默认是 passive 的，
    // 那种情况下 preventDefault 会被忽略并打印一条控制台警告。
    ev.preventDefault();
    if (!ev.deltaY) return;

    const x = localX(ev);
    const anchor = idxOf(state.vp, x, state.geom);
    const factor = ev.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR;
    zoomAt(state.vp, anchor, factor, state.signal.length);
    handlers.onViewChange();
  }

  function onPointerDown(ev) {
    const state = getState();
    if (!state.signal.length) return;

    const now = ev.timeStamp;
    if (now - lastPointerDownAt > DBLCLICK_WINDOW_MS) {
      selBeforeSequence = state.selected;
    }
    lastPointerDownAt = now;

    const x = localX(ev);
    // 只有绘图区内才起拖；左侧坐标轴区域留给将来的框选之类
    if (x < state.geom.padL) return;

    // 无论落点是否命中搏动都开始一次"可能的拖拽"。若按上一版的做法
    // （命中搏动就直接选中并 return），从搏动上方就无法起拖了。
    canvas.setPointerCapture(ev.pointerId);
    canvas.style.cursor = 'grabbing';
    drag = {
      moved: false,
      x0: x,
      vp0: { a: state.vp.a, b: state.vp.b },   // 从按下时的视图推算，避免累积误差
    };
  }

  function onPointerMove(ev) {
    const state = getState();
    if (!state.signal.length) return;
    const x = localX(ev);

    if (drag) {
      if (!drag.moved && Math.abs(x - drag.x0) > DRAG_START_TOL_PX) {
        drag.moved = true;
      }
      if (drag.moved) {
        state.vp.a = drag.vp0.a;
        state.vp.b = drag.vp0.b;
        panBy(state.vp, x - drag.x0, state.geom, state.signal.length);
        handlers.onViewChange();
      }
      return;
    }

    // 未按下时：更新十字线读数
    const idx = idxOf(state.vp, x, state.geom);
    if (x < state.geom.padL || x > state.geom.padL + state.geom.plotW) {
      handlers.onHover(null);
    } else {
      handlers.onHover({ idx, x });
      canvas.style.cursor = hitBeat(state, x) >= 0 ? 'pointer' : 'crosshair';
    }
  }

  function onPointerUp(ev) {
    if (!drag) return;
    const state = getState();
    const x = localX(ev);

    // 位移很小 => 这是一次点击，做命中测试
    if (!drag.moved) {
      const hit = hitBeat(state, x);
      if (hit >= 0) handlers.onSelect(hit);
    }
    drag = null;
    canvas.style.cursor = 'crosshair';

    if (canvas.hasPointerCapture(ev.pointerId)) {
      canvas.releasePointerCapture(ev.pointerId);
    }
  }

  function onPointerLeave() {
    if (!drag) handlers.onHover(null);
  }

  function onDblClick(ev) {
    const state = getState();
    if (!state.signal.length) return;
    ev.preventDefault();
    resetView(state.vp, state.signal.length);
    // 两次 click 可能已经把选中项改掉了，这里还原到双击序列开始前的值
    if (selBeforeSequence >= 0 && selBeforeSequence !== state.selected) {
      handlers.onSelect(selBeforeSequence);
    }
    handlers.onViewChange();
  }

  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('pointerleave', onPointerLeave);
  canvas.addEventListener('dblclick', onDblClick);
  canvas.style.cursor = 'crosshair';

  return function unbind() {
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerUp);
    canvas.removeEventListener('pointerleave', onPointerLeave);
    canvas.removeEventListener('dblclick', onDblClick);
  };
}
