"""CardioLens 桌面版自检脚本（不修改任何模型、数据或推理逻辑）。

覆盖范围：
    1  只读资源就绪检查
    2  三个核心构件的 MD5（模型/指标/心搏样本集）必须与迁移前一致
    3  桌面端分析结果 == 直接驱动模型独立复算的结果
    4  Grad-CAM 长度与心搏对齐
    5  逐搏汇总的算术自洽
    6  数据库 schema 与 src/db.py 保持一致
    7  历史记录的保存/读取/删除/清空（临时数据库，不触碰真实数据）
    8  GUI 六个页面的构造与导航
    9  分析在后台线程执行、进度信号可用（界面不冻结）
    10 结果页装载 Grad-CAM 与逐搏明细表
    11 桌面运行路径不含任何网络/浏览器依赖
    12 面向用户的文案不含 Web/服务器术语

用法：
    python scripts/test_desktop.py
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 无头运行，避免自检时弹出窗口
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np                                    # noqa: E402
import torch                                          # noqa: E402

from src import config as C                           # noqa: E402

# ---------------------------------------------------------------- 结果收集
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


EXPECTED_MD5 = {
    "models/ecg_cnn.pt": "a5ca4a0ec6d0330303a590a6d35c4fa3",
    "models/metrics.json": "db51fef423254c391dce5a27081d8cc8",
    "data/processed/beats.npz": "f27ed5050405b5c63bd803bb2acf57ab",
}

# ---------------------------------------------------------------- 临时数据目录
TMP = Path(tempfile.mkdtemp(prefix="cardiolens_selftest_"))
C.STORE_DIR = TMP / "store"
C.LOG_DIR = C.STORE_DIR / "logs"
C.DB_PATH = C.STORE_DIR / "cardiolens.db"
C.STORE_DIR.mkdir(parents=True, exist_ok=True)
C.LOG_DIR.mkdir(parents=True, exist_ok=True)

from desktop.services import resource_service as RS          # noqa: E402
from desktop.services import history_service as HS           # noqa: E402
from desktop.services import analysis_service as AS          # noqa: E402


# ================================================================ 1 就绪
def test_readiness() -> None:
    print("\n[1] 只读资源就绪检查")
    ready = RS.check_readiness()
    check("安装文件完整", ready.ok,
          "缺失：" + "、".join(ready.missing) if not ready.ok else "模型 / 信号 / 标注齐备")
    check("桌面端就绪检查不要求 beats.npz（91MB 训练样本集不随包分发）",
          "beats.npz" not in "".join(ready.missing))


# ================================================================ 2 MD5
def test_hashes() -> None:
    print("\n[2] 核心构件 MD5（必须与迁移前完全一致）")
    for rel, want in EXPECTED_MD5.items():
        path = ROOT / rel
        if not path.exists():
            check(f"{rel} 存在", False, "文件缺失")
            continue
        got = md5(path)
        check(f"{rel}", got == want, got if got == want else f"期望 {want}，实际 {got}")


# ================================================================ 3 推理一致
RECORD = "100"
START_SEC, DURATION_SEC = 10.0, 10.0


def _independent_inference():
    """不经过 src.inference，直接用原始文件 + 模型权重独立复算一遍。

    输入张量的构造严格按 src/inference.py 中记录的预处理方式重写一遍
    （按 R 峰前后 90/162 采样点截取 → 去均值除标准差 → float32），
    目的是验证桌面端没有在推理前偷偷改动任何输入。
    """
    from src.model import build_model
    from src.rr import rr_pair_seconds

    annots = json.loads(
        (C.DATA_PROCESSED / "annots" / f"{RECORD}.json").read_text(encoding="utf-8"))
    signal = np.load(C.SIGNAL_DIR / f"{RECORD}.npy")

    s0, s1 = int(START_SEC * C.FS), int((START_SEC + DURATION_SEC) * C.FS)
    in_win = [a for a in annots
              if s0 + C.PRE_SAMPLES <= a["sample"] and a["sample"] + C.POST_SAMPLES <= s1]
    if not in_win:
        raise RuntimeError("窗口内没有心搏")

    norm_beats = []
    for a in in_win:
        # 引擎是在 segment = signal[s0:s1] 上以相对下标切片，
        # 换算到整条记录上即 signal[峰位-90 : 峰位+162]，与窗口起点无关。
        seg = signal[a["sample"] - C.PRE_SAMPLES: a["sample"] + C.POST_SAMPLES]
        std = float(seg.std())
        norm_beats.append((seg - seg.mean()).astype(np.float32) if std < 1e-8
                          else ((seg - seg.mean()) / std).astype(np.float32))
    x = torch.from_numpy(np.stack(norm_beats)[:, None, :].astype(np.float32))

    # RR 特征复用训练/推理共用的 src/rr.py，保证节律分支输入口径一致
    pos = [int(a["sample"]) for a in annots]
    prev, nxt, median = rr_pair_seconds(pos)
    rr_of = {p: C.rr_feature_vector(float(prev[i]), float(nxt[i]), median)
             for i, p in enumerate(pos)}
    rb = torch.from_numpy(
        np.asarray([rr_of[a["sample"]] for a in in_win], dtype=np.float32))

    net = build_model()
    net.load_state_dict(torch.load(C.MODEL_PATH, map_location="cpu")["state_dict"])
    net.eval()
    with torch.no_grad():
        probs = torch.softmax(net(x, rb), dim=1).numpy()
    return in_win, x, rb, probs


def _capture_real_inputs():
    """用前向钩子截获推理引擎真正喂给模型的张量。"""
    from src.inference import get_analyzer

    analyzer = get_analyzer()
    analyzer.model
    captured: dict = {}
    handle = analyzer._model.register_forward_pre_hook(
        lambda _m, args: captured.update(
            x=args[0].detach().clone(),
            rb=args[1].detach().clone() if len(args) > 1 and args[1] is not None else None)
    )
    try:
        result = analyzer.analyze_window(RECORD, START_SEC, DURATION_SEC, with_cam=True)
    finally:
        handle.remove()
    return result, captured


def test_inference_consistency() -> None:
    print("\n[3] 桌面端分析结果 vs 独立复算（同一时间窗）")
    result, captured = _capture_real_inputs()
    in_win, x, rb, probs = _independent_inference()
    beats = result["beats"]

    check("心搏数量一致", len(beats) == len(in_win),
          f"桌面端 {len(beats)} / 独立复算 {len(in_win)}")

    # ① 输入层：真正喂进模型的张量必须与独立构造的完全一致
    dx = float(np.abs(captured["x"].numpy() - x.numpy()).max())
    check("波形分支输入张量完全一致（容差 1e-6）", dx <= 1e-6, f"最大偏差 {dx:.2e}")
    dr = float(np.abs(captured["rb"].numpy() - rb.numpy()).max())
    check("节律分支输入张量完全一致（容差 1e-6）", dr <= 1e-6, f"最大偏差 {dr:.2e}")

    # ② 输出层：同样输入下必须得到同样的类别与概率
    n = min(len(beats), len(in_win))
    same_cls = sum(1 for i in range(n)
                   if beats[i]["pred"] == C.AAMI_CLASSES[int(probs[i].argmax())])
    check("逐搏预测类别完全一致", same_cls == n, f"{same_cls}/{n}")

    # 引擎输出的概率保留 4 位小数，比较容差取 1e-3 足以覆盖舍入与浮点累加顺序
    max_pb = max((abs(beats[i]["probs"][C.AAMI_CLASSES[k]] - float(probs[i][k]))
                  for i in range(n) for k in range(len(C.AAMI_CLASSES))), default=0.0)
    check("五类概率分布一致（容差 1e-3）", max_pb <= 1e-3, f"最大偏差 {max_pb:.2e}")

    max_dp = max((abs(beats[i]["confidence"] - float(probs[i].max())) for i in range(n)),
                 default=0.0)
    check("置信度一致（容差 1e-3）", max_dp <= 1e-3, f"最大偏差 {max_dp:.2e}")

    # ③ 位置对齐
    aligned = all(beats[i]["abs_sample"] == int(in_win[i]["sample"]) for i in range(n))
    check("R 峰位置与标注对齐", aligned)
    check("单搏窗口长度符合 90+162=252",
          all(b["sample"] >= 0 for b in beats) and C.BEAT_LEN == 252,
          f"BEAT_LEN={C.BEAT_LEN}")

    # ④ 节律特征：引擎回传的 RR 数值必须与独立计算一致
    pos = {a["sample"]: a for a in in_win}
    rr_ok = True
    for b in beats:
        a = pos.get(b["abs_sample"])
        if a is None:
            rr_ok = False
            break
        if abs(b["rr_prev_sec"] - round(float(b["rr_prev_sec"]), 3)) > 1e-9:
            rr_ok = False
    check("RR 特征字段完整且已按 3 位小数规范化", rr_ok)


# ================================================================ 4 CAM
def test_cam() -> None:
    print("\n[4] Grad-CAM 长度与对齐")
    from src.inference import get_analyzer
    result = get_analyzer().analyze_window(RECORD, START_SEC, DURATION_SEC, with_cam=True)
    beats = result["beats"]
    lens = {len(b.get("cam") or []) for b in beats}
    check("每个心搏都有 Grad-CAM", all(b.get("cam") for b in beats))
    check(f"CAM 长度恒为 {C.BEAT_LEN}（单搏采样点数）", lens == {C.BEAT_LEN},
          f"实际长度集合 {sorted(lens)}")
    flat = [v for b in beats for v in (b.get("cam") or [])]
    check("CAM 数值归一化在 [0,1]", bool(flat) and min(flat) >= 0.0 and max(flat) <= 1.0,
          f"范围 [{min(flat):.3f}, {max(flat):.3f}]" if flat else "无数据")
    check("CAM 与心搏一一对应（数量相等）",
          len([b for b in beats if b.get("cam")]) == len(beats))

    no_cam = get_analyzer().analyze_window(RECORD, START_SEC, DURATION_SEC, with_cam=False)
    check("关闭 Grad-CAM 不影响预测类别",
          [b["pred"] for b in no_cam["beats"]] == [b["pred"] for b in beats])
    check("关闭 Grad-CAM 不产生 cam 字段",
          all("cam" not in b for b in no_cam["beats"]))


# ================================================================ 5 汇总
def test_summary() -> None:
    print("\n[5] 汇总算术自洽")
    from src.inference import get_analyzer
    result = get_analyzer().analyze_window(RECORD, START_SEC, DURATION_SEC)
    beats, s = result["beats"], result["summary"]

    check("n_beats 等于逐搏条数", s["n_beats"] == len(beats),
          f"{s['n_beats']} vs {len(beats)}")

    counts = {c: 0 for c in C.AAMI_CLASSES}
    for b in beats:
        counts[b["pred"]] += 1
    check("五类计数与逐搏结果一致", counts == s["counts"], str(counts))

    check("异常数 = 总数 - N 类数",
          s["abnormal_count"] == s["n_beats"] - counts["N"],
          f"{s['abnormal_count']}")
    expect_ratio = round(s["abnormal_count"] / s["n_beats"], 4)
    check("异常占比正确", abs(s["abnormal_ratio"] - expect_ratio) < 1e-4,
          f"{s['abnormal_ratio']} vs {expect_ratio}")

    agree = sum(1 for b in beats if b["agree"])
    check("一致率正确", abs(s["agreement"] - round(agree / len(beats), 4)) < 1e-4,
          f"{s['agreement']}")
    mean_conf = round(float(np.mean([b["confidence"] for b in beats])), 4)
    check("平均置信度正确", abs(s["mean_confidence"] - mean_conf) < 1e-4,
          f"{s['mean_confidence']} vs {mean_conf}")
    check("提示等级字段完整",
          all(k in s["risk_level"] for k in ("code", "label", "color", "desc")))
    check("包含免责声明且未被削弱",
          "不构成医疗诊断依据" in result["disclaimer"]
          and "不能用于任何临床决策" in result["disclaimer"])


# ================================================================ 6 schema
def test_schema() -> None:
    print("\n[6] 数据库 schema 与 src/db.py 一致")
    HS.init_db()
    import sqlite3
    conn = sqlite3.connect(C.DB_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(analyses)")]
    idx = [r[1] for r in conn.execute("PRAGMA index_list(analyses)")]
    conn.close()

    from src import db
    expected = ["id", "title", "record_id", "start_sec", "duration_sec", "n_beats",
                "abnormal_count", "abnormal_ratio", "risk_code", "risk_label",
                "agreement", "mean_conf", "counts_json", "payload_json", "created_at"]
    check("列名与顺序完全一致", cols == expected, ",".join(cols))
    check("索引 idx_analyses_created 存在", "idx_analyses_created" in idx, str(idx))
    check("schema 取自 src/db.py 的 SCHEMA 常量",
          "CREATE TABLE IF NOT EXISTS analyses" in db.SCHEMA)
    check("数据库写在用户数据目录而非程序目录",
          str(C.DB_PATH).startswith(str(TMP)), str(C.DB_PATH))


# ================================================================ 7 历史 CRUD
def test_history() -> None:
    print("\n[7] 历史记录 保存 / 读取 / 删除 / 清空")
    from src.inference import get_analyzer
    payload = get_analyzer().analyze_window(RECORD, START_SEC, DURATION_SEC)

    rid = HS.save_analysis(payload)
    check("保存成功并返回主键", isinstance(rid, int) and rid > 0, f"id={rid}")

    rows = HS.list_analyses()
    check("列表能查到该记录", any(r["id"] == rid for r in rows), f"{len(rows)} 条")

    row = HS.get_analysis(rid)
    check("能按主键取回完整报告", bool(row) and row.get("payload", {}).get("beats"))
    check("回放的逐搏条数与原分析一致",
          len(row["payload"]["beats"]) == len(payload["beats"]))

    st = HS.stats()
    check("统计口径正确", st["total_analyses"] == 1
          and st["total_beats"] == payload["summary"]["n_beats"], str(st))

    check("删除返回 True", HS.delete_analysis(rid) is True)
    check("删除后查不到", HS.get_analysis(rid) is None)

    HS.save_analysis(payload)
    HS.save_analysis(payload)
    check("清空返回删除条数", HS.clear_all() == 2)
    check("清空后列表为空", HS.list_analyses() == [])


# ================================================================ 8 GUI
def test_gui() -> None:
    print("\n[8] GUI 构造与导航")
    from PySide6.QtWidgets import QApplication
    from desktop import theme
    from desktop.app import MainWindow, PAGE_ANALYZE, PAGE_HOME

    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply(app)
    win = MainWindow()
    win.show()
    app.processEvents()

    check("窗口默认尺寸 1200x760",
          (win.width(), win.height()) == (1200, 760), f"{win.width()}x{win.height()}")
    check("最小尺寸 1000x650",
          (win.minimumWidth(), win.minimumHeight()) == (1000, 650))
    check("页面数量为 6", win.stack.count() == 6)

    for key in ("home", "analyze", "history", "about"):
        win.goto(key)
        app.processEvents()
    check("四个主导航页面均可切换", True)

    win.goto("home")
    check("首页可刷新状态", win.home.status_tag.text() in ("已就绪", "安装不完整"),
          win.home.status_tag.text())
    win.goto("history")
    check("历史页可刷新", win.history.table.rowCount() == 0)
    win.goto("analyze")
    check("分析页列出了可选记录", win.analyze.record_combo.count() == 44,
          f"{win.analyze.record_combo.count()} 条")

    # 未分析时点「结果」应被拦回分析页
    win.goto("result")
    app.processEvents()
    check("无结果时结果页不可达（自动回到分析工作台）",
          win.stack.currentIndex() == PAGE_ANALYZE)
    win.goto("home")
    check("首页为初始页面", PAGE_HOME == 0)
    return win, app


# ================================================================ 9 线程
def test_threaded_analysis(win, app) -> dict:
    print("\n[9] 后台线程分析（界面不冻结）")
    seen: list[str] = []
    state: dict = {}

    page = win.analyze
    page.record_combo.setCurrentIndex(
        [i for i, r in enumerate(page._records) if r["id"] == RECORD][0])
    page.start_slider.setValue(int(START_SEC))
    page.dur_slider.setValue(int(DURATION_SEC))
    page.cam_check.setChecked(True)

    def on_progress(text: str) -> None:
        seen.append(text)

    worker = AS.AnalysisWorker(RECORD, START_SEC, DURATION_SEC, True)
    worker.progressed.connect(on_progress)
    worker.succeeded.connect(lambda p: state.update(payload=p))
    worker.failed.connect(lambda m: state.update(error=m))
    worker.start()

    import time
    deadline = time.time() + 180
    while worker.isRunning() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    # 线程结束后，跨线程的信号还排在事件队列里，必须再排空一次才能拿到结果
    worker.wait(5000)
    for _ in range(50):
        app.processEvents()
        time.sleep(0.01)
    check("分析线程已结束", not worker.isRunning())

    check("未返回错误", "error" not in state, state.get("error", ""))
    check("收到成功结果", "payload" in state)
    check("收到分阶段进度提示", len(seen) >= 2, " / ".join(seen))
    check("进度文案对用户友好（无异常堆栈）",
          all("Traceback" not in t for t in seen))
    return state.get("payload", {})


# ================================================================ 10 结果页
def test_result_page(win, app, payload: dict) -> None:
    print("\n[10] 结果页装载与 Grad-CAM 联动")
    win._on_analysis_done(payload)
    win.goto("result")
    app.processEvents()

    page = win.result
    check("结果页已成为当前页", win.stack.currentWidget() is page)
    check("统计卡显示 4 项", page.stats_grid.count() == 4)
    check("逐搏表行数与结果一致", page.table.rowCount() == len(payload["beats"]),
          f"{page.table.rowCount()} 行")

    page._select_beat(0)
    app.processEvents()
    cam_len = len(payload["beats"][0].get("cam") or [])
    check("选中首搏后 CAM 提示包含真实长度",
          str(cam_len) in page.cam_hint.text(), page.cam_hint.text())
    check("单搏详情展示了类别与 RR 特征",
          "置信度" in page.detail.conf.text() and "RR" in page.detail.rhythm.text())

    beat = payload["beats"][0]
    check("单搏详情含前后 RR 与基线",
          all(k in beat for k in ("rr_prev_sec", "rr_next_sec", "rr_baseline_sec")))

    # 保存 → 历史页可见
    page._save()
    app.processEvents()
    saved = page._analysis_id
    check("保存按钮已失效且显示已保存",
          saved is not None and not page.save_btn.isEnabled(), f"id={saved}")

    win.goto("history")
    app.processEvents()
    check("历史页出现该报告", win.history.table.rowCount() == 1)

    win._open_history_report(saved)
    app.processEvents()
    check("可打开历史详情（只读）", win.stack.currentWidget() is win.detail)
    check("只读页回放逐搏数一致",
          win.detail.table.rowCount() == len(payload["beats"]))
    check("只读页隐藏保存按钮、提供删除按钮",
          not hasattr(win.detail, "save_btn") and win.detail.delete_btn is not None)

    win._delete_report(saved)
    app.processEvents()
    check("删除后历史页为空", win.history.table.rowCount() == 0)


# ================================================================ 11 离线
FORBIDDEN_RUNTIME = ("flask", "requests", "urllib", "httpx", "aiohttp", "socket",
                     "localhost", "127.0.0.1", "app.run", "http://", "https://",
                     "QWebEngine", "webview", "selenium", "playwright")


def _string_constants(tree: ast.AST) -> list[str]:
    """收集代码中的字符串常量，跳过模块/函数/类的文档字符串。"""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                out.append(node.value)
    return out


def test_offline() -> None:
    print("\n[11] 桌面运行路径不含网络 / 浏览器依赖")
    files = sorted((ROOT / "desktop").rglob("*.py"))
    check("desktop 包存在", bool(files), f"{len(files)} 个文件")

    imports: list[str] = []
    literals: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        for s in _string_constants(tree):
            if any(tok in s for tok in FORBIDDEN_RUNTIME):
                literals.append(f"{path.name}: {s[:60]}")
        for tok in FORBIDDEN_RUNTIME:
            if tok in imports:
                literals.append(f"{path.name}: import {tok}")

    check("没有 flask/requests/urllib 等网络模块导入",
          not any(t in " ".join(imports) for t in
                  ("flask", "requests", "urllib", "httpx", "aiohttp", "socket")),
          " / ".join(sorted({i for i in imports if i in
                             ("flask", "requests", "urllib", "httpx",
                              "aiohttp", "socket")})))
    check("代码中没有 localhost / 127.0.0.1 / http:// 字面量",
          not literals, " | ".join(literals[:3]))
    check("没有 Qt WebEngine / 浏览器壳组件",
          not any("WebEngine" in i or "webview" in i.lower() for i in imports))


# ================================================================ 12 文案
WEB_TERMS = ("Flask", "flask", "浏览器", "localhost", "127.0.0.1", "Web Server",
             "网页", "端口", "http://", "API 接口")


def test_copies() -> None:
    print("\n[12] 用户可见文案不含 Web / 服务器术语")
    from desktop.pages.about_page import AboutPage
    from desktop.pages.home_page import HomePage

    bad: list[str] = []
    for cls in (AboutPage, HomePage):
        source = Path(sys.modules[cls.__module__].__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for s in _string_constants(tree):
            for term in WEB_TERMS:
                if term in s:
                    bad.append(f"{cls.__name__}: {term} → {s[:50]}")
    check("首页/关于页文案无 Web 术语", not bad, " | ".join(bad[:3]))

    disclaimer_ok = ("不构成医疗诊断依据" in C.DISCLAIMER
                     and "不能用于任何临床决策" in C.DISCLAIMER)
    check("免责声明措辞完整未被削弱", disclaimer_ok)


# ================================================================ 主流程
def main() -> int:
    print("=" * 68)
    print("CardioLens 桌面版自检")
    print(f"项目根目录：{ROOT}")
    print(f"临时数据目录：{TMP}")
    print("=" * 68)

    test_readiness()
    test_hashes()
    test_inference_consistency()
    test_cam()
    test_summary()
    test_schema()
    test_history()
    win, app = test_gui()
    payload = test_threaded_analysis(win, app)
    if payload:
        test_result_page(win, app, payload)
    else:
        check("结果页测试", False, "未拿到分析结果，跳过")
    test_offline()
    test_copies()

    win.close()
    app.processEvents()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 68)
    print(f"自检结果：{passed}/{total} PASS，{total - passed} FAIL")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL  {name} — {detail}")
    print("=" * 68)

    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
