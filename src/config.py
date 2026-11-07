"""全局配置：路径、信号参数、AAMI 标注映射。

MIT-BIH 心律失常数据库 (mitdb) 的原始标注符号共 15+ 种，学术上通常按
AAMI EC57 标准归并为 5 大类，本项目沿用该归并方式。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------- 路径
# 只读资源（模型、心电数据）与可写数据（数据库、日志）分开存放：
#   * 只读资源随代码走，部署时可整体只读；
#   * 可写数据默认落在项目根的 store/，生产部署用环境变量 CARDIOLENS_STORE
#     显式指定（如 /var/lib/cardiolens），使代码目录无需写权限。


def _resource_root() -> Path:
    """只读资源根目录（模型、心电数据）。"""
    return Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    """可写数据目录（SQLite 数据库、日志）。

    生产部署建议显式设置 CARDIOLENS_STORE 指向持久化卷；不设置时
    落在代码目录下的 store/，适用于开发与单机运行。
    """
    env = os.environ.get("CARDIOLENS_STORE")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "store"


ROOT = _resource_root()
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
SIGNAL_DIR = DATA_PROCESSED / "signals"
MODEL_DIR = ROOT / "models"
STORE_DIR = _user_data_dir()
LOG_DIR = STORE_DIR / "logs"

# 数据来源：PhysioNet MIT-BIH (mitdb) 的 HuggingFace 完整镜像。
# 原站 physionet.org 从国内直连速度仅约 10 KB/s（约 87 MB 的数据需数小时），
# 镜像站可稳定跑到 400 KB/s 以上，因此默认镜像下载。
MITDB_PARQUET = DATA_RAW / "hf" / "mitdb.parquet"
MITDB_URL = (
    "https://hf-mirror.com/datasets/epr-labs/mit-bih-arrhythmia-database/"
    "resolve/main/data/train-00000-of-00001.parquet"
)

BEATS_NPZ = DATA_PROCESSED / "beats.npz"
RECORD_META = DATA_PROCESSED / "record_meta.json"
MODEL_PATH = MODEL_DIR / "ecg_cnn.pt"
METRICS_PATH = MODEL_DIR / "metrics.json"
DB_PATH = STORE_DIR / "app.db"

# 历史记录时间的基准时区。created_at 是人类可读的本地时间字符串，服务端时区
# 一变，"3 分钟前"这类相对时间就会算错；因此写入与解析都显式使用本常量，
# 并额外提供 created_at_ts（epoch 秒）供前端计算相对时间。
TZ_NAME = "Asia/Shanghai"

# ---------------------------------------------------------------- 信号参数
FS = 360                 # MIT-BIH 采样率 360 Hz
CHANNEL = 0              # 统一读取第 0 个信号通道（各记录导联排列不完全一致，多为 MLII）
PRE_SAMPLES = 90         # R 峰前 0.25 s
POST_SAMPLES = 162       # R 峰后 0.45 s
BEAT_LEN = PRE_SAMPLES + POST_SAMPLES   # 252 采样点

# 带通滤波（去除基线漂移与工频噪声）
BANDPASS_LOW = 0.5
BANDPASS_HIGH = 45.0

# ---------------------------------------------------------------- 节律特征
# 仅靠单搏形态无法区分「室上性早搏」与「正常搏动」——二者的 QRS 在单导联上
# 几乎同形，真正把它们区分开的是「提前出现」这一节律信息（RR 间期）。
# 同理，融合搏动也需要前后 RR 作参考。因此额外输入前后 RR 间期（见下方比值特征）。
#
# 归一化采用固定区间线性映射（而非按数据集统计量标准化），
# 这样推理时无需依赖训练集统计量，单条记录也能独立计算。
RR_MIN_SEC = 0.24        # 生理下限，约对应 250 bpm
RR_MAX_SEC = 2.00        # 生理上限，约对应 30 bpm

# 除绝对秒数外，再补一对「相对基线」的比值特征。原因是各记录的基础心率差异
# 很大（本项目 44 条记录的中位 RR 从 0.53 s 到 1.20 s，即 50-112 bpm），
# 绝对 RR 被基线高低严重污染：同样是 0.8 s，在慢心率记录里算正常，在快心率
# 记录里已属明显提前。改用「本记录 RR 中位数」作基线后实测区分度提升明显
# （V vs N 的 AUC 由 0.615 升到 0.811）。
RR_RATIO_MIN = 0.25      # 相对基线的最短比值
RR_RATIO_MAX = 2.00      # 相对基线的最长比值
RR_FEATURE_NAMES = ("rr_prev_sec", "rr_next_sec", "rr_prev_ratio", "rr_next_ratio")
RR_DIM = len(RR_FEATURE_NAMES)   # (前 RR, 后 RR, 前 RR/基线, 后 RR/基线)


def normalize_rr(rr_sec: float) -> float:
    """把 RR 间期（秒）线性映射到 [0, 1]，超出上下限则截断。"""
    v = (float(rr_sec) - RR_MIN_SEC) / (RR_MAX_SEC - RR_MIN_SEC)
    return float(min(1.0, max(0.0, v)))


def normalize_rr_ratio(rr_sec: float, median_sec: float) -> float:
    """把 RR 间期相对本记录基线的比值映射到 [0, 1]。

    比值 1.0（与基线持平）映射到约 0.43，早搏的短 RR 落在低值区，
    代偿间歇的长 RR 落在高值区。基线不可用时返回 0.5（中性值）。
    """
    if not (median_sec > 0):
        return 0.5
    v = (float(rr_sec) / float(median_sec) - RR_RATIO_MIN) / (RR_RATIO_MAX - RR_RATIO_MIN)
    return float(min(1.0, max(0.0, v)))


def rr_feature_vector(rr_prev_sec: float, rr_next_sec: float, median_sec: float) -> list[float]:
    """把一对 RR 间期组装成模型输入的节律特征向量（长度 RR_DIM）。

    训练与推理必须共用本函数，否则两侧特征分布会漂移。
    """
    return [
        normalize_rr(rr_prev_sec),
        normalize_rr(rr_next_sec),
        normalize_rr_ratio(rr_prev_sec, median_sec),
        normalize_rr_ratio(rr_next_sec, median_sec),
    ]

# ---------------------------------------------------------------- AAMI 五分类
# 顺序即模型输出索引，务必与训练/推理保持一致
AAMI_CLASSES = ["N", "S", "V", "F", "Q"]
CLASS_NAMES_ZH = {
    "N": "正常搏动",
    "S": "室上性早搏",
    "V": "室性早搏",
    "F": "融合搏动",
    "Q": "未分类/起搏搏动",
}
CLASS_DESC = {
    "N": "窦性心律来源的正常心搏，包括左/右束支传导阻滞搏动。",
    "S": "起源位于心室以上的异位搏动，如期前房性早搏、交界性早搏。",
    "V": "起源于心室的异位搏动，如室性早搏、室性逸搏，临床关注度较高。",
    "F": "正常搏动与室性搏动融合形成，QRS 形态介于两者之间。",
    "Q": "无法归入上述类别的搏动，以及起搏器起搏/感知搏动。",
}
# 风险分级：用于结果页给出「提示等级」，仅作演示用途
CLASS_RISK = {"N": 0, "S": 1, "V": 2, "F": 2, "Q": 1}

# MIT-BIH 原始标注符号 -> AAMI 类别
MITDB_TO_AAMI = {
    "N": "N", "L": "N", "R": "N", "e": "N", "j": "N",
    "A": "S", "a": "S", "J": "S", "S": "S",
    "V": "V", "E": "V",
    "F": "F",
    "/": "Q", "f": "Q", "Q": "Q",
}

# 改进版训练保留起搏记录，让 Q 类至少出现在训练集和测试集。
# 原始基线仍保存在 models/baseline/，其中 Q 类按旧版 AAMI 过滤规则被剔除。
EXCLUDED_RECORDS: set[str] = set()

# ---------------------------------------------------------------- 展示用
# 项目名称集中在这里定义，模板与启动横幅统一引用，避免改名时漏掉某处。
APP_NAME = "CardioLens"
APP_NAME_ZH = "心电节律智能分析平台"
APP_NAME_EN = "ECG Rhythm Intelligent Analysis Platform"
APP_TAGLINE = "基于深度学习与可解释 AI 的心电节律智能分析平台"

DISCLAIMER = (
    "本系统用于公开 ECG 数据集上的科研实验与算法评估，所有分析结果均由机器学习模型自动生成，"
    "仅用于科研与辅助分析，不构成医疗诊断依据，不能用于任何临床决策。"
    "如有健康问题请及时就医并遵从专业医师意见。"
)

# 推荐演示记录：覆盖不同心律类型，便于展示模型区分能力
DEMO_RECORDS = [
    {"id": "100", "label": "记录 100", "note": "以正常窦性心律为主，含少量室性/室上性早搏"},
    {"id": "119", "label": "记录 119", "note": "室性早搏频繁，适合展示异常搏动识别"},
    {"id": "208", "label": "记录 208", "note": "室性早搏与室性心动过速节律并存"},
    {"id": "209", "label": "记录 209", "note": "房性早搏与室上性心动过速交替"},
    {"id": "233", "label": "记录 233", "note": "室性二联律，异常搏动占比高"},
    {"id": "222", "label": "记录 222", "note": "含融合搏动，用于展示 F 类判别"},
]


def force_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，打印中文/符号会抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
