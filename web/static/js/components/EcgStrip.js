/* 心电条带组件：把绘制层、交互层与尺寸监听串起来。
 *
 * 对外能力与桌面版的波形控件一一对应：
 *   setData / setSelected / setCam / resetView / zoomToBeat
 * 在这里体现为 props + 暴露的方法。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { bindInteractions } from '../wave/interaction.js';
import { drawBase, drawOverlay, makeGeom } from '../wave/render.js';
import { clampView, createViewport, resetView } from '../wave/viewport.js';

export default {
  name: 'EcgStrip',
  props: {
    signal: { type: Array, default: () => [] },
    fs: { type: Number, default: 360 },
    startSec: { type: Number, default: 0 },
    beats: { type: Array, default: () => [] },
    selected: { type: Number, default: -1 },
    showCam: { type: Boolean, default: true },
    height: { type: Number, default: 340 },
  },
  emits: ['select'],

  setup(props, { emit, expose }) {
    const hostRef = ref(null);
    const baseRef = ref(null);
    const overlayRef = ref(null);

    const width = ref(0);
    // 视图区间必须活在渲染逻辑之外：否则"选中搏动"触发的重绘会把
    // 用户辛苦缩放到的位置丢掉。桌面版用实例字段规避了这点，这里同理。
    const vp = createViewport();
    let geom = makeGeom(800, props.height);
    let hover = null;
    let unbind = null;
    let observer = null;
    let lastSignal = null;

    function currentState() {
      return {
        signal: props.signal || [],
        fs: props.fs || 360,
        startSec: props.startSec || 0,
        beats: props.beats || [],
        selected: props.selected ?? -1,
        showCam: props.showCam,
        vp,
        width: width.value,
        height: props.height,
      };
    }

    function draw() {
      if (!baseRef.value || !overlayRef.value || width.value <= 0) return;
      const state = currentState();
      geom = drawBase(baseRef.value, state);
      drawOverlay(overlayRef.value, state, geom, hover);
    }

    function handleViewChange() {
      hover = null;          // 视图变了，旧的读数位置已失效
      draw();
    }

    function handleHover(h) {
      // 只重绘顶层，不动底层
      if (width.value <= 0 || !overlayRef.value) return;
      hover = h;
      drawOverlay(overlayRef.value, currentState(), geom, hover);
    }

    function measure() {
      if (!hostRef.value) return;
      const w = hostRef.value.clientWidth;
      if (w > 0 && w !== width.value) {
        width.value = w;
        draw();
      }
    }

    onMounted(() => {
      measure();
      draw();

      unbind = bindInteractions(baseRef.value, currentState, {
        onSelect: (i) => emit('select', i),
        onViewChange: handleViewChange,
        onHover: handleHover,
      });

      // SPA 里容器尺寸会随视图切换、窗口缩放、侧栏变化而变，
      // 只监听 window.resize 是不够的。
      if (window.ResizeObserver) {
        observer = new ResizeObserver(measure);
        observer.observe(hostRef.value);
      } else {
        window.addEventListener('resize', measure);
      }
    });

    onBeforeUnmount(() => {
      if (unbind) unbind();
      if (observer) observer.disconnect();
      else window.removeEventListener('resize', measure);
    });

    // 数据换了（新的一次分析 / 另一条历史）→ 复位视图
    watch(
      () => props.signal,
      (sig) => {
        if (sig === lastSignal) return;
        lastSignal = sig;
        resetView(vp, (sig || []).length);
        hover = null;
        draw();
      }
    );

    // 选中项、Grad-CAM 开关、窗口起点变化 → 重绘底层（视图区间保持不变）
    watch(
      () => [props.selected, props.showCam, props.startSec],
      () => draw()
    );

    watch(() => props.height, () => draw());

    function resetToFull() {
      resetView(vp, props.signal.length);
      handleViewChange();
    }

    function zoomToBeat(i) {
      const b = props.beats[i];
      if (!b) return;
      const n = props.signal.length;
      const half = Math.max(120, Math.min(n / 2, 400));
      vp.a = b.sample - half;
      vp.b = b.sample + half;
      clampView(vp, n);          // 与缩放/平移共用同一套边界规则
      handleViewChange();
    }

    expose({ resetView: resetToFull, zoomToBeat });

    // 模板里要直接调用，因此除了 expose 给父组件，还要从 setup 返回
    return { hostRef, baseRef, overlayRef, width, resetToFull, zoomToBeat };
  },

  template: `
    <div class="ecg-strip" ref="hostRef" style="width:100%">
      <div class="wave-toolbar">
        <span class="wave-hint">滚轮缩放 · 拖拽平移 · 双击复位 · 悬停读数 · 点击搏动查看详情</span>
        <button type="button" class="btn btn-ghost btn-sm" @click="resetToFull">复位视图</button>
      </div>
      <div class="wave-box">
        <div class="canvas-stack" :style="{ height: height + 'px' }">
          <canvas ref="baseRef" class="base" data-test="wave-canvas"></canvas>
          <canvas ref="overlayRef" class="overlay"></canvas>
        </div>
      </div>
    </div>
  `,
};
