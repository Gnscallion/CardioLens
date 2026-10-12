"""自动截图脚本：驱动浏览器访问各页面并保存课堂作业截图。

使用系统已安装的 Edge 浏览器（channel="msedge"），无需额外下载浏览器内核。

用法：
    python scripts/screenshot.py              # 若服务未启动则自动拉起
    python scripts/screenshot.py --url http://127.0.0.1:5000
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import force_utf8_stdout   # noqa: E402

OUT_DIR = ROOT / "docs" / "screenshots"
VIEWPORT = {"width": 1440, "height": 900}


def server_alive(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_server(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_alive(url):
            return True
        time.sleep(1.0)
    return False


def main() -> int:
    # Windows 控制台默认 GBK，下面用到的 ✓/✗ 与中文文件名会触发 UnicodeEncodeError
    force_utf8_stdout()

    ap = argparse.ArgumentParser(description="自动截取项目 UI 截图")
    ap.add_argument("--url", default="http://127.0.0.1:5000")
    ap.add_argument("--headed", action="store_true", help="显示浏览器窗口（调试用）")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = args.url.rstrip("/")

    proc = None
    if not server_alive(base):
        print("[截图] 服务未运行，正在启动 Flask ...")
        proc = subprocess.Popen(
            [sys.executable, "app.py"], cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_server(base):
            print("[截图] 启动服务失败，请手动运行 python app.py 后重试")
            if proc:
                proc.terminate()
            return 1
    print(f"[截图] 服务就绪：{base}")

    from playwright.sync_api import sync_playwright

    saved: list[str] = []
    errors: list[str] = []

    def shot(page, name: str, full: bool = False, wait: float = 0.6):
        try:
            page.wait_for_timeout(int(wait * 1000))
            path = OUT_DIR / name
            page.screenshot(path=str(path), full_page=full)
            saved.append(name)
            print(f"[截图] ✓ {name}")
        except Exception as e:                       # 单张失败不应中断整体流程
            errors.append(f"{name}: {e}")
            print(f"[截图] ✗ {name} -> {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=not args.headed)
        ctx = browser.new_context(
            viewport=VIEWPORT, device_scale_factor=2, locale="zh-CN",
        )
        page = ctx.new_page()
        page.set_default_timeout(30000)

        # ---------------- 1. 首页 ----------------
        page.goto(base + "/", wait_until="networkidle")
        shot(page, "01-首页.png", full=True, wait=1.0)

        # ---------------- 2. 分析工作台（含波形预览）----------------
        page.goto(base + "/analyze", wait_until="networkidle")
        page.wait_for_timeout(2500)                  # 等首屏自动预览完成
        shot(page, "02-分析工作台.png", wait=0.8)

        # 切换到室性早搏较多的记录，便于展示异常识别
        try:
            page.select_option("#recSel", "208")
            page.wait_for_timeout(600)
            page.click("#previewBtn")
            page.wait_for_timeout(2200)
            shot(page, "03-波形预览.png", wait=0.6)
        except Exception as e:
            errors.append(f"波形预览: {e}")

        # ---------------- 4. 分析过程（步骤动画中）----------------
        try:
            page.click("#analyzeBtn")
            page.wait_for_timeout(1100)              # 抓取步骤动画进行中的画面
            shot(page, "04-分析过程.png", wait=0.0)
            page.wait_for_selector("#resultArea .risk", timeout=30000)
            page.wait_for_timeout(1500)
            shot(page, "05-分析结果.png", wait=0.5)
        except Exception as e:
            errors.append(f"分析流程: {e}")
            print(f"[截图] ✗ 分析流程 -> {e}")

        # ---------------- 6. 逐搏明细表 ----------------
        try:
            page.evaluate("document.querySelector('#beatRows')?.scrollIntoView({block:'center'})")
            page.wait_for_timeout(900)
            shot(page, "06-逐搏明细.png", wait=0.5)
        except Exception as e:
            errors.append(f"逐搏明细: {e}")

        # ---------------- 7. 单搏详情（Grad-CAM）----------------
        try:
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(300)
            rows = page.query_selector_all("#beatRows tr")
            if len(rows) > 3:
                rows[3].click()                      # 点一个非首搏，展示交互
            page.wait_for_timeout(1100)
            page.evaluate(
                "document.querySelector('#beatCanvas')?.scrollIntoView({block:'center'})"
            )
            page.wait_for_timeout(700)
            shot(page, "07-单搏详情与GradCAM.png", wait=0.5)
        except Exception as e:
            errors.append(f"单搏详情: {e}")

        # ---------------- 8. 保存报告 ----------------
        try:
            if page.query_selector("#saveBtn"):
                page.evaluate("window.scrollTo(0, 0)")
                page.fill("#saveTitle", "课堂演示 · 记录208室性早搏分析")
                page.click("#saveBtn")
                page.wait_for_timeout(2500)
                page.evaluate("window.scrollTo(0, 0)")
                shot(page, "08-保存报告.png", wait=0.6)
        except Exception as e:
            errors.append(f"保存报告: {e}")

        # ---------------- 9. 历史记录 ----------------
        page.goto(base + "/history", wait_until="networkidle")
        shot(page, "09-历史记录.png", full=True, wait=0.9)

        # ---------------- 10. 历史详情 ----------------
        try:
            link = page.query_selector("tbody tr a.btn")
            if link:
                link.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1600)
                shot(page, "10-历史详情.png", wait=0.8)
        except Exception as e:
            errors.append(f"历史详情: {e}")

        # ---------------- 11~12. 关于页 ----------------
        page.goto(base + "/about", wait_until="networkidle")
        shot(page, "11-关于与技术原理.png", full=True, wait=1.0)

        try:
            page.evaluate(
                "document.querySelector('img[alt=\"混淆矩阵\"]')"
                "?.scrollIntoView({block:'center'})"
            )
            page.wait_for_timeout(900)
            shot(page, "12-评估结果与混淆矩阵.png", wait=0.6)
        except Exception as e:
            errors.append(f"评估结果: {e}")

        # ---------------- 13~14. 数据划分提示（训练集 / 测试集对照）----------------
        # 记录 208 属训练集 DS1，模型训练时见过该患者，界面必须明示"一致率偏高、
        # 不能当作泛化能力"；记录 100 属测试集 DS2，训练全程不可见。
        # 两张图对照，体现项目对指标口径的诚实交代——这是本项目的设计要点之一。
        try:
            page.goto(base + "/analyze", wait_until="networkidle")
            page.wait_for_timeout(2200)
            page.select_option("#recSel", "208")
            page.wait_for_timeout(600)
            page.click("#analyzeBtn")
            page.wait_for_selector("#resultArea .alert-warn", timeout=30000)
            page.wait_for_timeout(1200)
            page.evaluate(
                "document.querySelector('#resultArea .alert-warn')"
                "?.scrollIntoView({block:'center'})"
            )
            page.wait_for_timeout(800)
            shot(page, "13-数据划分提示-训练集记录.png", wait=0.5)

            page.select_option("#recSel", "100")
            page.wait_for_timeout(600)
            page.click("#analyzeBtn")
            page.wait_for_selector("#resultArea .alert-ok", timeout=30000)
            page.wait_for_timeout(1200)
            page.evaluate(
                "document.querySelector('#resultArea .alert-ok')"
                "?.scrollIntoView({block:'center'})"
            )
            page.wait_for_timeout(800)
            shot(page, "14-数据划分提示-测试集记录.png", wait=0.5)
        except Exception as e:
            errors.append(f"数据划分提示: {e}")
            print(f"[截图] ✗ 数据划分提示 -> {e}")

        ctx.close()
        browser.close()

    if proc:
        proc.terminate()
        print("[截图] 已关闭临时启动的 Flask 服务")

    print(f"\n[截图] 完成：成功 {len(saved)} 张，失败 {len(errors)} 张")
    print(f"[截图] 输出目录：{OUT_DIR}")
    for e in errors:
        print(f"        失败 -> {e}")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
