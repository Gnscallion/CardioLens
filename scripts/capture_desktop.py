"""桌面端界面截图脚本：把各个页面渲染成 PNG，供项目报告使用。

用 Qt 自己的渲染（QWidget.grab()）直接截取真实控件，不依赖任何浏览器，
也不需要人工操作。产物写到 docs/screenshots_desktop/。

默认使用正常的 Windows 平台插件（窗口会短暂闪现，这是为了拿到真实的中文渲染）；
若在无显示环境（CI）下运行，可设 QT_QPA_PLATFORM=offscreen，
但注意离屏插件的字体库不含中文字形，截图里的中文会变成方框。

用法：
    python scripts/capture_desktop.py

注意：脚本会把分析历史写入临时目录（不污染项目 store/ 与用户目录），
截取历史页时会先临时插入报告，结束后全部清空。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if os.environ.get("CARDIOLENS_SHOT_OFFSCREEN"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "docs" / "screenshots_desktop"

# 在导入任何业务模块之前，把可写数据重定向到临时目录
_TMP = tempfile.mkdtemp(prefix="cardiolens_shot_")
from src import config as C                     # noqa: E402

C.STORE_DIR = Path(_TMP)
C.LOG_DIR = C.STORE_DIR / "logs"
C.DB_PATH = C.STORE_DIR / "app.db"
C.STORE_DIR.mkdir(parents=True, exist_ok=True)

from PySide6.QtWidgets import QApplication                # noqa: E402

from desktop import theme                                 # noqa: E402
from desktop.app import MainWindow                        # noqa: E402
from desktop.services import history_service as HS        # noqa: E402
from src.inference import get_analyzer                    # noqa: E402

W, H = 1200, 760
shots: list[str] = []


def _settle(app: QApplication, rounds: int = 6) -> None:
    """让布局与绘制事件跑完，避免截到未完成渲染的画面。"""
    for _ in range(rounds):
        app.processEvents()


def _grab(app: QApplication, win: MainWindow, name: str) -> None:
    _settle(app)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    ok = win.grab().save(str(path))
    shots.append(f"{'✓' if ok else '✗'} {name}")
    print(f"  {'✓' if ok else '✗'} {path.relative_to(ROOT)}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    theme.apply(app)

    HS.init_db()
    win = MainWindow()
    win.resize(W, H)
    win.show()
    _settle(app)
    win.set_status("系统就绪", True)
    _settle(app)

    # ---------------------------------------------------------- 1. 首页
    win.goto("home")
    _grab(app, win, "01-首页.png")

    # ---------------------------------------------------------- 2. 分析页
    win.goto("analyze")
    _settle(app)
    _grab(app, win, "02-ECG分析-参数与预览.png")

    # 跑一次真实分析（正常搏动为主的记录 100）
    analyzer = get_analyzer()
    payload = analyzer.analyze_window("100", 10.0, 10.0, with_cam=True)
    win._on_analysis_done(payload)
    win.goto("result")
    _settle(app)
    _grab(app, win, "03-分析结果-整体.png")

    # 换一条异常搏动较多的记录（208，训练集 DS1），展示风险分级与多类别
    payload_abn = analyzer.analyze_window("208", 300.0, 10.0, with_cam=True)
    win._on_analysis_done(payload_abn)
    win.goto("result")
    _settle(app)
    _grab(app, win, "04-分析结果-异常搏动.png")

    # 选中一个异常搏动，展示单搏详情 + Grad-CAM + 五类概率 + 节律上下文
    abnormal_idx = next((i for i, b in enumerate(payload_abn["beats"])
                         if b["pred"] != "N"), 0)
    win.result._select_beat(abnormal_idx)
    _settle(app)
    _grab(app, win, "05-单搏详情与GradCAM.png")

    # ---------------------------------------------------------- 6. 保存到历史
    analysis_id = HS.save_analysis(payload)
    HS.save_analysis(payload_abn)
    win.result.save_btn.setEnabled(True)

    # ---------------------------------------------------------- 7. 历史页
    win.goto("history")
    _settle(app)
    _grab(app, win, "06-分析历史.png")

    # ---------------------------------------------------------- 8. 历史详情
    win._open_history_report(analysis_id)
    _settle(app)
    _grab(app, win, "07-历史详情.png")

    # ---------------------------------------------------------- 9. 关于页
    win.goto("about")
    _settle(app, rounds=10)
    _grab(app, win, "08-关于-上半.png")
    # 关于页较长，滚动后补两张（评估结果 / 局限与声明）
    scroll = getattr(win.about, "_scroll", None)
    if scroll is not None:
        bar = scroll.verticalScrollBar()
        bar.setValue(int(bar.maximum() * 0.45))
        _settle(app)
        _grab(app, win, "09-关于-评估结果.png")
        bar.setValue(bar.maximum())
        _settle(app)
        _grab(app, win, "10-关于-局限与声明.png")

    # ---------------------------------------------------------- 清理
    HS.clear_all()
    win.close()
    _settle(app)

    print("\n共生成", len(shots), "张截图 →", OUT_DIR.relative_to(ROOT))
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
