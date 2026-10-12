"""数据准备：载入 MIT-BIH 心电数据库 -> 带通滤波 -> 按 AAMI 标准切分心搏。

数据来源
--------
PhysioNet 的 MIT-BIH Arrhythmia Database（48 条双导联 30 分钟心电记录，
由心电专家逐搏标注）。本项目使用其 HuggingFace 完整镜像
``epr-labs/mit-bih-arrhythmia-database``：该镜像完整保留了原始信号、R 峰
位置与标注符号，且从国内可高速下载（原站直连约 10 KB/s，镜像可达 400 KB/s 以上）。

产物
----
data/processed/beats.npz         训练用搏动片段 (X, y, rec, split)
data/processed/record_meta.json  各记录统计信息（前端展示）
data/processed/signals/{rec}.npy 滤波后整段信号（前端画波形）
data/processed/annots/{rec}.json 专家标注（R 峰位置 + AAMI 类别）

用法
----
python -m src.prepare_data            # 已生成则跳过
python -m src.prepare_data --force    # 强制重新生成
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from collections import Counter

import numpy as np
from scipy import signal as sp_signal

from . import config as C
from .rr import rr_feature_matrix

# de Chazal 等人提出的 inter-patient 划分方案：
# 训练集与测试集的患者（记录）完全不重叠，比随机切分更贴近真实的跨患者场景。
DS1 = {"101", "106", "108", "109", "112", "114", "115", "116", "118", "119",
       "122", "124", "201", "203", "205", "207", "208", "209", "215", "220",
       "223", "230"}
DS2 = {"100", "103", "105", "111", "113", "117", "121", "123", "200", "202",
       "210", "212", "213", "214", "219", "221", "222", "228", "231", "232",
       "233", "234"}

RECORD_LIST = sorted(DS1 | DS2)


# ------------------------------------------------------------------ 数据获取
def ensure_dataset(force: bool = False) -> None:
    """确保 MIT-BIH 数据文件已就绪，缺失时从镜像下载。"""
    if C.MITDB_PARQUET.exists() and not force:
        size_mb = C.MITDB_PARQUET.stat().st_size / 1e6
        print(f"[数据] 已存在：{C.MITDB_PARQUET}（{size_mb:.1f} MB）")
        return

    C.MITDB_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    print(f"[数据] 正在下载 MIT-BIH（约 87 MB）...\n       {C.MITDB_URL}")

    tmp = C.MITDB_PARQUET.with_suffix(".part")
    try:
        with urllib.request.urlopen(C.MITDB_URL, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(1 << 18)      # 256 KB
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"       {done / 1e6:6.1f} / {total / 1e6:.1f} MB "
                              f"({done / total * 100:5.1f}%)", end="\r")
        print()
        tmp.replace(C.MITDB_PARQUET)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"[数据] 下载失败：{e}\n"
            f"       可手动下载后放到 {C.MITDB_PARQUET}\n"
            f"       下载地址：{C.MITDB_URL}"
        )
    print(f"[数据] 完成：{C.MITDB_PARQUET}")


def load_records():
    """读取 parquet，逐条产出 (记录编号, 双导联信号, R峰位置, 标注符号)。

    该 parquet 的两处存储细节需要注意：
      * ``header`` 是 JSON 字符串（含 record_name / fs / sig_name 等），非 WFDB 文本；
      * ``signals`` 在 pandas 中是 object 数组，每个元素是一条采样点的多导联数组，
        实测经 ``tolist()`` 再转 ndarray 比 ``np.stack`` 快约 7 倍。
    """
    import json

    import pandas as pd

    df = pd.read_parquet(C.MITDB_PARQUET)
    for _, row in df.iterrows():
        rec_id = str(json.loads(row["header"])["record_name"]).strip()
        sig = np.array(row["signals"].tolist(), dtype=np.float32)   # (n_samples, n_leads)
        samples = np.asarray(row["annotation_sample"], dtype=np.int64)
        symbols = [str(s) for s in row["annotation_symbol"]]
        yield rec_id, sig, samples, symbols


# ------------------------------------------------------------------ 信号处理
def bandpass_filter(sig: np.ndarray) -> np.ndarray:
    """0.5-45 Hz Butterworth 带通滤波，抑制基线漂移与高频噪声。"""
    nyq = 0.5 * C.FS
    b, a = sp_signal.butter(
        3, [C.BANDPASS_LOW / nyq, C.BANDPASS_HIGH / nyq], btype="band"
    )
    return sp_signal.filtfilt(b, a, sig).astype(np.float32)


def normalize_beat(beat: np.ndarray) -> np.ndarray:
    """单搏 z-score 标准化；标准差为 0 时退化为去均值。"""
    std = float(beat.std())
    if std < 1e-8:
        return (beat - beat.mean()).astype(np.float32)
    return ((beat - beat.mean()) / std).astype(np.float32)


def rr_features(positions: np.ndarray) -> np.ndarray:
    """由 R 峰位置序列计算节律特征 (N, RR_DIM)。

    具体算法与设计理由见 src/rr.py —— 那里是与推理侧共用的唯一实现，
    本函数只是转发，避免两侧各写一份导致特征漂移。
    """
    return rr_feature_matrix(positions)


def process_record(rec_id: str, sig: np.ndarray, samples: np.ndarray, symbols: list[str]):
    """对单条记录做滤波与切分，返回 (搏动片段, 标签, 样本位置, 节律特征, 滤波信号, 统计)。"""
    if sig.ndim != 2 or sig.shape[1] <= C.CHANNEL:
        return None

    raw = sig[:, C.CHANNEL].astype(np.float32)
    # 个别记录存在电极脱落造成的 NaN，用线性插值补齐
    bad = ~np.isfinite(raw)
    if bad.any():
        idx = np.arange(len(raw))
        raw[bad] = np.interp(idx[bad], idx[~bad], raw[~bad])

    filtered = bandpass_filter(raw)
    n_sig = len(filtered)

    beats, labels, positions = [], [], []
    for sample, symbol in zip(samples, symbols):
        aami = C.MITDB_TO_AAMI.get(symbol)
        if aami is None:
            continue
        sample = int(sample)
        if sample < C.PRE_SAMPLES or sample + C.POST_SAMPLES > n_sig:
            continue
        seg = filtered[sample - C.PRE_SAMPLES: sample + C.POST_SAMPLES]
        beats.append(normalize_beat(seg))
        labels.append(C.AAMI_CLASSES.index(aami))
        positions.append(sample)

    beats = np.asarray(beats, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int64)
    positions = np.asarray(positions, dtype=np.int64)
    rr = rr_features(positions)

    meta = {
        "id": rec_id,
        "n_beats": int(len(beats)),
        "duration_sec": round(n_sig / C.FS, 1),
        "class_counts": {c: int(np.sum(labels == i)) for i, c in enumerate(C.AAMI_CLASSES)},
        "split": "DS1（训练/验证）" if rec_id in DS1 else "DS2（测试）",
    }
    return beats, labels, positions, rr, filtered, meta


# ------------------------------------------------------------------ 主流程
def main(force: bool = False) -> None:
    C.force_utf8_stdout()
    ensure_dataset()

    C.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    C.SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
    (C.DATA_PROCESSED / "annots").mkdir(parents=True, exist_ok=True)

    if C.BEATS_NPZ.exists() and not force:
        print(f"[处理] 已存在 {C.BEATS_NPZ}，跳过。使用 --force 重新生成。")
        return

    wanted = set(RECORD_LIST)
    all_beats, all_labels, all_rec, all_split, all_rr = [], [], [], [], []
    metas, seen = [], set()

    for i, (rec_id, sig, samples, symbols) in enumerate(load_records(), 1):
        if rec_id not in wanted:
            print(f"[{i:2d}] 记录 {rec_id} 不在 DS1/DS2 划分内，跳过")
            continue
        seen.add(rec_id)

        if rec_id in C.EXCLUDED_RECORDS:
            print(f"[{i:2d}] 记录 {rec_id} 起搏搏动标注存在争议，按 AAMI 惯例剔除")
            continue

        out = process_record(rec_id, sig, samples, symbols)
        if out is None or len(out[0]) == 0:
            print(f"[{i:2d}] 记录 {rec_id} 无有效搏动，跳过")
            continue

        beats, labels, positions, rr, filtered, meta = out
        np.save(C.SIGNAL_DIR / f"{rec_id}.npy", filtered)
        (C.DATA_PROCESSED / "annots" / f"{rec_id}.json").write_text(
            json.dumps(
                [{"sample": int(p), "aami": C.AAMI_CLASSES[int(l)]}
                 for p, l in zip(positions, labels)],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        all_beats.append(beats)
        all_labels.append(labels)
        all_rr.append(rr)
        all_rec.append(np.array([rec_id] * len(beats)))
        all_split.append(np.array(["train" if rec_id in DS1 else "test"] * len(beats)))
        metas.append(meta)

        dist = " ".join(f"{k}={v}" for k, v in meta["class_counts"].items() if v)
        print(f"[{i:2d}] 记录 {rec_id}: {len(beats):5d} 搏  {dist}")

    missing = wanted - seen
    if missing:
        print(f"[警告] 以下记录未在数据源中找到：{sorted(missing)}")
    if not all_beats:
        raise SystemExit("[错误] 未提取到任何心搏，请检查数据文件是否完整")

    X = np.concatenate(all_beats)
    y = np.concatenate(all_labels)
    rec = np.concatenate(all_rec)
    split = np.concatenate(all_split)
    R = np.concatenate(all_rr)
    np.savez_compressed(C.BEATS_NPZ, X=X, y=y, rec=rec, split=split, R=R)

    overall = Counter(C.AAMI_CLASSES[i] for i in y)
    payload = {
        "records": metas,
        "classes": [
            {"code": c, "name": C.CLASS_NAMES_ZH[c], "desc": C.CLASS_DESC[c]}
            for c in C.AAMI_CLASSES
        ],
        "total_beats": int(len(y)),
        "class_totals": {c: int(overall.get(c, 0)) for c in C.AAMI_CLASSES},
        "n_train": int(np.sum(split == "train")),
        "n_test": int(np.sum(split == "test")),
        "source": "MIT-BIH Arrhythmia Database (PhysioNet) · HF 镜像 epr-labs/mit-bih-arrhythmia-database",
    }
    C.RECORD_META.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[完成] 共 {len(y)} 个心搏片段，特征维度 {X.shape[1]}")
    print(f"       训练集 {payload['n_train']} / 测试集 {payload['n_test']}")
    print(f"       类别分布 {dict(overall)}")
    print(f"       已写入 {C.BEATS_NPZ}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="准备 MIT-BIH 心电数据")
    ap.add_argument("--force", action="store_true", help="强制重新生成")
    main(force=ap.parse_args().force)
