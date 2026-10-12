/* 关于：数据来源、五分类定义、模型原理、评估结果、Grad-CAM、已知局限、技术栈。 */
import { computed } from 'vue';

import { DisclaimerNote } from '../components/common.js';
import { int, num, pct } from '../format.js';
import { store } from '../store.js';

const TECH_STACK = [
  ['前端', 'Vue 3（ESM 构建，本地分发）+ 原生 Canvas 2D', '不引入构建工具与 npm 依赖，部署时服务器只需 Python；波形用 Canvas 自绘以获得缩放/平移与热力图叠加的自由度'],
  ['后端', 'Flask 3 + Waitress', '应用工厂 + 蓝图；单进程多线程，使限流与并发控制的内存状态保持正确'],
  ['推理引擎', 'PyTorch 2.x（CPU 版）', '与界面完全解耦；本次从桌面版迁移到 Web 版未改动模型与推理逻辑'],
  ['模型结构', '双分支 1D-CNN（103,109 参数）', '形态分支负责 QRS 形态，RR 节律分支补足早搏判别所需的"提前出现"信息'],
  ['信号处理', 'SciPy（Butterworth 带通 + filtfilt）', '零相位滤波，不引入时间偏移'],
  ['数据读取', 'NumPy', '记录以 .npy 存储，按需加载并做有界缓存'],
  ['持久化', 'SQLite（WAL 模式）', '免安装、免配置；按会话标识隔离历史记录'],
  ['可解释性', 'Grad-CAM（一维推广）', '对最后一层卷积求梯度，上采样回 252 个采样点与波形严格对齐'],
];

export default {
  name: 'AboutView',
  components: { DisclaimerNote },

  setup() {
    const metrics = computed(() => store.metrics || {});
    const test = computed(() => metrics.value.test || {});
    const perClass = computed(() => test.value.per_class || {});

    const classRows = computed(() =>
      (store.classes || []).map((c) => {
        const m = perClass.value[c.code] || {};
        return { code: c.code, name: c.name, ...m };
      })
    );

    const metricNote = computed(() => metrics.value.metric_note || '');

    return { store, metrics, test, perClass, classRows, metricNote, TECH_STACK, pct, num, int };
  },

  template: `
    <div>
      <div class="card">
        <h2>项目背景</h2>
        <p>
          一次 24 小时动态心电监测会产生约 <b>10 万次心搏</b>，由医师逐搏人工判读既耗时又存在主观差异。
          本项目实现了一套可在普通笔记本（纯 CPU、无 GPU、无付费 API）上完整运行的心电搏动自动分析系统：
          读取 MIT-BIH 心律失常数据库的真实记录，经带通滤波与逐搏切分后，由一维卷积网络完成
          <b>AAMI EC57 五分类</b>，并用 Grad-CAM 给出模型判定时关注的时间片段。
        </p>
        <p class="mb0">
          上一版交付形态是 PySide6 桌面程序。本次改为 <b>Web 服务</b>：客户端无需安装任何软件，
          打开浏览器即可使用，且多名使用者可以在同一份服务上并行工作、各自只看到自己的历史记录。
          之所以能这样切换，是因为推理引擎与界面从一开始就是解耦的——
          这次迁移没有改动模型结构、训练流程与推理算法。
        </p>
      </div>

      <div class="card">
        <h2>数据来源与划分</h2>
        <dl class="kv">
          <dt>数据集</dt><dd>MIT-BIH Arrhythmia Database（PhysioNet mitdb）</dd>
          <dt>记录数</dt><dd>{{ store.meta.n_records || '—' }} 条</dd>
          <dt>总心搏数</dt><dd>{{ int(store.meta.total_beats) }}</dd>
          <dt>划分方式</dt><dd>跨患者划分（inter-patient）：训练 {{ store.meta.n_train || '—' }} / 测试 {{ store.meta.n_test || '—' }}</dd>
        </dl>
        <p class="muted small" style="margin-top:10px">
          按 AAMI 惯例剔除 4 条起搏搏动占比过高、标注存在争议的记录（102、104、107、217）。
          跨患者划分要求同一患者不能同时出现在训练集与测试集中，否则模型可能记住患者个体特征，
          得出虚高的指标。
        </p>
      </div>

      <div class="card">
        <h2>AAMI EC57 五分类</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>类别</th><th>名称</th><th>说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in store.classes" :key="c.code">
                <td><span class="badge" :class="'badge-' + c.code">{{ c.code }}</span></td>
                <td class="nowrap">{{ c.name }}</td>
                <td class="small muted">{{ c.desc }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>模型原理</h2>
        <p>
          网络是<b>双分支结构</b>，共 103,109 个参数：
        </p>
        <ul>
          <li>
            <b>形态分支</b>：三层一维卷积 + 全局池化，输入为单个心搏的 252 个采样点
            （R 峰前 90 点、后 162 点）。最后一层卷积刻意保留时间分辨率，因此可以直接用于 Grad-CAM。
          </li>
          <li>
            <b>节律分支</b>：一条轻量 MLP，输入为前后 RR 间期及其相对本记录基线的比值，共 4 维。
          </li>
        </ul>
        <p>
          <b>为什么需要节律分支：</b>单导联上「室上性早搏」与「正常搏动」的 QRS 形态几乎同形，
          真正把它们区分开的是<b>提前出现</b>这一节律信息。只用形态特征时，这两类几乎无法分开；
          补上相对基线归一化的 RR 比值后，区分度有实质提升。
        </p>
        <p class="mb0">
          RR 特征采用<b>相对本记录 RR 中位数</b>的比值而非绝对秒数——各记录的基础心率差异很大，
          同样是 0.8 秒，在慢心率记录里算正常，在快心率记录里已属明显提前。
          用中位数而非均值作基线，是因为早搏会让少数 RR 明显偏离，均值容易被拉偏。
        </p>
      </div>

      <div class="card">
        <h2>评估结果</h2>
        <div class="grid grid-4">
          <div class="stat ok"><div class="k">准确率</div><div class="v">{{ pct(test.accuracy) }}</div></div>
          <div class="stat"><div class="k">Macro-F1（四类）</div><div class="v">{{ num(test.macro_f1, 3) }}</div></div>
          <div class="stat warn"><div class="k">Macro-F1（五类）</div><div class="v">{{ num(test.macro_f1_5class, 3) }}</div></div>
          <div class="stat accent"><div class="k">最佳轮次</div><div class="v">{{ metrics.best_epoch ?? '—' }}</div></div>
        </div>

        <div class="table-wrap mt16">
          <table>
            <thead>
              <tr><th>类别</th><th>名称</th><th class="num">精确率</th><th class="num">召回率</th><th class="num">F1</th><th class="num">样本数</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in classRows" :key="r.code">
                <td><span class="badge" :class="'badge-' + r.code">{{ r.code }}</span></td>
                <td class="nowrap">{{ r.name }}</td>
                <td class="num">{{ r.precision != null ? num(r.precision, 3) : '—' }}</td>
                <td class="num">{{ r.recall != null ? num(r.recall, 3) : '—' }}</td>
                <td class="num">{{ r.f1 != null ? num(r.f1, 3) : '—' }}</td>
                <td class="num">{{ r.support ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="muted small" style="margin-top:10px" v-if="metricNote">{{ metricNote }}</p>
        <p class="muted small mb0">
          该项目<b>如实展示</b>各项指标，未做删除或美化。指标偏低的两类在下方"已知局限"中专门讨论。
        </p>
      </div>

      <div class="grid grid-2">
        <div class="card">
          <h2>训练曲线</h2>
          <img src="/media/training_curve.png" alt="训练与验证损失、Macro-F1 随轮次的变化"
               style="width:100%;border-radius:9px;border:1px solid var(--border)">
          <p class="muted small" style="margin-top:8px">
            训练带早停机制（连续多轮验证指标不提升即停止），本次在第 {{ metrics.best_epoch ?? '—' }} 轮取到最佳权重。
          </p>
        </div>
        <div class="card">
          <h2>混淆矩阵</h2>
          <img src="/media/confusion_matrix.png" alt="测试集混淆矩阵"
               style="width:100%;border-radius:9px;border:1px solid var(--border)">
          <p class="muted small" style="margin-top:8px">
            对角线为正确判定。可以直观看到 F 类（融合搏动）几乎全部被误判为 N 或 V。
          </p>
        </div>
      </div>

      <div class="card">
        <h2>Grad-CAM 可解释性</h2>
        <p>
          Grad-CAM 回答的是「模型凭什么这么判断」：取最后一层卷积的特征图，
          对目标类别得分求梯度并在通道维求平均得到权重，加权求和后经 ReLU，
          再线性上采样回 252 个采样点，与该搏波形严格对齐。
        </p>
        <p class="mb0">
          对心电而言，高亮区域通常落在 QRS 波群附近——这与临床医生判读早搏时关注 QRS 形态
          （宽大畸形提示室性来源）的经验一致。需要注意：Grad-CAM 解释的是<b>波形分支</b>，
          节律分支只参与前向计算提供上下文，不对其求显著性（它本身只有 4 维，可读性已经足够）。
        </p>
      </div>

      <div class="card">
        <h2>已知局限</h2>
        <ul>
          <li>
            <b>F 类（融合搏动）基本识别不出。</b>测试集中的 F 类样本绝大多数被误判为 N 或 V。
            融合搏动的形态介于正常与室性之间，单导联形态学特征本身区分度不足，训练样本也偏少。
          </li>
          <li>
            <b>S 类（室上性早搏）召回率很低。</b>即"判为 S 的基本是对的，但绝大多数 S 被漏掉"。
            这是当前最主要的短板。加入 RR 节律特征后已有改善，但离可用仍有距离。
          </li>
          <li>
            <b>Q 类样本极少，指标不具统计意义。</b>因此主指标按 N/S/V/F 四类计算 Macro-F1，
            五类 Macro-F1 仅作对照列出。
          </li>
          <li>
            <b>仅使用单导联、单搏形态 + RR 特征。</b>未做多导联融合，也未建模更长的节律上下文。
          </li>
          <li>
            <b>不是医疗器械。</b>本系统为软件工程课程作业演示项目，不具备任何临床用途。
          </li>
        </ul>
      </div>

      <div class="card">
        <h2>技术栈</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>层次</th><th>选型</th><th>选择理由</th></tr></thead>
            <tbody>
              <tr v-for="row in TECH_STACK" :key="row[0]">
                <td class="nowrap"><b>{{ row[0] }}</b></td>
                <td class="nowrap">{{ row[1] }}</td>
                <td class="small muted">{{ row[2] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>运行环境与数据安全</h2>
        <dl class="kv">
          <dt>推理设备</dt><dd>纯 CPU，无需显卡</dd>
          <dt>外部依赖</dt><dd>无付费 API；前端依赖本地分发，不依赖任何 CDN</dd>
          <dt>上传功能</dt><dd>无。本站使用内置的公开数据集记录，服务端不接受任何文件上传</dd>
          <dt>数据流向</dt><dd>浏览器 → HTTPS → 服务端推理 → 返回结果</dd>
          <dt>访问标识</dt><dd>仅存储一个 256 位随机浏览器标识，用于隔离各自的历史记录；不关联设备信息，不做埋点</dd>
        </dl>
        <p class="muted small" style="margin-top:10px">
          该标识等同于访问你自己历史记录的凭据。清除浏览器数据后，原记录将无法在此浏览器中访问。
          服务端不接受上传，意味着使用者的本地数据不会被传输到服务器。
        </p>
      </div>

      <DisclaimerNote :text="store.disclaimer" />
    </div>
  `,
};
