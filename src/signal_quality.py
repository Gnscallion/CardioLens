"""轻量 ECG 文件预检：不做诊断，只评估能否进入后续分析流程。"""
from __future__ import annotations
import io
import numpy as np

def parse_signal(raw: bytes) -> np.ndarray:
    text = raw.decode('utf-8-sig', errors='ignore')
    vals = []
    for line in io.StringIO(text):
        for token in line.replace(';', ',').split(','):
            token = token.strip()
            if not token:
                continue
            try: vals.append(float(token))
            except ValueError:
                continue
    if len(vals) < 360 * 3:
        raise ValueError('文件中至少需要 3 秒的数值型 ECG 信号（按 360 Hz 计算）')
    arr = np.asarray(vals, dtype=np.float32)
    if not np.isfinite(arr).all():
        raise ValueError('信号包含无效数值')
    return arr

def assess(signal: np.ndarray, fs: int = 360) -> dict:
    diff = np.diff(signal)
    scale = float(np.std(signal))
    jump = float(np.percentile(np.abs(diff), 99.5)) if len(diff) else 0
    clipped = int(np.sum(np.abs(signal - np.median(signal)) > max(scale * 8, 1e-6)))
    noise_ratio = min(1.0, jump / max(scale * 3, 1e-6)) if scale else 1.0
    flags = []
    if scale < 1e-5: flags.append('振幅几乎为零')
    if noise_ratio > 0.8: flags.append('高频跳变或噪声较多')
    if clipped > len(signal) * 0.01: flags.append('疑似存在饱和或异常尖峰')
    quality = 'good' if not flags else ('poor' if len(flags) > 1 else 'warning')
    return {'quality': quality, 'quality_label': {'good':'信号质量良好','warning':'信号质量需关注','poor':'信号质量较差'}[quality], 'n_samples': int(len(signal)), 'duration_sec': round(len(signal)/fs, 2), 'mean': round(float(np.mean(signal)), 5), 'std': round(scale, 5), 'noise_ratio': round(noise_ratio, 4), 'flags': flags}
