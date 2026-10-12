"""生成 Web 版界面截图，输出到 docs/screenshots_web/。

使用系统已安装的 Edge 浏览器（channel="msedge"），无需额外下载浏览器内核。

脚本会自己拉起一个服务实例，并把可写数据目录指向临时位置——
否则演示用的报告会被写进真实的 store/app.db。

用法：
    python scripts/screenshot.py              # 无头运行
    python scripts/screenshot.py --headed     # 显示浏览器窗口
    python scripts/screenshot.py --keep       # 保留临时数据目录（便于排查）
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "screenshots_web"

HOST = "127.0.0.1"
PORT = int(os.environ.get("CARDIOLENS_SHOT_PORT", "5082"))
BASE = f"http://{HOST}:{PORT}"

VIEWPORT = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}

# 截图用的两条记录：一条测试集、一条训练集，用于对照"划分提示"
RECORD_TEST = "100"      # DS2 测试集
RECORD_TRAIN = "208"     # DS1 训练集


def start_server(store: Path) -> subprocess.Popen:
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{ROOT}');"
        "from waitress import serve;"
        "from wsgi import app;"
        f"serve(app, host='{HOST}', port={PORT}, threads=4, ident='CardioLensShot')"
    )
    env = {
        **os.environ,
        "CARDIOLENS_STORE": str(store),
        "CARDIOLENS_SECRET_KEY": "screenshot-secret",
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("服务启动即退出")
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:                                    # noqa: BLE001
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("服务启动超时")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Web 版界面截图")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--keep", action="store_true", help="保留临时数据目录")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺少 playwright。安装：pip install playwright", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cardiolens_shot_"))
    store = tmp / "store"
    store.mkdir(parents=True, exist_ok=True)
    print(f"临时数据目录：{store}")

    proc = start_server(store)
    shots: list[Path] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=not args.headed)
            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2,
                                      locale="zh-CN")
            page = ctx.new_page()

            def shot(name: str, clip=None, full=False):
                path = OUT_DIR / f"{name}.png"
                page.screenshot(path=str(path), clip=clip, full_page=full)
                shots.append(path)
                print(f"  ✓ {path.name}")

            def shot_el(locator, name: str):
                """按元素截图。会自动把元素滚入视口，无需自己算坐标裁剪。"""
                locator.scroll_into_view_if_needed()
                page.wait_for_timeout(250)
                path = OUT_DIR / f"{name}.png"
                locator.screenshot(path=str(path))
                shots.append(path)
                print(f"  ✓ {path.name}")

            def wait_ready(timeout=30000):
                page.wait_for_selector(".topbar", timeout=timeout)

            # ---------------------------------------------------- 首页
            print("\n[首页]")
            page.goto(BASE + "/", wait_until="load")
            wait_ready()
            page.wait_for_selector(".hero")
            page.wait_for_timeout(500)
            shot("01-首页", full=True)

            # ---------------------------------------------------- 分析工作台
            print("\n[分析工作台]")
            page.click(".nav a[href='/analyze']")
            page.wait_for_selector("[data-test='rec-select']")
            page.wait_for_selector("[data-test='wave-canvas']")
            page.wait_for_timeout(1200)
            box = page.locator(".grid-side").bounding_box()
            shot("02-分析工作台-参数与预览")
            shot("03-波形预览", clip=box)

            # 训练集记录的分析，用于"划分提示"对照
            print("\n[分析：训练集记录 208]")
            page.select_option("[data-test='rec-select']", RECORD_TRAIN)
            page.wait_for_timeout(1500)
            page.click("[data-test='analyze-btn']")
            # 分析很快（约 0.3 秒），先抢一张"分析中"再等结果
            try:
                page.wait_for_selector("[data-test='analyzing']", timeout=3000)
                shot("04-分析过程")
            except Exception:                                # noqa: BLE001
                print("  · 分析过快，未捕捉到进行中状态（属正常）")
            page.wait_for_selector("[data-test='split-note']", timeout=60000)
            page.wait_for_timeout(900)
            shot("05-分析结果-整体", full=True)
            beat_table_head = page.locator("h2").filter(has_text="逐搏结果")
            beat_table_head.wait_for(timeout=20000)
            beat_table_head.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            shot("06-逐搏明细")

            # 单搏详情与 Grad-CAM
            page.locator("[data-test='beat-rows'] tbody tr").nth(3).click()
            page.wait_for_timeout(900)
            page.locator("h3").filter(has_text="五类概率").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            shot("07-单搏详情与GradCAM")

            # 波形交互（作为"补齐桌面版能力"的验收证据）
            print("\n[波形交互]")
            strip = page.locator(".ecg-strip").last
            strip.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            wbox = page.locator("[data-test='wave-canvas']").last.bounding_box()
            cx, cy = wbox["x"] + wbox["width"] * 0.5, wbox["y"] + wbox["height"] * 0.5
            page.mouse.move(cx, cy)
            page.mouse.wheel(0, -700)
            page.wait_for_timeout(600)
            shot_el(strip, "08-波形缩放")

            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx + 150, cy, steps=15)
            page.mouse.up()
            page.wait_for_timeout(600)
            shot_el(strip, "09-波形平移")

            page.mouse.dblclick(cx, cy)
            page.wait_for_timeout(500)
            page.mouse.move(cx - 120, cy - 30)
            page.wait_for_timeout(600)
            shot_el(strip, "10-悬停十字线读数")

            # 划分提示：训练集
            page.locator("[data-test='split-note']").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            shot("11-数据划分提示-训练集记录")

            # 保存报告
            print("\n[保存与历史]")
            page.click("[data-test='save-btn']")
            page.wait_for_timeout(3500)
            page.locator("[data-test='save-btn']").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            shot("12-保存报告")

            # 测试集记录：再来一份，并截"划分提示-测试集"
            page.select_option("[data-test='rec-select']", RECORD_TEST)
            page.wait_for_timeout(1500)
            page.click("[data-test='analyze-btn']")
            page.wait_for_selector("[data-test='split-note']", timeout=60000)
            page.wait_for_timeout(800)
            page.locator("[data-test='split-note']").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            shot("13-数据划分提示-测试集记录")
            page.click("[data-test='save-btn']")
            page.wait_for_timeout(3500)

            # 历史列表
            page.click(".nav a[href='/history']")
            page.wait_for_selector("[data-test='history-table']")
            page.wait_for_timeout(800)
            shot("14-历史记录", full=True)

            # 历史详情
            page.locator("[data-test='history-table'] tbody tr").first.click()
            page.wait_for_selector("[data-test='split-note']", timeout=30000)
            page.wait_for_timeout(900)
            shot("15-历史详情", full=True)

            # ---------------------------------------------------- 关于页
            print("\n[关于页]")
            page.click(".nav a[href='/about']")
            page.locator("h2").filter(has_text="已知局限").wait_for(timeout=20000)
            page.wait_for_timeout(900)
            shot("16-关于-项目与技术原理", full=True)
            page.locator("h2").filter(has_text="评估结果").first.scroll_into_view_if_needed()
            page.wait_for_timeout(700)
            shot("17-关于-评估结果与混淆矩阵")
            page.locator("h2").filter(has_text="已知局限").scroll_into_view_if_needed()
            page.wait_for_timeout(600)
            shot("18-关于-已知局限")

            # ---------------------------------------------------- 会话与移动端
            print("\n[其他]")
            page.goto(BASE + "/history", wait_until="load")
            page.wait_for_selector("[data-test='session-notice']")
            page.wait_for_timeout(600)
            shot("19-会话隔离提示")

            # 新会话（无历史）展示空状态
            fresh = browser.new_context(viewport=VIEWPORT, device_scale_factor=2,
                                        locale="zh-CN")
            fpage = fresh.new_page()
            fpage.goto(BASE + "/history", wait_until="load")
            fpage.wait_for_selector("text=本浏览器还没有保存过", timeout=20000)
            fpage.wait_for_timeout(600)
            fpage.screenshot(path=str(OUT_DIR / "20-新会话空历史.png"), full_page=True)
            shots.append(OUT_DIR / "20-新会话空历史.png")
            print("  ✓ 20-新会话空历史.png")
            fresh.close()

            # 移动端视口
            mobile = browser.new_context(viewport=MOBILE, device_scale_factor=3,
                                         locale="zh-CN", is_mobile=True,
                                         has_touch=True)
            mpage = mobile.new_page()
            mpage.goto(BASE + "/", wait_until="load")
            mpage.wait_for_selector(".hero", timeout=20000)
            mpage.wait_for_timeout(700)
            mpage.screenshot(path=str(OUT_DIR / "21-移动端-首页.png"), full_page=True)
            shots.append(OUT_DIR / "21-移动端-首页.png")
            print("  ✓ 21-移动端-首页.png")
            mpage.goto(BASE + "/analyze", wait_until="load")
            mpage.wait_for_selector("[data-test='wave-canvas']", timeout=25000)
            mpage.wait_for_timeout(1200)
            mpage.screenshot(path=str(OUT_DIR / "22-移动端-分析页.png"), full_page=True)
            shots.append(OUT_DIR / "22-移动端-分析页.png")
            print("  ✓ 22-移动端-分析页.png")
            mobile.close()

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if args.keep:
            print(f"\n临时目录已保留：{tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n共生成 {len(shots)} 张截图，位于 {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
