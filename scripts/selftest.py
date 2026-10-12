"""【旧 Web 版接口自测】—— 针对已退役的 Flask 实现，仅作留档与回归对照。

CardioLens 现在是一款纯 PySide6 原生桌面软件（入口 desktop/main.py），
桌面版的自检脚本是 scripts/test_desktop.py。
本脚本测的是迁移前的 Web 版接口，被测对象已移动到 legacy_web/，
运行方式也相应改为 python -m legacy_web.app。桌面版的运行路径完全
不依赖本脚本，也不依赖 legacy_web/。

覆盖三类共 32 个用例：
  1. 正常流程 —— 状态查询、记录列表、波形预览、完整分析、历史增删查；
     并在分析结果上顺带校验数据一致性（概率归一、Grad-CAM 长度、
     预测类别与最大概率一致、逐搏计数与汇总一致、异常占比计算）
  2. 输入校验 —— 非法记录号、时长越界、负数起始、非数字、缺少字段、非 JSON 请求体
  3. 历史记录 —— 保存报告、读取列表、读取详情、删除记录、读取/删除不存在的记录

用法：
    python scripts/selftest.py            # 若服务未启动则自动拉起
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:            # 允许直接以脚本方式运行（python scripts/selftest.py）
    sys.path.insert(0, str(ROOT))

from src import config as C                # noqa: E402
from src.config import force_utf8_stdout   # noqa: E402

BASE = "http://127.0.0.1:5000"

TESTS: list[tuple[str, callable]] = []
CTX: dict = {}


def test(name: str):
    def deco(fn):
        TESTS.append((name, fn))
        return fn
    return deco


def req(method: str, path: str, body=None, raw: bytes | None = None,
        content_type: str = "application/json"):
    """发起请求，返回 (状态码, 解析后的 JSON 或 None)。"""
    url = BASE + path
    data = raw if raw is not None else (
        json.dumps(body).encode("utf-8") if body is not None else None
    )
    r = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(payload)
            except json.JSONDecodeError:
                return resp.status, None
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, None


def server_alive() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/status", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# ============================================================ 1. 正常流程
@test("状态接口返回就绪标志")
def _():
    code, j = req("GET", "/api/status")
    assert code == 200, f"HTTP {code}"
    assert j["ok"] is True
    assert j["ready"] is True, f"系统未就绪：{j['message']}"


@test("记录列表非空且包含推荐记录")
def _():
    code, j = req("GET", "/api/records")
    assert code == 200 and j["ok"]
    recs = j["records"]
    assert len(recs) > 0, "记录列表为空"
    assert any(r["recommended"] for r in recs), "没有标记推荐记录"
    CTX["rec"] = recs[0]["id"]
    CTX["records"] = recs


@test("波形预览返回信号与心搏标记")
def _():
    code, j = req("GET", f"/api/preview?record_id={CTX['rec']}&start=0&duration=10")
    assert code == 200 and j["ok"], j
    assert len(j["signal"]) > 0, "信号为空"
    assert j["n_beats_in_window"] > 0, "窗口内无标注心搏"
    assert len(j["beat_marks"]) == j["n_beats_in_window"]


@test("完整分析返回逐搏结果且概率归一")
def _():
    code, j = req("POST", "/api/analyze",
                  {"record_id": CTX["rec"], "start_sec": 0, "duration_sec": 10})
    assert code == 200 and j["ok"], j
    assert j["beats"], "无逐搏结果"
    assert j["summary"]["n_beats"] == len(j["beats"])
    assert len(j["signal"]) == j["n_samples"]

    for b in j["beats"][:20]:
        total = sum(b["probs"].values())
        assert abs(total - 1.0) < 0.02, f"概率和偏离 1：{total}"
        assert 0.0 <= b["confidence"] <= 1.0
        assert b["pred"] in ("N", "S", "V", "F", "Q")
        assert len(b["cam"]) == 252, f"Grad-CAM 长度应为 252，实际 {len(b['cam'])}"
        assert b["pred"] == max(b["probs"], key=b["probs"].get), "预测类别与最大概率不一致"
    CTX["payload"] = j


@test("汇总统计与逐搏明细一致")
def _():
    j = CTX["payload"]
    s = j["summary"]
    counts = {c: 0 for c in ("N", "S", "V", "F", "Q")}
    for b in j["beats"]:
        counts[b["pred"]] += 1
    assert counts == s["counts"], f"计数不一致 {counts} vs {s['counts']}"
    assert s["abnormal_count"] == s["n_beats"] - counts["N"]
    assert abs(s["abnormal_ratio"] - s["abnormal_count"] / s["n_beats"]) < 1e-3
    assert s["risk_level"]["code"] in ("low", "medium", "high")


@test("关闭 Grad-CAM 时结果不含 cam 字段")
def _():
    code, j = req("POST", "/api/analyze",
                  {"record_id": CTX["rec"], "start_sec": 2, "duration_sec": 8,
                   "with_cam": False})
    assert code == 200 and j["ok"], j
    assert "cam" not in j["beats"][0], "with_cam=False 时不应返回 cam"


@test("窗口超出记录末尾时向前回退而非报错")
def _():
    rec = next(r for r in CTX["records"] if r["id"] == CTX["rec"])
    total = rec["duration_sec"]
    code, j = req("POST", "/api/analyze",
                  {"record_id": CTX["rec"], "start_sec": total - 5, "duration_sec": 20})
    assert code == 200 and j["ok"], f"应回退窗口，实际 {code} {j}"
    # 窗口长度应保持 20 秒，且整体落在记录范围内
    assert abs(j["duration_sec"] - 20) < 0.1, f"窗口长度被改动：{j['duration_sec']}"
    assert j["start_sec"] + j["duration_sec"] <= total + 0.1, "窗口越过了记录末尾"


@test("分析结果标注记录所属的训练/测试划分")
def _():
    # 训练集记录模型见过，界面需据此提示"一致率偏高、不代表泛化能力"，
    # 因此后端必须如实返回该记录属于 DS1 还是 DS2。
    code, j = req("POST", "/api/analyze",
                  {"record_id": "208", "start_sec": 0, "duration_sec": 10})
    assert code == 200 and j["ok"], j
    assert j["in_training_set"] is True, "记录 208 属训练集 DS1，应标记 in_training_set=True"
    assert "DS1" in j["split"], f"划分字段异常：{j['split']}"

    code, j = req("POST", "/api/analyze",
                  {"record_id": "100", "start_sec": 0, "duration_sec": 10})
    assert code == 200 and j["ok"], j
    assert j["in_training_set"] is False, "记录 100 属测试集 DS2，应标记 in_training_set=False"
    assert "DS2" in j["split"], f"划分字段异常：{j['split']}"


# ============================================================ 2. 输入校验
def _expect_400(name, body, raw=None, content_type="application/json"):
    def fn():
        code, j = req("POST", "/api/analyze", body, raw=raw, content_type=content_type)
        assert code == 400, f"应返回 400，实际 {code}"
        assert j and j["ok"] is False, "应返回 ok=false"
        assert j.get("error"), "应包含错误说明"
    _expect_400.cases.append((name, fn))


_expect_400.cases = []


_expect_400("非法记录编号", {"record_id": "99999", "start_sec": 0, "duration_sec": 10})
_expect_400("记录编号不存在", {"record_id": "abc", "start_sec": 0, "duration_sec": 10})
_expect_400("缺少 record_id", {"start_sec": 0, "duration_sec": 10})
_expect_400("时长为负", {"record_id": "100", "start_sec": 0, "duration_sec": -5})
_expect_400("时长过短", {"record_id": "100", "start_sec": 0, "duration_sec": 1})
_expect_400("时长超上限", {"record_id": "100", "start_sec": 0, "duration_sec": 999})
_expect_400("起始时间为负", {"record_id": "100", "start_sec": -10, "duration_sec": 10})
_expect_400("起始时间非数字", {"record_id": "100", "start_sec": "abc", "duration_sec": 10})
_expect_400("时长非数字", {"record_id": "100", "start_sec": 0, "duration_sec": "xyz"})
_expect_400("标题超长", {"record_id": "100", "start_sec": 0, "duration_sec": 10,
                        "save": True, "title": "长" * 200})

# NaN / Infinity 不是合法 JSON 数值，但 Python 的 json.loads 默认接受这三个字面量。
# 若不显式拦截，它们会一路传进窗口计算，产生 int(nan) 之类的崩溃。
# 这里用原始字节构造非法数值，验证后端确实做了有限性检查。
_expect_400("起始时间为 NaN", None, raw=b'{"record_id":"100","start_sec":NaN,"duration_sec":10}')
_expect_400("起始时间为 Infinity", None,
            raw=b'{"record_id":"100","start_sec":Infinity,"duration_sec":10}')
_expect_400("起始时间为 -Infinity", None,
            raw=b'{"record_id":"100","start_sec":-Infinity,"duration_sec":10}')
_expect_400("时长为 NaN", None, raw=b'{"record_id":"100","start_sec":0,"duration_sec":NaN}')
_expect_400("时长为 Infinity", None,
            raw=b'{"record_id":"100","start_sec":0,"duration_sec":Infinity}')

# 记录 100 总长 30 分钟；请求 3600 秒远超记录本身
_expect_400("时长超出记录总长度", {"record_id": "100", "start_sec": 0, "duration_sec": 3600})


@test("请求体非合法 JSON 被拒绝")
def _():
    code, j = req("POST", "/api/analyze", raw=b"{not valid json",
                  content_type="application/json")
    assert code == 400, f"应返回 400，实际 {code}"
    assert j and j["ok"] is False


@test("请求体为 JSON 数组被拒绝")
def _():
    code, j = req("POST", "/api/analyze", raw=b"[1,2,3]",
                  content_type="application/json")
    assert code == 400, f"应返回 400，实际 {code}"


# 动态注册带参数的校验用例
for _name, _fn in _expect_400.cases:
    TESTS.append((f"输入校验 · {_name}", _fn))


@test("预览接口参数非法时返回 400")
def _():
    code, j = req("GET", "/api/preview?record_id=99999&start=0&duration=10")
    assert code == 400, f"应返回 400，实际 {code}"
    assert j["ok"] is False

    code, j = req("GET", "/api/preview?record_id=100&start=0&duration=9999")
    assert code == 400, "时长超上限应返回 400"


@test("不存在的接口返回 404 JSON")
def _():
    code, j = req("GET", "/api/does-not-exist")
    assert code == 404, f"应返回 404，实际 {code}"
    assert j and j["ok"] is False


# ============================================================ 3. 历史记录
@test("保存分析报告并写入历史")
def _():
    code, j = req("POST", "/api/analyze",
                  {"record_id": CTX["rec"], "start_sec": 0, "duration_sec": 10,
                   "save": True, "title": "自测用例报告"})
    assert code == 200 and j["ok"], j
    assert j.get("saved_id"), "未返回 saved_id"
    CTX["saved_id"] = j["saved_id"]

    code, h = req("GET", "/api/history")
    assert code == 200 and h["ok"]
    assert any(it["id"] == CTX["saved_id"] for it in h["items"]), "历史中找不到刚保存的报告"


@test("读取历史详情")
def _():
    code, j = req("GET", f"/api/history/{CTX['saved_id']}")
    assert code == 200 and j["ok"], j
    assert j["payload"]["beats"], "详情缺少逐搏数据"
    assert j["record_id"] == CTX["rec"]


@test("删除历史记录")
def _():
    code, j = req("DELETE", f"/api/history/{CTX['saved_id']}")
    assert code == 200 and j["ok"], j
    code, j = req("GET", f"/api/history/{CTX['saved_id']}")
    assert code == 404, "删除后仍能读到该记录"


@test("读取/删除不存在的记录返回 404")
def _():
    code, _j = req("GET", "/api/history/999999")
    assert code == 404, f"GET 应返回 404，实际 {code}"
    code, _j = req("DELETE", "/api/history/999999")
    assert code == 404, f"DELETE 应返回 404，实际 {code}"


# ============================================================ 执行
def main() -> int:
    # Windows 控制台默认 GBK，下面用到的 ✓/✗ 与中文会触发 UnicodeEncodeError
    force_utf8_stdout()
    proc = None
    if not server_alive():
        print("[自测] 服务未运行，正在启动 Flask（旧 Web 版：legacy_web.app）...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "legacy_web.app"], cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 60
        while time.time() < deadline and not server_alive():
            time.sleep(1)
        if not server_alive():
            print("[自测] 启动服务失败，请手动运行 python -m legacy_web.app")
            if proc:
                proc.terminate()
            return 1

    print("=" * 70)
    print(f"  {C.APP_NAME} {C.APP_NAME_ZH} · 接口自测")
    print("=" * 70)

    passed, failed = 0, []
    for i, (name, fn) in enumerate(TESTS, 1):
        try:
            fn()
            passed += 1
            print(f"  [{i:2d}/{len(TESTS)}] ✓  {name}")
        except Exception as e:
            failed.append((name, str(e)))
            print(f"  [{i:2d}/{len(TESTS)}] ✗  {name}")
            print(f"            -> {e}")

    print("-" * 70)
    print(f"  通过 {passed} / {len(TESTS)}，失败 {len(failed)}")
    if failed:
        print("  失败明细：")
        for name, err in failed:
            print(f"    · {name}: {err}")
    print("=" * 70)

    if proc:
        proc.terminate()
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
