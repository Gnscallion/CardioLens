"""CardioLens Web 版端到端测试（真实 HTTP + 真实 WSGI 服务器）。

与 test_web.py 的分工：
    test_web.py     用 Flask test_client，离线、快，覆盖接口契约与边界
    test_web_e2e.py 起一个真正的 waitress 进程，覆盖 test_client 走不到的部分：
                    Cookie 的真实序列化与回传、真实的并发行为、
                    以及"生产部署方式本身能不能跑起来"

覆盖范围：
    A  服务可用性（真实 WSGI 起得来、探活接口正常）
    B  正常流程（状态 / 记录 / 预览 / 分析 / 指标的契约）
    C  输入校验的负向分支（16 例）
    D  历史记录增删查（真实 Cookie）
    E  会话隔离（两个独立 CookieJar，互不可见、互不可删）
    F  并发实测（8 个并发分析请求全部成功、无 500、耗时在预期内）
    G  单次分析耗时基准（用于校准并发槽位与超时参数）

用法：
    python scripts/test_web_e2e.py
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HOST = "127.0.0.1"
PORT = int(os.environ.get("CARDIOLENS_E2E_PORT", "5071"))
BASE = f"http://{HOST}:{PORT}"

RECORD = "100"
START_SEC, DURATION_SEC = 10.0, 10.0

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


# ---------------------------------------------------------------- HTTP 客户端
class Session:
    """带独立 CookieJar 的简易 HTTP 客户端。

    用独立 CookieJar 是为了模拟两个不同的浏览器——会话隔离必须靠
    Cookie 的真实往返来验证，test_client 的 session_transaction 绕过了这一层。
    """

    def __init__(self, base: str = BASE):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, method: str, path: str, payload=None, raw: bytes | None = None,
                content_type: str = "application/json", timeout: float = 60.0):
        url = self.base + path
        data = None
        headers = {}
        if raw is not None:
            data = raw
            headers["Content-Type"] = content_type
        elif payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                body = resp.read()
                return resp.status, self._decode(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, self._decode(body)

    @staticmethod
    def _decode(body: bytes):
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, payload=None, **kw):
        return self.request("POST", path, payload=payload if payload is not None else {}, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def cookie_value(self, name: str) -> str:
        for c in self.jar:
            if c.name == name:
                return c.value
        return ""


# ---------------------------------------------------------------- 启动服务
def start_server(store: Path) -> subprocess.Popen:
    """用生产部署方式启动：waitress，单进程多线程。

    刻意不用 app.run()——顺便验证"生产启动命令本身可用"。
    """
    code = (
        "import os, sys;"
        f"sys.path.insert(0, r'{ROOT}');"
        "from waitress import serve;"
        "from wsgi import app;"
        f"serve(app, host='{HOST}', port={PORT}, threads=4, ident='CardioLensE2E')"
    )
    env = {
        **os.environ,
        "CARDIOLENS_STORE": str(store),
        "CARDIOLENS_SECRET_KEY": "e2e-test-secret",
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", code], cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            raise RuntimeError(f"服务启动即退出：\n{out}")
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:                                     # noqa: BLE001
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("服务启动超时（90 秒）")


# ================================================================ A 可用性
def test_availability(s: Session) -> None:
    print("\n[A] 服务可用性（真实 waitress 进程）")
    status, body = s.get("/api/health")
    check("探活接口 200", status == 200, f"HTTP {status}")
    check("探活返回应用名", body.get("app") == "CardioLens", str(body))

    status, body = s.get("/api/status")
    check("状态接口就绪", status == 200 and body.get("ready") is True,
          body.get("message", ""))
    check("Cookie 已下发", bool(s.cookie_value("cardiolens_sid")))

    status, _ = s.get("/")
    check("SPA 壳可访问", status == 200, f"HTTP {status}")


# ================================================================ B 正常流程
def test_happy_path(s: Session) -> None:
    print("\n[B] 正常流程")
    status, body = s.get("/api/records")
    check("记录列表 200", status == 200, f"HTTP {status}")
    records = body.get("records", [])
    check("记录数与非空", len(records) > 0, f"{len(records)} 条")
    check("含推荐记录标记", any(r.get("recommended") for r in records))
    check("记录带训练/测试划分", all("split" in r for r in records))

    status, body = s.get(f"/api/preview?record_id={RECORD}&start=0&duration=10")
    check("预览 200", status == 200, f"HTTP {status}")
    check("预览返回 3600 个采样点（10s × 360Hz）",
          len(body.get("signal", [])) == 3600, f"实际 {len(body.get('signal', []))}")
    check("预览带 R 峰标注", len(body.get("beat_marks", [])) == body.get("n_beats_in_window"))
    check("预览的采样点下标是窗口内相对值",
          all(0 <= m["sample"] < 3600 for m in body.get("beat_marks", [])))

    status, body = s.post("/api/analyze", {
        "record_id": RECORD, "start_sec": START_SEC,
        "duration_sec": DURATION_SEC, "with_cam": True,
    })
    check("分析 200", status == 200, f"HTTP {status}")
    beats = body.get("beats", [])
    check("逐搏结果非空", len(beats) > 0, f"{len(beats)} 搏")
    check("概率之和为 1", all(abs(sum(b["probs"].values()) - 1) < 1e-3 for b in beats))
    check("cam 长度与心搏采样点对齐",
          all(len(b.get("cam", [])) == 252 for b in beats))
    check("预测类别取自五分类",
          all(b["pred"] in ("N", "S", "V", "F", "Q") for b in beats))
    check("预测类别与概率最大值一致",
          all(b["pred"] == max(b["probs"], key=b["probs"].get) for b in beats))
    check("窗口内计数与逐搏条数一致",
          body["summary"]["n_beats"] == len(beats))
    check("划分标记正确（记录 100 属测试集）",
          body["in_training_set"] is False and body["split"].startswith("DS2"),
          f"split={body['split']}")

    status, body = s.post("/api/analyze", {
        "record_id": "208", "start_sec": 0, "duration_sec": 10, "with_cam": False,
    })
    check("关闭 Grad-CAM 时不返回 cam 字段",
          status == 200 and all("cam" not in b for b in body.get("beats", [])))
    check("记录 208 属训练集", body.get("in_training_set") is True,
          f"split={body.get('split')}")

    status, body = s.get("/api/metrics")
    check("指标接口 200", status == 200, f"HTTP {status}")
    check("指标含主指标名", "main_metric" in body)


# ================================================================ C 负向校验
def test_negative(s: Session) -> None:
    print("\n[C] 输入校验（负向分支）")
    cases = [
        ("记录号不存在", {"record_id": "999"}),
        ("缺少 record_id", {"start_sec": 0}),
        ("时长为负", {"record_id": RECORD, "duration_sec": -5}),
        ("时长过短", {"record_id": RECORD, "duration_sec": 1}),
        ("时长超上限", {"record_id": RECORD, "duration_sec": 60}),
        ("起始为负", {"record_id": RECORD, "start_sec": -5}),
        ("起始非数字", {"record_id": RECORD, "start_sec": "abc"}),
        ("时长非数字", {"record_id": RECORD, "duration_sec": "abc"}),
        ("标题过长", {"record_id": RECORD, "duration_sec": 10, "save": True,
                      "title": "长" * 200}),
    ]
    for name, payload in cases:
        status, body = s.post("/api/analyze", payload)
        check(f"拒绝：{name}", status == 400 and body.get("ok") is False,
              f"HTTP {status} {body.get('error', '')}")

    raw_cases = [
        ("NaN", b'{"record_id":"100","duration_sec":NaN}'),
        ("+Infinity", b'{"record_id":"100","start_sec":Infinity}'),
        ("-Infinity", b'{"record_id":"100","duration_sec":-Infinity}'),
    ]
    for name, raw in raw_cases:
        status, _ = s.request("POST", "/api/analyze", raw=raw)
        check(f"拒绝：{name}（原始字节）", status == 400, f"HTTP {status}")

    status, _ = s.request("POST", "/api/analyze", raw=b"not json")
    check("拒绝：非法 JSON", status == 400, f"HTTP {status}")

    status, _ = s.post("/api/analyze", [1, 2, 3])
    check("拒绝：JSON 数组", status == 400, f"HTTP {status}")

    status, body = s.get("/api/preview?record_id=999&start=0&duration=10")
    check("预览参数非法返回 400", status == 400, f"HTTP {status}")

    status, body = s.get("/api/does-not-exist")
    check("未知接口返回 JSON 404", status == 404 and body.get("ok") is False,
          f"HTTP {status}")


# ================================================================ D 历史 CRUD
def test_history(s: Session) -> None:
    print("\n[D] 历史记录增删查")
    status, body = s.post("/api/analyze", {
        "record_id": RECORD, "start_sec": START_SEC, "duration_sec": DURATION_SEC,
        "save": True, "title": "端到端自检报告",
    })
    aid = body.get("saved_id")
    check("保存返回 saved_id", isinstance(aid, int), str(aid))

    _, body = s.get("/api/history")
    check("列表含刚保存的报告", any(i["id"] == aid for i in body["items"]))
    check("列表统计与条数一致",
          body["stats"]["total_analyses"] == len(body["items"]))

    status, body = s.get(f"/api/history/{aid}")
    check("详情可读", status == 200 and body.get("title") == "端到端自检报告")
    check("详情含逐搏 payload", bool(body.get("payload", {}).get("beats")))

    status, _ = s.delete(f"/api/history/{aid}")
    check("删除成功", status == 200, f"HTTP {status}")
    status, _ = s.get(f"/api/history/{aid}")
    check("删除后 404", status == 404, f"HTTP {status}")
    status, _ = s.delete(f"/api/history/{aid}")
    check("重复删除返回 404", status == 404, f"HTTP {status}")

    s.post("/api/analyze", {"record_id": RECORD, "start_sec": 0,
                            "duration_sec": DURATION_SEC, "save": True})
    status, body = s.post("/api/history/clear", {})
    check("清空返回删除条数", status == 200 and body.get("deleted") == 1,
          str(body.get("deleted")))
    _, body = s.get("/api/history")
    check("清空后列表为空", body["items"] == [])


# ================================================================ E 会话隔离
def test_isolation() -> None:
    """跨会话隔离（真实 HTTP + 两个独立 CookieJar）。

    与离线套件的同名测试互补：这里走的是**真实的 Cookie 往返**——
    Cookie 由服务端 Set-Cookie 下发、由客户端 CookieJar 保存并回传，
    而离线套件的 test_client 可以绕过这一层。会话隔离本质上是"凭据如何
    绑定请求"的问题，因此真实往返是必要的验证。

    测试设计上的三点要求：
      1. 必须有**正向对照**（A 能读自己的、B 也能读自己的），否则 404
         无法排除"端点本身坏了"这一解释；
      2. 必须断言**响应体内容**，而不只是状态码；
      3. **不能把 405 当作隔离证据**——`/api/history/<id>` 只注册了
         GET 与 DELETE，用 POST 请求得到 405 只说明方法不存在。
         跨会话请求一律使用**路由实际允许的方法**。
    """
    print("\n[E] 会话隔离（两个独立 CookieJar，逐一覆盖历史端点）")
    a, b = Session(), Session()

    a.get("/api/status")
    b.get("/api/status")
    check("两个会话的 Cookie 不同",
          a.cookie_value("cardiolens_sid") != b.cookie_value("cardiolens_sid"))
    check("两次会话的 Cookie 都不为空",
          bool(a.cookie_value("cardiolens_sid")) and bool(b.cookie_value("cardiolens_sid")))

    secret_title = "A-SECRET-e2e-51c4"
    _, body = a.post("/api/analyze", {
        "record_id": RECORD, "start_sec": START_SEC, "duration_sec": DURATION_SEC,
        "save": True, "title": secret_title,
    })
    a_id = body.get("saved_id")
    _, body = b.post("/api/analyze", {
        "record_id": RECORD, "start_sec": START_SEC + 2,
        "duration_sec": DURATION_SEC, "save": True, "title": "B 自己的报告",
    })
    b_id = body.get("saved_id")
    check("A 与 B 各自保存成功且 id 不同",
          isinstance(a_id, int) and isinstance(b_id, int) and a_id != b_id,
          f"A={a_id} B={b_id}")

    # ---------- 正向对照 ----------
    status, body = a.get(f"/api/history/{a_id}")
    check("正向对照：A 读自己的记录 → 200", status == 200, f"HTTP {status}")
    check("正向对照：A 读到的是自己那条（标题一致）",
          body.get("title") == secret_title)
    check("正向对照：A 的详情含逐搏 payload", bool(body.get("payload", {}).get("beats")))

    status, body = b.get(f"/api/history/{b_id}")
    check("正向对照：B 读自己的记录 → 200（证明端点对 B 可用）",
          status == 200, f"HTTP {status}")

    # ---------- 列表端点 ----------
    _, a_list = a.get("/api/history")
    _, b_list = b.get("/api/history")
    check("A 的列表只含自己那 1 条", len(a_list["items"]) == 1, f"{len(a_list['items'])} 条")
    check("B 的列表只含自己那 1 条", len(b_list["items"]) == 1, f"{len(b_list['items'])} 条")
    check("B 的列表不含 A 的记录 id",
          a_id not in [i["id"] for i in b_list["items"]])
    check("B 的列表不含 A 的标题",
          secret_title not in json.dumps(b_list, ensure_ascii=False))

    # ---------- 详情端点：GET（路由允许的方法）----------
    status, body = b.get(f"/api/history/{a_id}")
    check("B 读 A 的记录 → 404（而非 403，不泄露存在性）",
          status == 404, f"HTTP {status}")
    raw = json.dumps(body, ensure_ascii=False)
    check("B 的 404 响应体不含 A 的标题", secret_title not in raw)
    check("B 的 404 响应体不含逐搏数据或 payload",
          "beats" not in raw and "payload" not in raw)

    # ---------- 删除端点：DELETE ----------
    status, body = b.delete(f"/api/history/{a_id}")
    check("B 删 A 的记录 → 404", status == 404, f"HTTP {status}")
    check("B 的删除响应体不含 A 的标题",
          secret_title not in json.dumps(body, ensure_ascii=False))
    status, body = a.get(f"/api/history/{a_id}")
    check("B 删除后 A 的记录仍然存在且可读",
          status == 200 and body.get("title") == secret_title, f"HTTP {status}")

    # ---------- 清空端点：只影响自己 ----------
    status, body = b.post("/api/history/clear", {})
    check("B 清空只删掉自己那 1 条", body.get("deleted") == 1,
          f"deleted={body.get('deleted')}")
    _, b_list = b.get("/api/history")
    check("B 清空后自己的列表为空", b_list["items"] == [])
    status, body = a.get(f"/api/history/{a_id}")
    check("B 清空后 A 的记录仍可读",
          status == 200 and body.get("title") == secret_title, f"HTTP {status}")
    _, a_list = a.get("/api/history")
    check("B 清空后 A 的列表仍有 1 条", len(a_list["items"]) == 1)

    # ---------- 明确排除"用错方法"这类假证据 ----------
    status, _ = b.request("POST", f"/api/history/{a_id}", payload={})
    check("405（方法不存在）不是隔离证据——此处仅记录事实",
          status in (404, 405), f"HTTP {status}（不作为隔离结论的依据）")

    # ---------- 凭据不外泄 ----------
    _, body = a.get("/api/history")
    raw = json.dumps(body, ensure_ascii=False)
    check("历史响应不含 owner 字段", "owner" not in raw)
    check("历史响应不含会话标识明文",
          a.cookie_value("cardiolens_sid")[:16] not in raw)


# ================================================================ F 并发实测
def test_concurrency() -> None:
    print("\n[F] 并发实测")
    session = Session()
    session.get("/api/status")

    payload = {"record_id": RECORD, "start_sec": START_SEC,
               "duration_sec": DURATION_SEC, "with_cam": True}

    n = 8
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(
            lambda _: session.post("/api/analyze", payload, timeout=60), range(n)))
    elapsed = time.perf_counter() - t0

    codes = [c for c, _ in results]
    ok = sum(1 for c in codes if c == 200)
    print(f"      {n} 个并发请求耗时 {elapsed:.2f}s，状态码 {codes}")

    check(f"{n} 个并发分析请求全部成功", ok == n, f"{ok}/{n}，状态码 {codes}")
    check("并发下没有 5xx", not any(c >= 500 for c in codes), str(codes))
    check("并发下没有请求被拒绝（限流未误伤）",
          not any(c == 429 for c in codes), str(codes))

    # 结果必须与串行一致：并发不能改变推理结果
    first = results[0][1]
    same = all(
        [b["pred"] for b in r.get("beats", [])] == [b["pred"] for b in first.get("beats", [])]
        for _, r in results)
    check("并发返回的结果彼此一致（推理未被串扰）", same)

    check("总耗时在合理范围（< 30s）", elapsed < 30, f"{elapsed:.2f}s")


# ================================================================ G 性能基准
def test_benchmark() -> None:
    print("\n[G] 单次分析耗时基准")
    session = Session()
    session.get("/api/status")

    def timeit(with_cam: bool, duration: float) -> float:
        t0 = time.perf_counter()
        session.post("/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC,
            "duration_sec": duration, "with_cam": with_cam,
        }, timeout=60)
        return time.perf_counter() - t0

    timeit(True, 10)                      # 预热：排除首次加载模型的影响
    samples = [timeit(True, 30) for _ in range(3)]

    median = statistics.median(samples)
    print(f"      30 秒窗口（含 Grad-CAM）三次耗时："
          f"{[f'{s:.3f}s' for s in samples]}，中位数 {median:.3f}s")

    check("单次分析在 5 秒内返回", median < 5.0, f"中位数 {median:.3f}s")
    check("耗时量级与文档描述一致（亚秒级）", median < 1.5,
          f"中位数 {median:.3f}s —— 若明显偏大，需重新校准并发槽位与超时参数")

    # 30 秒窗口的响应体积，用于核对 nginx 的 gzip 与缓冲配置
    _, body = session.post("/api/analyze", {
        "record_id": RECORD, "start_sec": START_SEC,
        "duration_sec": 30, "with_cam": True,
    })
    size_kb = len(json.dumps(body).encode("utf-8")) / 1024
    print(f"      30 秒窗口响应体积约 {size_kb:.0f} KB")
    check("响应体积在预期范围（0.05~0.6 MB）", 50 < size_kb < 600, f"{size_kb:.0f} KB")


# ================================================================ 主流程
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    print("=" * 70)
    print("  CardioLens Web 版端到端测试（真实 HTTP + 真实 WSGI）")
    print(f"  地址：{BASE}")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="cardiolens_e2e_"))
    store = tmp / "store"
    store.mkdir(parents=True, exist_ok=True)
    print(f"  临时数据目录：{store}（不触碰真实数据库）")

    proc = None
    try:
        proc = start_server(store)
        print("  服务已就绪\n")

        session = Session()
        test_availability(session)
        test_happy_path(session)
        test_negative(session)
        test_history(session)
        test_isolation()
        test_concurrency()
        test_benchmark()
    except Exception as exc:                                  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("端到端测试执行未抛异常", False, f"{type(exc).__name__}: {exc}")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

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
    sys.exit(main())
