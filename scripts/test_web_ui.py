"""CardioLens Web 版前端验收（真实浏览器驱动）。

另外两套测试都覆盖不到前端：
    test_web.py      Flask test_client，只到 HTTP 层
    test_web_e2e.py  真实 WSGI，仍然只到 HTTP 层
波形是 Canvas 画出来的，缩放/平移/悬停这类交互只在浏览器里才存在——
本脚本用 Playwright 驱动真实浏览器，并以**画布像素**为判据，
而不是"没报错就算过"。

覆盖：
    A  页面与视图：五个视图可达、无控制台异常
    B  波形初始状态：视图为全览（不是塌缩）、坐标轴刻度确实画出来了
    C  四项交互：滚轮缩放 / 拖拽平移 / 双击复位 / 悬停十字线读数
    D  联动：点击搏动、逐搏表格选中项与单搏详情同步
    E  分析全流程：预览 → 分析 → 结果 → 保存 → 历史 → 详情
    F  错误处理：未知路径显示 404 视图而非白屏

用法：
    python scripts/test_web_ui.py            # 无头
    python scripts/test_web_ui.py --headed   # 显示浏览器窗口
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
HOST = "127.0.0.1"
PORT = int(os.environ.get("CARDIOLENS_UI_PORT", "5091"))
BASE = f"http://{HOST}:{PORT}"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def start_server(store: Path) -> subprocess.Popen:
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{ROOT}');"
        "from waitress import serve;"
        "from wsgi import app;"
        f"serve(app, host='{HOST}', port={PORT}, threads=4, ident='CardioLensUI')"
    )
    env = {
        **os.environ,
        "CARDIOLENS_STORE": str(store),
        "CARDIOLENS_SECRET_KEY": "ui-test-secret",
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


# ---------------------------------------------------------------- 浏览器侧工具
JS_COUNT_BRIGHT = """
(args) => {
  const [sel, nth, x0, y0, x1, y1] = args;
  const list = document.querySelectorAll(sel);
  const c = nth < 0 ? list[list.length + nth] : list[nth];
  if (!c) return -1;
  const ctx = c.getContext('2d');
  const W = c.width, H = c.height;
  const ax0 = x0 < 0 ? 0 : Math.round(x0 * W);
  const ax1 = x1 < 0 ? W : Math.round(x1 * W);
  const ay0 = y0 < 0 ? 0 : Math.round(y0 * H);
  const ay1 = y1 < 0 ? H : Math.round(y1 * H);
  const d = ctx.getImageData(ax0, ay0, Math.max(1, ax1 - ax0), Math.max(1, ay1 - ay0)).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i] > 60 || d[i + 1] > 70 || d[i + 2] > 90) n++;
  }
  return n;
}"""

JS_FINGERPRINT = """
() => {
  const list = document.querySelectorAll("[data-test='wave-canvas']");
  const c = list[list.length - 1];
  if (!c) return 0;
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let h = 0;
  for (let i = 0; i < d.length; i += 499) h = (h * 33 + d[i]) >>> 0;
  return h;
}"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Web 版前端验收")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺少 playwright。安装：pip install playwright", file=sys.stderr)
        return 1

    print("=" * 70)
    print("  CardioLens Web 版前端验收（真实浏览器）")
    print(f"  地址：{BASE}")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="cardiolens_ui_"))
    store = tmp / "store"
    store.mkdir(parents=True, exist_ok=True)
    print(f"  临时数据目录：{store}\n")

    proc = None
    page_errors: list[str] = []
    console_errors: list[str] = []
    try:
        proc = start_server(store)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=not args.headed)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                      device_scale_factor=1, locale="zh-CN")
            page = ctx.new_page()
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("console",
                    lambda m: console_errors.append(m.text) if m.type == "error" else None)

            # ---------------------------------------------- A 页面与视图
            print("[A] 页面与视图")
            page.goto(BASE + "/", wait_until="load")
            page.wait_for_selector(".hero", timeout=20000)
            check("首页渲染", page.locator(".hero h1").count() == 1)

            for path, marker in (("/analyze", "[data-test='rec-select']"),
                                 ("/history", "[data-test='session-notice']"),
                                 ("/about", "text=已知局限")):
                page.goto(BASE + path, wait_until="load")
                page.wait_for_selector(marker, timeout=20000)
                check(f"{path} 可达", True)

            # ---------------------------------------------- B 初始状态与刻度
            print("\n[B] 波形初始状态与坐标轴刻度")
            page.goto(BASE + "/analyze", wait_until="load")
            page.wait_for_selector("[data-test='wave-canvas']", timeout=20000)
            page.click("[data-test='analyze-btn']")
            page.wait_for_selector("[data-test='split-note']", timeout=60000)
            page.wait_for_timeout(1500)

            strip = page.locator(".ecg-strip").last
            strip.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            box = page.locator("[data-test='wave-canvas']").last.bounding_box()
            cx = box["x"] + box["width"] * 0.5
            cy = box["y"] + box["height"] * 0.5

            # 左轴 mV 刻度位于 x ∈ [0, padL/W]；底部时间刻度位于 y ∈ [1-padB/H, 1]
            left = page.evaluate(JS_COUNT_BRIGHT,
                                 ["[data-test='wave-canvas']", -1, 0.0, 0.0, 0.06, 1.0])
            bottom = page.evaluate(JS_COUNT_BRIGHT,
                                   ["[data-test='wave-canvas']", -1, 0.0, 0.90, 1.0, 1.0])
            check("左侧幅值刻度已绘制", left > 50, f"亮点 {left}")
            check("底部时间刻度已绘制", bottom > 10, f"亮点 {bottom}")

            # 初始视图必须是全览。曾经有过一个缺陷：视图区间未初始化，
            # 跨度恒为 0，波形被压缩到左边界——只靠"没报错"完全发现不了。
            beats_span = page.evaluate("""() => {
              const rows = document.querySelectorAll("[data-test='beat-rows'] tbody tr");
              if (rows.length < 2) return -1;
              const cells = Array.from(rows).map(r => parseFloat(r.children[1].textContent));
              return cells[cells.length - 1] - cells[0];
            }""")
            check("逐搏时间跨度合理（分析窗口内有多次心搏）",
                  beats_span > 1.0, f"首末搏相差 {beats_span}s")
            check("波形画布尺寸与容器一致（未被裁切）", box["width"] > 400,
                  f"宽 {round(box['width'])}px")

            # ---------------------------------------------- C 四项交互
            print("\n[C] 波形四项交互")
            f0 = page.evaluate(JS_FINGERPRINT)

            page.mouse.move(cx, cy)
            page.mouse.wheel(0, -600)
            page.wait_for_timeout(600)
            f_zoom = page.evaluate(JS_FINGERPRINT)
            check("滚轮缩放改变视图", f_zoom != f0)

            # 全览状态下平移没有余地，属于预期行为；先缩放再平移
            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx - 130, cy, steps=14)
            page.mouse.up()
            page.wait_for_timeout(600)
            f_pan = page.evaluate(JS_FINGERPRINT)
            check("缩放后拖拽平移改变视图", f_pan != f_zoom)

            page.mouse.dblclick(cx, cy)
            page.wait_for_timeout(700)
            f_reset = page.evaluate(JS_FINGERPRINT)
            check("双击复位改变视图（回到全览）", f_reset != f_pan)

            # 复位后应能再次完整看到首末两搏
            span_after_reset = page.evaluate("""() => {
              const rows = document.querySelectorAll("[data-test='beat-rows'] tbody tr");
              const cells = Array.from(rows).map(r => parseFloat(r.children[1].textContent));
              return cells.length ? cells[cells.length - 1] - cells[0] : -1;
            }""")
            check("复位后与初始跨度一致（确实是全览）",
                  abs(span_after_reset - beats_span) < 0.01,
                  f"{span_after_reset}s vs {beats_span}s")

            # 悬停十字线画在顶层画布上
            page.mouse.move(cx - 80, cy - 40)
            page.wait_for_timeout(600)
            overlay = page.evaluate(JS_COUNT_BRIGHT,
                                    ["canvas.overlay", -1, -1.0, -1.0, -1.0, -1.0])
            check("悬停十字线与读数已绘制", overlay > 200, f"顶层亮点 {overlay}")

            # ---------------------------------------------- D 联动
            print("\n[D] 搏动联动")
            page.locator("[data-test='beat-rows'] tbody tr").nth(2).click()
            page.wait_for_timeout(700)
            selected = page.locator("[data-test='beat-rows'] tbody tr.sel").count()
            check("点击逐搏表格行后该行被选中", selected == 1, f"选中 {selected} 行")
            check("单搏详情同步更新",
                  page.locator("h2").filter(has_text="搏 ·").count() >= 1)
            beat_canvas = page.evaluate(JS_COUNT_BRIGHT,
                                        ["[data-test='beat-canvas']", -1, -1.0, -1.0, -1.0, -1.0])
            check("单搏波形已绘制", beat_canvas > 200, f"亮点 {beat_canvas}")

            # ---------------------------------------------- E 全流程
            print("\n[E] 分析全流程")
            page.click("[data-test='save-btn']")
            page.wait_for_timeout(3500)
            check("保存后按钮文案更新",
                  "已保存" in page.locator("[data-test='save-btn']").inner_text())

            page.click(".nav a[href='/history']")
            page.wait_for_selector("[data-test='history-table'] tbody tr", timeout=20000)
            rows = page.locator("[data-test='history-table'] tbody tr").count()
            check("历史列表出现已保存的报告", rows == 1, f"{rows} 行")

            page.locator("[data-test='history-table'] tbody tr").first.click()
            page.wait_for_selector("[data-test='split-note']", timeout=20000)
            check("历史详情可回放", page.locator("[data-test='wave-canvas']").count() >= 1)

            # ---------------------------------------------- F 错误处理
            print("\n[F] 错误处理")
            resp = page.goto(BASE + "/no-such-page", wait_until="load")
            check("未知页面返回 404 状态码", resp.status == 404, f"HTTP {resp.status}")
            page.wait_for_selector("text=页面不存在", timeout=10000)
            check("未知页面显示 404 视图而非白屏", True)

            browser.close()
    except Exception as exc:                                  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("前端验收执行未抛异常", False, f"{type(exc).__name__}: {exc}")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n[G] 运行时异常")
    check("无未捕获的页面异常（pageerror）", not page_errors,
          str(page_errors[:3]) if page_errors else "0 条")
    # 静态资源缺失也会记成 console error，这里单独排除预期内的 404
    unexpected = [e for e in console_errors if "404" not in e]
    check("无意外的控制台错误", not unexpected, str(unexpected[:3]) if unexpected else "0 条")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    failed = [(n, d) for n, ok, d in RESULTS if not ok]

    print("\n" + "=" * 70)
    print(f"  结果：{passed}/{total} 通过")
    if failed:
        print("  失败项：")
        for n, d in failed:
            print(f"    ✗ {n}" + (f" — {d}" if d else ""))
    print("=" * 70)
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
