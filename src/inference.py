"""推理引擎：把一段心电信号变成一份逐搏分析报告。

对外主入口是 ECGAnalyzer.analyze_window(record_id, start_sec, duration_sec)，
返回结构直接供 Flask 接口序列化为 JSON。
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache

import numpy as np
import torch

from . import config as C
from .gradcam import GradCAM1D
from .model import build_model
from .rr import rr_pair_seconds

# 一次分析窗口的长度上限（秒），防止前端传入超大区间拖垮服务
MAX_WINDOW_SEC = 30.0
MIN_WINDOW_SEC = 3.0


class AnalysisError(Exception):
    """输入不合法或无法分析时抛出，由 Flask 层转成 400 响应。"""


def _round(arr, nd: int = 4) -> list[float]:
    return [round(float(v), nd) for v in np.asarray(arr).ravel()]


def build_rr_table(annots: list[dict]) -> dict[int, dict]:
    """为每条标注搏动计算前后 RR 间期，供节律分支使用。

    算法与训练侧共用 src/rr.py，这里只负责组织成按 R 峰位置索引的表。
    两个容易踩的坑，都由共用实现保证不出现：
      * 用整条记录的标注序列计算，而不是只用窗口内的搏动——
        窗口内首搏的"前一个 RR"必须回溯到窗口外的上一次心搏才算得准
      * 「相对基线」的比值要用整条记录的中位 RR 作分母，不能只用窗口内的
    """
    pos = [int(a["sample"]) for a in annots]
    prev, nxt, median = rr_pair_seconds(pos)
    table: dict[int, dict] = {}
    for i, p in enumerate(pos):
        table[p] = {
            "prev_sec": round(float(prev[i]), 3),
            "next_sec": round(float(nxt[i]), 3),
            "baseline_sec": round(float(median), 3),
            "prev_ratio": round(float(prev[i]) / median, 3) if median > 0 else 1.0,
            "next_ratio": round(float(nxt[i]) / median, 3) if median > 0 else 1.0,
            "feat": C.rr_feature_vector(float(prev[i]), float(nxt[i]), median),
        }
    return table


class ECGAnalyzer:
    """封装模型加载、信号缓存与窗口分析。进程内单例使用。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._cam = None
        self._meta = None
        self._signal_cache: dict[str, np.ndarray] = {}
        self._annot_cache: dict[str, list] = {}

    # ------------------------------------------------------------ 资源加载
    @property
    def model(self):
        if self._model is None:
            if not C.MODEL_PATH.exists():
                raise AnalysisError(
                    "模型文件不存在，请先运行训练脚本：python -m src.train"
                )
            net = build_model()
            ckpt = torch.load(C.MODEL_PATH, map_location="cpu")
            net.load_state_dict(ckpt["state_dict"])
            net.eval()
            self._model = net
            self._cam = GradCAM1D(net)
        return self._model

    @property
    def meta(self) -> dict:
        if self._meta is None:
            if not C.RECORD_META.exists():
                raise AnalysisError(
                    "数据元信息不存在，请先运行：python -m src.prepare_data"
                )
            self._meta = json.loads(C.RECORD_META.read_text(encoding="utf-8"))
        return self._meta

    def is_ready(self) -> tuple[bool, str]:
        if not C.BEATS_NPZ.exists() or not C.RECORD_META.exists():
            return False, "数据未准备，请运行 python -m src.prepare_data"
        if not C.MODEL_PATH.exists():
            return False, "模型未训练，请运行 python -m src.train"
        return True, "就绪"

    # ------------------------------------------------------------ 信号读取
    def list_records(self) -> list[dict]:
        note = {d["id"]: d for d in C.DEMO_RECORDS}
        out = []
        for r in self.meta["records"]:
            rid = r["id"]
            out.append({
                **r,
                "label": f"记录 {rid}",
                "note": note.get(rid, {}).get("note", ""),
                "recommended": rid in note,
            })
        # 推荐记录排在前面，其余按编号
        out.sort(key=lambda x: (not x["recommended"], x["id"]))
        return out

    def get_signal(self, record_id: str) -> np.ndarray:
        if record_id not in self._signal_cache:
            path = C.SIGNAL_DIR / f"{record_id}.npy"
            if not path.exists():
                raise AnalysisError(f"记录 {record_id} 的信号数据不存在")
            self._signal_cache[record_id] = np.load(path)
        return self._signal_cache[record_id]

    def get_annots(self, record_id: str) -> list[dict]:
        if record_id not in self._annot_cache:
            path = C.DATA_PROCESSED / "annots" / f"{record_id}.json"
            if not path.exists():
                raise AnalysisError(f"记录 {record_id} 的标注数据不存在")
            self._annot_cache[record_id] = json.loads(path.read_text(encoding="utf-8"))
        return self._annot_cache[record_id]

    def valid_ids(self) -> set[str]:
        return {r["id"] for r in self.meta["records"]}

    # ------------------------------------------------------------ 核心分析
    def analyze_window(self, record_id: str, start_sec: float, duration_sec: float,
                       with_cam: bool = True) -> dict:
        record_id = str(record_id).strip()
        s0, s1, segment = self._resolve_window(record_id, start_sec, duration_sec)

        # 该记录属于训练集还是测试集。训练集记录模型见过，其"与专家标注一致率"
        # 不能当作泛化能力，必须如实告诉用户，避免把演示效果误读为模型真实水平。
        rec_meta = next((r for r in self.meta["records"] if r["id"] == record_id), {})
        split = rec_meta.get("split", "")
        in_training_set = split.startswith("DS1")

        annots = self.get_annots(record_id)
        in_win = [a for a in annots if s0 + C.PRE_SAMPLES <= a["sample"] and a["sample"] + C.POST_SAMPLES <= s1]
        if not in_win:
            raise AnalysisError(
                "该时间窗内未检测到有效心搏，请调整起始时间或延长分析时长"
            )

        beats = np.stack([
            self._normalize(segment[a["sample"] - s0 - C.PRE_SAMPLES: a["sample"] - s0 + C.POST_SAMPLES])
            for a in in_win
        ]).astype(np.float32)

        rr_table = build_rr_table(annots)
        rr = np.asarray([rr_table[a["sample"]]["feat"] for a in in_win], dtype=np.float32)

        with self._lock:
            self.model  # 确保模型已加载
            x = torch.from_numpy(beats[:, None, :])
            rb = torch.from_numpy(rr)
            with torch.no_grad():
                logits = self._model(x, rb)
                probs = torch.softmax(logits, dim=1).numpy()
            preds = probs.argmax(axis=1)

            cams = None
            if with_cam:
                try:
                    cams = self._cam.generate(x, torch.from_numpy(preds), rb)
                except Exception:
                    cams = None      # Grad-CAM 失败不应阻断主流程

        # -------- 组装逐搏结果
        beat_results = []
        for i, a in enumerate(in_win):
            p = int(preds[i])
            code = C.AAMI_CLASSES[p]
            rel = a["sample"] - s0
            entry = {
                "index": i + 1,
                "sample": int(rel),
                "time_sec": round(rel / C.FS, 3),
                "abs_sample": int(a["sample"]),
                "pred": code,
                "pred_name": C.CLASS_NAMES_ZH[code],
                "confidence": round(float(probs[i, p]), 4),
                "probs": {C.AAMI_CLASSES[k]: round(float(probs[i, k]), 4)
                          for k in range(len(C.AAMI_CLASSES))},
                "expert": a["aami"],
                "expert_name": C.CLASS_NAMES_ZH[a["aami"]],
                "agree": bool(code == a["aami"]),
                "risk": C.CLASS_RISK[code],
                # 节律特征回传前端展示，让"为什么判为早搏"有据可查
                "rr_prev_sec": rr_table[a["sample"]]["prev_sec"],
                "rr_next_sec": rr_table[a["sample"]]["next_sec"],
                "rr_baseline_sec": rr_table[a["sample"]]["baseline_sec"],
                "rr_prev_ratio": rr_table[a["sample"]]["prev_ratio"],
                "rr_next_ratio": rr_table[a["sample"]]["next_ratio"],
            }
            if cams is not None:
                entry["cam"] = _round(cams[i], 3)
            beat_results.append(entry)

        counts = {c: 0 for c in C.AAMI_CLASSES}
        for b in beat_results:
            counts[b["pred"]] += 1
        n = len(beat_results)
        abnormal = n - counts["N"]

        agree = sum(1 for b in beat_results if b["agree"])
        summary = {
            "n_beats": n,
            "counts": counts,
            "counts_zh": {C.CLASS_NAMES_ZH[c]: counts[c] for c in C.AAMI_CLASSES},
            "abnormal_count": abnormal,
            "abnormal_ratio": round(abnormal / n, 4),
            "agreement": round(agree / n, 4),
            "mean_confidence": round(float(np.mean([b["confidence"] for b in beat_results])), 4),
            "risk_level": self._risk_level(counts, n),
        }

        payload = {
            "record_id": record_id,
            "start_sec": round(s0 / C.FS, 2),
            "duration_sec": round((s1 - s0) / C.FS, 2),
            "fs": C.FS,
            "signal": _round(segment, 4),
            "n_samples": int(len(segment)),
            "beats": beat_results,
            "summary": summary,
            "split": split,
            "in_training_set": in_training_set,
            "classes": [
                {"code": c, "name": C.CLASS_NAMES_ZH[c], "desc": C.CLASS_DESC[c]}
                for c in C.AAMI_CLASSES
            ],
            "disclaimer": C.DISCLAIMER,
        }
        return payload

    def preview_window(self, record_id: str, start_sec: float, duration_sec: float) -> dict:
        """只取波形与专家标注位置，用于分析前的波形预览。"""
        record_id = str(record_id).strip()
        s0, s1, segment = self._resolve_window(record_id, start_sec, duration_sec)
        annots = self.get_annots(record_id)
        marks = [
            {"sample": int(a["sample"] - s0), "aami": a["aami"],
             "name": C.CLASS_NAMES_ZH[a["aami"]]}
            for a in annots
            if s0 <= a["sample"] < s1
        ]
        return {
            "record_id": record_id,
            "start_sec": round(s0 / C.FS, 2),
            "duration_sec": round((s1 - s0) / C.FS, 2),
            "fs": C.FS,
            "signal": _round(segment, 4),
            "beat_marks": marks,
            "n_beats_in_window": len(marks),
        }

    # ------------------------------------------------------------ 内部工具
    def _resolve_window(self, record_id: str, start_sec, duration_sec):
        """校验参数并返回窗口 (起止采样点, 信号片段)。"""
        if record_id not in self.valid_ids():
            raise AnalysisError(f"记录编号 {record_id} 不存在，请从有效列表中选择")

        try:
            start_sec = float(start_sec)
            duration_sec = float(duration_sec)
        except (TypeError, ValueError):
            raise AnalysisError("起始时间与时长必须为数字")

        if not np.isfinite(start_sec) or not np.isfinite(duration_sec):
            raise AnalysisError("起始时间与时长必须为有限数值")
        if duration_sec < MIN_WINDOW_SEC:
            raise AnalysisError(f"分析时长不得短于 {MIN_WINDOW_SEC:.0f} 秒")
        if duration_sec > MAX_WINDOW_SEC:
            raise AnalysisError(f"单次分析时长不得超过 {MAX_WINDOW_SEC:.0f} 秒")
        if start_sec < 0:
            raise AnalysisError("起始时间不能为负数")

        signal = self.get_signal(record_id)
        total_sec = len(signal) / C.FS
        if duration_sec > total_sec:
            raise AnalysisError(
                f"记录 {record_id} 总时长仅 {total_sec:.0f} 秒，无法截取 {duration_sec:.0f} 秒窗口"
            )
        # 超出末尾时向左回退，保证窗口长度不变
        if start_sec + duration_sec > total_sec:
            start_sec = max(0.0, total_sec - duration_sec)

        s0 = max(0, int(round(start_sec * C.FS)))
        s1 = min(len(signal), int(round((start_sec + duration_sec) * C.FS)))
        return s0, s1, signal[s0:s1]

    @staticmethod
    def _normalize(beat: np.ndarray) -> np.ndarray:
        std = float(beat.std())
        if std < 1e-8:
            return (beat - beat.mean()).astype(np.float32)
        return ((beat - beat.mean()) / std).astype(np.float32)

    @staticmethod
    def _risk_level(counts: dict, n: int) -> dict:
        """基于异常搏动占比给出提示等级（演示用，非临床分级标准）。"""
        abn = n - counts["N"]
        ratio = abn / max(n, 1)
        v_ratio = (counts["V"] + counts["F"]) / max(n, 1)

        if v_ratio >= 0.15 or ratio >= 0.30:
            code, label, color = "high", "异常搏动占比较高", "#dc2626"
            desc = "本段信号中室性/融合搏动或总体异常搏动比例较高，建议重点关注。"
        elif abn > 0:
            code, label, color = "medium", "存在少量异常搏动", "#d97706"
            desc = "本段信号中检出少量异位搏动，整体节律以正常搏动为主。"
        else:
            code, label, color = "low", "未见明显异常搏动", "#059669"
            desc = "本段信号内各心搏均被判定为正常搏动，未检出异位搏动。"

        return {
            "code": code, "label": label, "color": color, "desc": desc,
            "abnormal_ratio": round(ratio, 4),
            "ventricular_ratio": round(v_ratio, 4),
        }


@lru_cache(maxsize=1)
def get_analyzer() -> ECGAnalyzer:
    return ECGAnalyzer()
