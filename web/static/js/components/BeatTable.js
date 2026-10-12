/* 逐搏结果表。点击任意一行联动波形与单搏详情。
 *
 * 一个 30 秒窗口最多约 50 次搏动（时长上限见 src/inference.py 的
 * MAX_WINDOW_SEC），因此不需要分页或虚拟滚动，整表渲染即可。
 */
import { CLASS_NAME_FALLBACK, num, pct } from '../format.js';

export default {
  name: 'BeatTable',
  props: {
    beats: { type: Array, default: () => [] },
    selected: { type: Number, default: -1 },
    startSec: { type: Number, default: 0 },
    fs: { type: Number, default: 360 },
  },
  emits: ['select'],

  computed: {
    rows() {
      return this.beats.map((b, i) => ({
        i,
        beat: b,
        // 绝对时间 = 窗口起点 + 窗口内偏移，与波形刻度、十字线读数同一坐标系
        absTime: (this.startSec + (b.time_sec ?? b.sample / this.fs)).toFixed(2),
        name: b.pred_name || CLASS_NAME_FALLBACK[b.pred] || '',
      }));
    },
  },

  template: `
    <div class="table-wrap" style="max-height:420px;overflow-y:auto">
      <table data-test="beat-rows">
        <thead>
          <tr>
            <th class="num">序号</th>
            <th class="num">位置 (s)</th>
            <th>预测类别</th>
            <th class="num">置信度</th>
            <th>专家标注</th>
            <th class="center">是否一致</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.i"
              class="clickable"
              :class="{ sel: r.i === selected }"
              @click="$emit('select', r.i)">
            <td class="num">{{ r.beat.index }}</td>
            <td class="num">{{ r.absTime }}</td>
            <td>
              <span class="badge" :class="'badge-' + r.beat.pred">{{ r.beat.pred }} · {{ r.name }}</span>
            </td>
            <td class="num">{{ pct(r.beat.confidence) }}</td>
            <td>
              <span class="badge badge-mute">{{ r.beat.expert }} · {{ r.beat.expert_name }}</span>
            </td>
            <td class="center">
              <span :class="r.beat.agree ? 'badge badge-ok' : 'badge badge-warn'">
                {{ r.beat.agree ? '一致' : '不一致' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `,

  setup() {
    return { pct, num };
  },
};
