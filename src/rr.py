"""R 峰位置 -> 前后 RR 间期（秒）及节律特征。

训练（prepare_data）与推理（inference）**必须**共用本模块。两侧各写一份是
最容易埋雷的地方：只要边界处理或归一化差一点点，训练与推理的特征分布就会漂移，
表现为「离线指标尚可、在线推理全错」，而且很难排查。

为什么需要节律特征
------------------
单导联单搏的形态无法区分「室上性早搏」与「正常搏动」——二者的 QRS 几乎同形，
真正把 S 类区分开的是它「提前出现」这一节律事实。实测只用形态特征时，模型只能
按类别先验"猜"出大致数量的 S 搏，却指不到正确的位置（预测 1828 个 S，其中仅 44 个正确）。

为什么还要用「相对基线」的比值
------------------------------
各记录基础心率差异很大（本项目 44 条记录的中位 RR 从 0.53 s 到 1.20 s，即 50-112 bpm），
绝对 RR 秒数被基线高低污染：同样是 0.8 s，在慢心率记录里算正常，在快心率记录里
已属明显提前。改用「本记录 RR 中位数」作基线后区分度实测提升明显
（V vs N 的 AUC 由 0.615 升到 0.811）。
"""
from __future__ import annotations

import numpy as np

from . import config as C


def rr_pair_seconds(positions) -> tuple[np.ndarray, np.ndarray, float]:
    """由 R 峰位置序列算出每条搏动的 (前 RR, 后 RR)（秒）及本记录基线。

    边界处理：首搏没有「前一个 RR」、末搏没有「后一个 RR」，用可用的那一侧顶替，
    避免引入无意义的零值造成分布偏移。基线取全部相邻间隔的中位数。
    """
    pos = np.asarray(positions, dtype=np.float64)
    n = len(pos)

    if n == 0:
        return np.empty(0), np.empty(0), C.RR_MAX_SEC
    if n == 1:
        # 单搏记录无从计算间隔，用生理上限当作中性值
        return np.array([C.RR_MAX_SEC]), np.array([C.RR_MAX_SEC]), C.RR_MAX_SEC

    gaps = np.diff(pos) / C.FS                       # 相邻 R 峰间隔（秒）
    prev = np.empty(n, dtype=np.float64)
    nxt = np.empty(n, dtype=np.float64)
    prev[1:] = gaps
    prev[0] = gaps[0]                                # 首搏沿用第一个间隔
    nxt[:-1] = gaps
    nxt[-1] = gaps[-1]                               # 末搏沿用最后一个间隔

    median = float(np.median(gaps))
    if not np.isfinite(median) or median <= 0:
        median = C.RR_MAX_SEC
    return prev, nxt, median


def rr_feature_matrix(positions) -> np.ndarray:
    """(N, RR_DIM) 节律特征矩阵，供模型节律分支使用。"""
    prev, nxt, median = rr_pair_seconds(positions)
    if len(prev) == 0:
        return np.zeros((0, C.RR_DIM), dtype=np.float32)
    return np.asarray(
        [C.rr_feature_vector(p, q, median) for p, q in zip(prev, nxt)],
        dtype=np.float32,
    )
