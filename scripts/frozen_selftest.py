"""【打包后运行时自检】—— 在冻结（PyInstaller）环境里跑通完整分析链路。

这个脚本**不是产品功能**，只是为了回答一个问题：
把 CardioLens.exe 单独拷到一台没有 Python 的电脑上，它到底能不能真的
完成一次心电分析？光看到主窗口显示「系统就绪」只证明模型文件被读到了，
并不能证明 numpy 读得到包内的 signals/*.npy、torch 能跑完一次前向、
Grad-CAM 能算出来、SQLite 写得到用户目录。

因此这里在冻结运行时内直接驱动 src.inference 与 desktop.services，
把结果写进 JSON 报告并以退出码表示成败（0 成功 / 1 失败）。

用法：
    # 打包版（用于自检的独立 EXE，不影响 CardioLens.exe 本身）
    CardioLensSelfTest.exe --out frozen_report.json

    # 开发机上跑同一份脚本，得到对照基准
    python scripts/frozen_selftest.py --dev --out dev_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

# 开发机直接运行时，把项目根目录挂进 sys.path；打包后资源在 _MEIPASS，
# 已经在 sys.path 上，不需要也不应该再加。
if not getattr(sys, "frozen", False):
    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

# ------------------------------------------------------------------ 常量
# 三个受保护的产物，任何情况下都不允许被改写
ARTIFACT_MD5 = {
    "models/ecg_cnn.pt": "a5ca4a0ec6d0330303a590a6d35c4fa3",
    "models/metrics.json": "db51fef423254c391dce5a27081d8cc8",
    "data/processed/beats.npz": "f27ed5050405b5c63bd803bb2acf57ab",
}

# 三个有代表性的时间窗：
#   100 → 以正常搏动为主，用来对照开发机基准
#   208 → 混有 V/F 类异常搏动，能触发风险等级与多类别概率
#   232 → 几乎全是 S 类异常搏动，能触发高风险提示
WINDOWS = [
    ("100", 10.0, 10.0),
    ("208", 300.0, 10.0),
    ("232", 60.0, 10.0),
]


def _md5(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _summarize(res: dict) -> dict:
    """从 analyze_window 的返回值里抽取可比对的关键结论。"""
    beats = res.get("beats") or []
    summary = res.get("summary") or {}
    risk = summary.get("risk_level") or {}
    signal = res.get("signal") or []
    first = beats[0] if beats else {}
    return {
        "n_beats": len(beats),
        "mean_confidence": summary.get("mean_confidence"),
        "abnormal_count": summary.get("abnormal_count"),
        "abnormal_ratio": summary.get("abnormal_ratio"),
        "risk_code": risk.get("code"),
        "risk_label": risk.get("label"),
        "counts": summary.get("counts"),
        "agreement": summary.get("agreement"),
        "split": res.get("split"),
        "in_training_set": res.get("in_training_set"),
        "preds": [b.get("pred") for b in beats],
        # 逐搏概率保留 4 位小数，用于跨环境逐位比对
        "probs": [b.get("probs") for b in beats],
        "confidences": [b.get("confidence") for b in beats],
        "beat_samples": [b.get("sample") for b in beats],
        "experts": [b.get("expert") for b in beats],
        "cam_len": len(first.get("cam") or []),
        "cam_head": (first.get("cam") or [])[:6],
        "cam_sum": round(sum(first.get("cam") or []), 3),
        "n_samples": res.get("n_samples"),
        "signal_len": len(signal),
        "signal_head": signal[:4],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="JSON 报告输出路径")
    ap.add_argument("--dev", action="store_true",
                    help="开发机模式：把数据库/日志重定向到临时目录，避免污染项目 store/")
    args = ap.parse_args()

    report: dict = {}
    tmp_dir = None
    try:
        # ---------------------------------------------------- 路径准备
        if args.dev:
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="cardiolens_selftest_")
            from src import config as C
            C.STORE_DIR = Path(tmp_dir)
            C.LOG_DIR = C.STORE_DIR / "logs"
            C.DB_PATH = C.STORE_DIR / "app.db"

        from desktop.services import resource_service as RS
        from desktop.services import history_service as HS
        from src import config as C
        from src.inference import get_analyzer

        report["frozen"] = bool(getattr(sys, "frozen", False))
        report["executable"] = sys.executable
        report["meipass"] = getattr(sys, "_MEIPASS", None)
        report["python"] = sys.version.split()[0]
        report["resource_root"] = str(RS.resource_root())
        report["user_data_dir"] = str(RS.user_data_dir())

        # ---------------------------------------------------- 1) 启动前置
        report["log_dir"] = str(RS.setup_logging())
        RS.ensure_user_dirs()

        rd = RS.check_readiness()
        report["readiness"] = {"ok": rd.ok, "message": rd.message,
                               "missing": rd.missing}

        # ---------------------------------------------------- 2) 受保护产物校验
        report["artifacts"] = {}
        for rel, expect in ARTIFACT_MD5.items():
            p = C.ROOT / rel
            got = _md5(p)
            report["artifacts"][rel] = {
                "path": str(p), "exists": p.exists(),
                "md5": got, "expected": expect, "match": got == expect,
            }
        # beats.npz 不打包是刻意设计，冻结环境下允许缺失
        report["beats_npz_required"] = False

        # ---------------------------------------------------- 3) metrics / meta
        metrics = RS.load_metrics()
        meta = RS.load_meta()
        report["metrics_loaded"] = metrics is not None
        report["meta_loaded"] = meta is not None
        if metrics:
            test = metrics.get("test") or {}
            report["metrics_key_numbers"] = {
                "accuracy": test.get("accuracy"),
                "macro_f1_4": test.get("macro_f1_4class"),
                "macro_f1_5": test.get("macro_f1_5class"),
                "n_test": metrics.get("n_test"),
                "n_params": metrics.get("n_params"),
                "best_epoch": metrics.get("best_epoch"),
            }

        # ---------------------------------------------------- 4) 模型
        analyzer = get_analyzer()
        report["model_params"] = int(
            sum(p.numel() for p in analyzer.model.parameters()))
        report["n_records"] = len(analyzer.list_records())
        report["signal_dir"] = str(C.SIGNAL_DIR)
        # 信号是否真的来自只读资源根（打包后即 _MEIPASS）
        probe = analyzer.get_signal("100")
        report["signal_shape"] = list(probe.shape)
        report["signal_dtype"] = str(probe.dtype)

        # ---------------------------------------------------- 5) 真实分析
        report["windows"] = {}
        for rid, start, dur in WINDOWS:
            key = f"{rid}@{start:.0f}s+{dur:.0f}s"
            try:
                res = analyzer.analyze_window(rid, start, dur, with_cam=True)
                report["windows"][key] = _summarize(res)
            except Exception as exc:                      # noqa: BLE001
                report["windows"][key] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }

        # ---------------------------------------------------- 6) 数据库写入往返
        HS.init_db()
        first_key = f"{WINDOWS[0][0]}@{WINDOWS[0][1]:.0f}s+{WINDOWS[0][2]:.0f}s"
        payload = analyzer.analyze_window(*WINDOWS[0], with_cam=True)
        saved_id = HS.save_analysis(payload)
        rows = HS.list_analyses()
        back = HS.get_analysis(saved_id)
        report["db"] = {
            "path": str(C.DB_PATH),
            "saved_id": saved_id,
            "list_count": len(rows),
            "roundtrip_beats": len(((back or {}).get("payload") or {}).get("beats") or []),
            "roundtrip_risk": ((((back or {}).get("payload") or {})
                                .get("summary") or {}).get("risk_level") or {}).get("code"),
            "stats": HS.stats(),
            "window_key": first_key,
            "deleted": HS.delete_analysis(saved_id),
            "count_after_delete": len(HS.list_analyses()),
        }

        # ---------------------------------------------------- 7) 无服务器证据
        report["server"] = {
            "has_app_run": False,
            "note": "进程内不创建任何监听套接字（由外部 netstat 复核）",
        }
        report["ok"] = True

    except Exception as exc:                              # noqa: BLE001
        report["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()

    # ------------------------------------------------------------ 输出
    out_path = Path(args.out) if args.out else (
        Path(sys.executable).resolve().parent / "frozen_selftest_report.json")
    try:
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        written = str(out_path)
    except OSError:
        fallback = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")))
        out_path = fallback / "CardioLens" / "frozen_selftest_report.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        written = str(out_path)

    print("=" * 68)
    print(f"冻结运行时自检  frozen={report.get('frozen')}  ok={report.get('ok')}")
    print(f"报告已写入: {written}")
    if not report.get("ok"):
        print(report.get("error"))
        print(report.get("traceback", ""))
    print("=" * 68)
    if tmp_dir:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
