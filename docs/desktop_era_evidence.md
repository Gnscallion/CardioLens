# 桌面版时代证据留存

> 本文件在「桌面版 → Web 版」改造**之前**建立，用于保存随后被删除的桌面版产物与验收证据的
> 关键事实，供 `PROJECT_REPORT.md` 的迁移叙事引用。
>
> 被删目录：`desktop/`、`dist/`、`CardioLens.spec`、`CardioLensSelfTest.spec`、
> `docs/screenshots_desktop/`、`docs/screenshots_legacy_web/`、`docs/test_evidence/`

---

## 1. 交付产物

| 项 | 值 |
|---|---|
| 产物 | `dist/CardioLens.exe` |
| 体积 | 324,192,992 字节（约 309 MB） |
| MD5 | `21a414daadfe0f397b9b36ae02ece349` |
| 构建方式 | PyInstaller `--onefile --windowed`（见 `CardioLens.spec`） |
| 备份位置 | 项目外 `..\CardioLens_pre_web_backup\`（**未进 git**，故 git 历史中不含此文件） |

体积主要来自打包进单文件的 Python 运行时、PyTorch 与 Qt（可从中检出 `python312.dll`、`PySide6`、`torch`）。

## 2. 受保护产物的 MD5 基线

迁移期间必须保持不变，`scripts/test_web.py` 会持续校验：

| 产物 | MD5 |
|---|---|
| `models/ecg_cnn.pt` | `a5ca4a0ec6d0330303a590a6d35c4fa3` |
| `models/metrics.json` | `db51fef423254c391dce5a27081d8cc8` |
| `data/processed/beats.npz` | `f27ed5050405b5c63bd803bb2acf57ab` |

## 3. 冻结运行时自检（`docs/test_evidence/frozen_report.json`）

在 PyInstaller 冻结运行时中的实测结果：

| 字段 | 值 |
|---|---|
| `frozen` | `true` |
| `resource_root` | `C:\Windows\Temp\_MEI000011d02` |
| `user_data_dir` | `%LOCALAPPDATA%\CardioLens` |
| `readiness.ok` | `true` |
| `beats_npz_required` | **`false`** |
| `metrics_loaded` / `meta_loaded` | `true` / `true` |

> **`beats_npz_required: false` 是本次 Web 改造的一条重要依据。**
> 推理链路只需要 `signals/` + `annots/` + `record_meta.json` + 模型权重，**不需要** 91 MB 的
> `beats.npz`（那是训练样本集）。但 `src/inference.py` 的 `is_ready()` 会检查它，
> 因此 Web 版必须自建就绪检查（`web/readiness.py`），否则只部署运行最小集时整个应用会表现为不可用。

## 4. 桌面版自测结果

`scripts/test_desktop.py` 共 12 组、**73 个断言全部通过**，覆盖：

| 组 | 内容 | Web 版去向 |
|:--:|---|---|
| [1] | 就绪检查 2 例 | 迁移至 `test_web.py` |
| [2] | 三个受保护产物 MD5 3 例 | 原样迁移 |
| [3] | 推理一致性 9 例（独立复算 + forward hook 截获比对） | 迁移，改经 `/api/analyze` |
| [4] | Grad-CAM 6 例（长度 252、值域、开关一致性） | 原样迁移 |
| [5] | 汇总算术 8 例 | 原样迁移 |
| [6] | DB schema 4 例 | 按新 schema（+`owner` 列）改写 |
| [7] | 历史 CRUD 9 例 | 迁移，改走 HTTP |
| [8] | GUI 构造与导航 9 例 | **废弃**（PySide6 专有） |
| [9] | 后台线程与进度 5 例 | **废弃**（QThread 专有） |
| [10] | 结果页装载与 Grad-CAM 联动 12 例 | **废弃**（GUI 专有），语义由前端验收覆盖 |
| [11] | 离线扫描（AST 扫 `desktop/**` 禁 flask/requests/localhost 等） | **语义反转**为「Web 版不得含 PySide6」 |
| [12] | 用户文案无 Web 术语 2 例 | **语义反转**为「文案不得含 EXE / %LOCALAPPDATA%」 |

## 5. 界面截图清单

`docs/screenshots_desktop/`（11 张，桌面版交付形态）：

```
01-首页.png                        07-历史详情.png
02-ECG分析-参数与预览.png           08-关于-上半.png
03-分析结果-整体.png                09-关于-评估结果.png
04-分析结果-异常搏动.png            10-关于-局限与声明.png
05-单搏详情与GradCAM.png            11-独立EXE首次启动验证.png
06-分析历史.png
```

`docs/screenshots_legacy_web/`（14 张，更早的 Flask+Jinja 版）：

```
01-首页.png              08-保存报告.png
02-分析工作台.png         09-历史记录.png
03-波形预览.png           10-历史详情.png
04-分析过程.png           11-关于与技术原理.png
05-分析结果.png           12-评估结果与混淆矩阵.png
06-逐搏明细.png           13-数据划分提示-训练集记录.png
07-单搏详情与GradCAM.png  14-数据划分提示-测试集记录.png
```

新 Web 版的截图产出到 `docs/screenshots_web/`，页面覆盖对齐上述两份清单，
并新增 4 张 Web 特性截图（波形缩放 / 波形平移 / 悬停十字线读数 / 移动端视口）。

## 6. 桌面版独有、Web 版必须补齐的交互能力

对照 `desktop/widgets/ecg_plot.py`（469 行，QPainter 自绘），以下能力在更早的 `legacy_web` 版中
**完全缺失**，Web 版重写时必须补齐，否则属于功能回退：

1. 滚轮缩放（锚点在光标处）
2. 拖拽平移
3. 双击复位
4. 悬停十字线读数（时间 + 幅值）
5. 真实进度反馈（桌面版为不确定进度条 `setRange(0,0)`，非假进度）

另注：`desktop/` 中真实存在的波形控件文件是 `widgets/ecg_plot.py`。
`PROJECT_REPORT.md` 曾引用 `desktop/widgets/waveform.py`，该文件**并不存在**，属既有文档 bug，修订时一并改正。
