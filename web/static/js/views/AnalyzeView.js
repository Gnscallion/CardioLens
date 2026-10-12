/* ECG 分析工作台：选记录 → 调窗口 → 预览 → 分析 → 读结果 → 保存。 */
import { computed, onMounted, ref, watch } from 'vue';

import EcgStrip from '../components/EcgStrip.js';
import ResultPanel from '../components/ResultPanel.js';
import SessionNotice from '../components/SessionNotice.js';
import { store } from '../store.js';

export default {
  name: 'AnalyzeView',
  components: { EcgStrip, ResultPanel, SessionNotice },

  setup() {
    const recordId = ref('');
    const startSec = ref(0);
    const durationSec = ref(10);
    const withCam = ref(true);

    const previewLoading = ref(false);
    const analysisError = ref('');
    const saving = ref(false);
    const saved = ref(false);

    const records = computed(() => store.records || []);

    const currentRecord = computed(
      () => records.value.find((r) => r.id === recordId.value) || null
    );

    /** 记录总时长，用于收敛滑块上限 */
    const totalSec = computed(() => currentRecord.value?.duration_sec || 0);

    /** 起点上限：保证 start + duration 不超出记录末尾 */
    const maxStart = computed(() =>
      Math.max(0, Math.floor((totalSec.value - durationSec.value) * 10) / 10)
    );

    const ready = computed(() => store.ready);

    /** 预览用的窗口值一律取响应里的真值（后端可能向左回退对齐） */
    const previewStart = computed(() => store.preview?.start_sec ?? startSec.value);

    /**
     * 预览时隐藏 Grad-CAM：预览的目标是看波形与 R 峰位置，
     * 这个阶段还没跑推理，没有显著性可叠加。
     */
    const previewBeats = computed(() =>
      (store.preview?.beat_marks || []).map((m, i) => ({
        index: i + 1,
        sample: m.sample,
        pred: m.aami,
        time_sec: m.sample / (store.preview?.fs || 360),
      }))
    );

    function selectRecord(id) {
      recordId.value = id;
      startSec.value = 0;
      if (currentRecord.value) {
        const max = Math.max(3, Math.min(30, currentRecord.value.duration_sec));
        if (durationSec.value > max) durationSec.value = max;
      }
    }

    function clampStart() {
      if (startSec.value > maxStart.value) startSec.value = maxStart.value;
      if (startSec.value < 0) startSec.value = 0;
    }

    async function doPreview() {
      if (!recordId.value) return;
      previewLoading.value = true;
      analysisError.value = '';
      try {
        clampStart();
        await store.loadPreview(recordId.value, startSec.value, durationSec.value);
      } catch (err) {
        analysisError.value = err.message;
      } finally {
        previewLoading.value = false;
      }
    }

    async function doAnalyze() {
      analysisError.value = '';
      saved.value = false;
      try {
        clampStart();
        await store.runAnalysis({
          recordId: recordId.value,
          startSec: startSec.value,
          durationSec: durationSec.value,
          withCam: withCam.value,
        });
      } catch (err) {
        if (err.name !== 'AbortError') analysisError.value = err.message;
      }
    }

    async function doSave() {
      if (!store.result) return;
      saving.value = true;
      try {
        // 保存会把当前参数重新提交一次，由后端重跑并落库（约 0.3 秒）。
        // 这样前端不需要维护"未保存的结果"这份额外状态。
        await store.runAnalysis({
          recordId: store.result.record_id,
          startSec: store.result.start_sec,
          durationSec: store.result.duration_sec,
          withCam: withCam.value,
          save: true,
        });
        saved.value = true;
        store.notify('报告已保存到分析历史', 'ok');
      } catch (err) {
        store.notify(err.message, 'err');
      } finally {
        saving.value = false;
      }
    }

    onMounted(async () => {
      if (!recordId.value && records.value.length) {
        const preferred = records.value.find((r) => r.recommended) || records.value[0];
        selectRecord(preferred.id);
      }
      if (ready.value && recordId.value) doPreview();
    });

    // 记录列表可能比视图更晚就绪（首屏通常已内联进来，这是兜底）
    watch(records, (list) => {
      if (!recordId.value && list.length) {
        const preferred = list.find((r) => r.recommended) || list[0];
        selectRecord(preferred.id);
        if (ready.value) doPreview();
      }
    });

    watch(durationSec, () => {
      if (startSec.value > maxStart.value) startSec.value = maxStart.value;
    });

    return {
      store, recordId, startSec, durationSec, withCam, records, currentRecord,
      maxStart, totalSec, previewLoading, analysisError, saving, saved,
      ready, previewStart, previewBeats,
      selectRecord, doPreview, doAnalyze, doSave,
    };
  },

  template: `
    <div>
      <div class="alert alert-err" v-if="!ready" data-test="not-ready">
        <span class="ic">⚠️</span>
        <span>
          <strong>服务尚未就绪。</strong>{{ store.readyMessage }}<br>
          <span class="small">请确认数据集与模型文件已就位后刷新页面。</span>
        </span>
      </div>

      <SessionNotice compact />

      <div class="grid grid-side">
        <!-- 左栏：参数 -->
        <div>
          <div class="card">
            <h2>分析参数</h2>

            <div class="field">
              <label for="recSel">心电记录</label>
              <select id="recSel" data-test="rec-select" v-model="recordId"
                      @change="doPreview">
                <option v-for="r in records" :key="r.id" :value="r.id">
                  {{ r.recommended ? '★ ' : '' }}记录 {{ r.id }} · {{ r.n_beats }} 搏
                  {{ r.split ? ' · ' + r.split : '' }}
                </option>
              </select>
              <p class="hint" v-if="currentRecord && currentRecord.note">
                {{ currentRecord.note }}
              </p>
            </div>

            <div class="field">
              <label>快速选择（推荐演示记录）</label>
              <div class="quick">
                <template v-for="(r, i) in records" :key="r.id">
                  <button v-if="r.recommended" type="button" class="chip"
                          :class="{ on: r.id === recordId }"
                          @click="selectRecord(r.id); doPreview()">
                    {{ r.id }}
                  </button>
                </template>
              </div>
            </div>

            <div class="field">
              <label>起始时间</label>
              <div class="range-row">
                <input type="range" min="0" :max="maxStart" step="0.5"
                       v-model.number="startSec" data-test="start-range">
                <span class="range-val">{{ startSec.toFixed(1) }}s</span>
              </div>
              <p class="hint">记录总时长 {{ totalSec.toFixed(0) }} 秒</p>
            </div>

            <div class="field">
              <label>分析时长</label>
              <div class="range-row">
                <input type="range" min="3" max="30" step="1"
                       v-model.number="durationSec" data-test="duration-range">
                <span class="range-val">{{ durationSec }}s</span>
              </div>
              <p class="hint">上限 30 秒：逐搏 Grad-CAM 需要逐样本反向传播，窗口越长耗时越长。</p>
            </div>

            <div class="field">
              <label class="check">
                <input type="checkbox" v-model="withCam" data-test="cam-check">
                生成 Grad-CAM 可解释性热力图
              </label>
            </div>

            <button type="button" class="btn btn-ghost btn-block"
                    data-test="preview-btn"
                    :disabled="!ready || previewLoading" @click="doPreview">
              {{ previewLoading ? '加载中…' : '预览波形' }}
            </button>

            <button type="button" class="btn btn-primary btn-block mt16"
                    data-test="analyze-btn"
                    :disabled="!ready || store.analyzing" @click="doAnalyze">
              {{ store.analyzing ? '分析中…' : '开始分析' }}
            </button>
          </div>
        </div>

        <!-- 右栏：波形与结果 -->
        <div>
          <div class="card" v-if="store.preview">
            <div class="card-head">
              <h2>波形预览</h2>
              <span class="card-sub mb0">
                记录 {{ store.preview.record_id }} ·
                {{ store.preview.start_sec.toFixed(1) }}s 起
                {{ store.preview.duration_sec.toFixed(0) }} 秒 ·
                窗口内 {{ store.preview.n_beats_in_window }} 次心搏
              </span>
            </div>
            <EcgStrip :signal="store.preview.signal"
                      :fs="store.preview.fs"
                      :start-sec="previewStart"
                      :beats="previewBeats"
                      :selected="-1"
                      :show-cam="false"
                      :height="280" />
            <p class="muted small mb0" style="margin-top:8px">
              预览阶段只展示信号与 R 峰位置，不加载模型；点击"开始分析"后才会逐搏分类。
            </p>
          </div>

          <div class="card" v-if="analysisError">
            <div class="alert alert-err mb0" data-test="analyze-error">
              <span class="ic">⚠️</span>
              <span><strong>分析失败。</strong>{{ analysisError }}</span>
            </div>
          </div>

          <!--
            分析进行中。这里刻意不显示百分比：推理是一次同步调用，
            拿不到真实的阶段进度，编一个动画进度条反而是在骗用户。
            桌面版用的同样是不确定进度条。
          -->
          <div class="card" v-if="store.analyzing" data-test="analyzing">
            <div class="loading">
              <div class="spinner"></div>
              <div>正在进行逐搏分析，请稍候…</div>
              <div class="progress-indeterminate"></div>
              <p class="muted small mb0">
                分析期间页面仍可正常滚动与切换，结果返回后会自动展示。
              </p>
            </div>
          </div>

          <div class="card" v-else-if="!store.result">
            <div class="empty">
              <div class="big">🫀</div>
              <p>在左侧选择记录与时间窗，点击"开始分析"查看逐搏结果。</p>
            </div>
          </div>

          <ResultPanel v-else-if="store.result"
                       :result="store.result"
                       :saving="saving"
                       :saved="saved"
                       @save="doSave" />
        </div>
      </div>
    </div>
  `,
};
