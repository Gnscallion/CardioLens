/* 单心搏放大视图：252 个采样点 + Grad-CAM 曲线。
 *
 * 与条带视图的区别：这里横坐标固定为整搏，不做缩放平移；
 * 重点是看清 QRS 形态与模型关注的时刻。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { CLASS_COLOR } from '../format.js';
import { POST_SAMPLES, PRE_SAMPLES, setupCanvas, THEME } from '../wave/render.js';
import { makeYScale } from '../wave/viewport.js';

/**
 * 从整窗信号里切出单搏。
 *
 * 后端返回的 beats[i] 只带索引与分类信息，不含波形本身——波形是整窗一份
 * （`signal`），单搏按 [sample - 90, sample + 162] 从中切出，与模型输入的
 * 252 个采样点严格对应。这样响应体积只随窗口长度增长，而不是随搏动数翻倍。
 */
export function sliceBeat(signal, sample) {
  if (!signal || !signal.length) return [];
  const start = Math.max(0, sample - PRE_SAMPLES);
  const end = Math.min(signal.length, sample + POST_SAMPLES);
  if (end <= start) return [];
  return signal.slice(start, end);
}

export default {
  name: 'BeatChart',
  props: {
    beat: { type: Object, default: () => ({}) },
    signal: { type: Array, default: () => [] },
    height: { type: Number, default: 200 },
  },

  setup(props) {
    const hostRef = ref(null);
    const canvasRef = ref(null);
    let observer = null;

    function draw() {
      const canvas = canvasRef.value;
      const host = hostRef.value;
      if (!canvas || !host) return;

      const beat = props.beat || {};
      const signal = sliceBeat(props.signal, beat.sample ?? -1);
      const cam = beat.cam;
      const w = host.clientWidth;
      if (w <= 0) return;

      const { ctx, W, H } = setupCanvas(canvas, w, props.height);
      const padL = 16;
      const padR = 16;
      const padT = 18;
      const padB = 24;
      const geom = { padL, padR, padT, padB, plotW: W - padL - padR, plotH: H - padT - padB };

      ctx.fillStyle = THEME.bg;
      ctx.fillRect(0, 0, W, H);

      const n = signal.length;
      if (!n) {
        ctx.fillStyle = THEME.text;
        ctx.font = '12px ui-monospace, monospace';
        ctx.textAlign = 'center';
        ctx.fillText('（该报告未保存单搏波形）', W / 2, H / 2);
        return;
      }

      let lo = Infinity;
      let hi = -Infinity;
      for (let i = 0; i < n; i++) {
        const v = signal[i];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      if (hi - lo < 1e-9) {
        lo -= 1;
        hi += 1;
      }
      const pad = (hi - lo) * 0.15;
      const bounds = { lo: lo - pad, hi: hi + pad };
      const yOf = makeYScale(bounds, geom);
      const xOf = (i) => padL + (i / Math.max(n - 1, 1)) * geom.plotW;

      // 网格
      ctx.strokeStyle = THEME.grid;
      ctx.lineWidth = 1;
      for (let i = 0; i < n; i += 25) {
        const x = xOf(i);
        ctx.beginPath();
        ctx.moveTo(x, padT);
        ctx.lineTo(x, padT + geom.plotH);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.moveTo(padL, yOf(0));
      ctx.lineTo(padL + geom.plotW, yOf(0));
      ctx.stroke();

      // R 峰参考线：单搏以 R 峰为原点，前 90 点后 162 点
      const rIdx = Math.min(PRE_SAMPLES, n - 1);
      ctx.strokeStyle = 'rgba(248,113,113,.55)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(xOf(rIdx), padT);
      ctx.lineTo(xOf(rIdx), padT + geom.plotH);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#f87171';
      ctx.font = '10px ui-monospace, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText('R', xOf(rIdx), padT - 5);

      // Grad-CAM 面积
      if (cam && cam.length === n) {
        const bottom = padT + geom.plotH;
        ctx.beginPath();
        ctx.moveTo(xOf(0), bottom);
        for (let i = 0; i < n; i++) {
          const h = geom.plotH * 0.42 * Math.max(0, Math.min(1, cam[i] || 0));
          ctx.lineTo(xOf(i), bottom - h);
        }
        ctx.lineTo(xOf(n - 1), bottom);
        ctx.closePath();
        ctx.fillStyle = `rgba(${THEME.camColor},.22)`;
        ctx.fill();
        ctx.strokeStyle = `rgba(${THEME.camColor},.7)`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }

      // 波形：按预测类别着色，与条带中的标记颜色一致
      const color = CLASS_COLOR[beat.pred] || THEME.signal;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineJoin = 'round';
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = xOf(i);
        const y = yOf(signal[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.fillStyle = THEME.text;
      ctx.font = '10px ui-monospace, monospace';
      ctx.textAlign = 'left';
      ctx.fillText('-0.25s', padL, H - 8);
      ctx.textAlign = 'right';
      ctx.fillText('+0.45s', padL + geom.plotW, H - 8);
    }

    onMounted(() => {
      draw();
      if (window.ResizeObserver) {
        observer = new ResizeObserver(draw);
        observer.observe(hostRef.value);
      }
    });

    onBeforeUnmount(() => {
      if (observer) observer.disconnect();
    });

    watch(() => [props.beat, props.signal], draw, { deep: false });

    return { hostRef, canvasRef };
  },

  template: `
    <div ref="hostRef" style="width:100%">
      <div class="wave-box">
        <canvas ref="canvasRef" data-test="beat-canvas"></canvas>
      </div>
    </div>
  `,
};
