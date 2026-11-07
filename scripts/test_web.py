"""CardioLens Web 版自检脚本（离线运行，不修改任何模型、数据或推理逻辑）。

覆盖范围：
     1  就绪检查，且**不依赖** beats.npz（91 MB 训练样本集）
     2  改进前基线构件的 MD5 未被覆盖，当前构件存在
     3  接口返回的逐搏结果 == 直接驱动模型独立复算的结果
     4  Grad-CAM 长度与心搏采样点对齐
     5  逐搏汇总的算术自洽
     6  数据库 schema（含新增的 owner 列）与 src/db.py 一致
     7  历史记录的保存 / 读取 / 删除 / 清空
     8  会话隔离（本次改造的重心）
     9  输入校验的负向分支（含 NaN / ±Infinity 的原始字节）
    10  HTTP 语义：接口 404 返回 JSON、方法错返回 405、SPA 路由与未知路径
    11  请求体上限与 Content-Type 校验
    12  限流
    13  并发槽位耗尽
    14  /media 白名单（防止模型权重与训练日志外泄）
    15  静态审计：后端不含 PySide6、前端不用 v-html / innerHTML
    16  用户可见文案：免责声明完整且不含桌面版遗留表述
    17  旧库迁移回归（老 schema → 新 schema，数据不丢）

用法：
    python scripts/test_web.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------- 临时数据目录
# 必须在导入 src.config 之前设好环境变量，让「可写数据目录」一开始就指向临时位置。
TMP = Path(tempfile.mkdtemp(prefix="cardiolens_web_"))
os.environ["CARDIOLENS_STORE"] = str(TMP / "store")
os.environ["CARDIOLENS_SECRET_KEY"] = "test-secret-key"

import numpy as np                                    # noqa: E402
import torch                                          # noqa: E402

from src import config as C                           # noqa: E402
from src import db                                    # noqa: E402

# 双保险：即使环境变量没生效，也把三个路径属性直接改掉。
# （db.connect() 是在调用时读取 C.DB_PATH 的，因此这样改一定生效。）
C.STORE_DIR = TMP / "store"
C.LOG_DIR = C.STORE_DIR / "logs"
C.DB_PATH = C.STORE_DIR / "app.db"
C.STORE_DIR.mkdir(parents=True, exist_ok=True)
C.LOG_DIR.mkdir(parents=True, exist_ok=True)

from web import create_app                            # noqa: E402
from web import guard                                 # noqa: E402
from web.config import TestConfig                     # noqa: E402

app = create_app(TestConfig)
db.init_db()


# 测试专用的日志探针路由：必须**在任何请求之前**注册（Flask 不允许在首个请求
# 之后再往路由表里加东西）。用途是让"未捕获异常会写日志"这条路径在测试里真实
# 发生一次——否则"会话标识不在日志里"就成了空断言（因为没有日志可查）。
# 同时也顺带覆盖了 500 兜底响应。
@app.get("/api/_log_probe")
def _log_probe():                                   # pragma: no cover - 测试用
    raise RuntimeError("隔离测试用的日志探针")

RECORD = "100"
START_SEC, DURATION_SEC = 10.0, 10.0

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


def new_client():
    """每个 client 自带独立 cookie jar，等价于一个独立浏览器。"""
    return app.test_client()


def post_json(client, url, payload, **kw):
    return client.post(url, data=json.dumps(payload), content_type="application/json", **kw)


class no_rate_limit:
    """在需要连续打同一接口的分组里临时关闭限流。

    限流本身由第 12 组专门覆盖；其他分组若被它干扰，失败原因会很难定位。
    """

    def __enter__(self):
        self._saved = dict(app.config["RATE_LIMITS"])
        app.config["RATE_LIMITS"] = {}
        guard.reset_rate_limits()
        return self

    def __exit__(self, *exc):
        app.config["RATE_LIMITS"] = self._saved
        guard.reset_rate_limits()
        return False


BASELINE_MD5 = {
    "models/baseline/ecg_cnn_before_improvement.pt": "a5ca4a0ec6d0330303a590a6d35c4fa3",
    "models/baseline/metrics_before_improvement.json": "db51fef423254c391dce5a27081d8cc8",
    "models/baseline/beats_before_improvement.npz": "f27ed5050405b5c63bd803bb2acf57ab",
}


def _all_keys(obj, out=None):
    """递归收集 JSON 里出现过的所有键名。"""
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _all_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _all_keys(v, out)
    return out


# ================================================================ 1 就绪
def test_readiness() -> None:
    print("\n[1] 就绪检查")
    from web.readiness import check as ready_check

    r = ready_check()
    check("推理链路所需文件齐备", r.ok, r.message)
    check("就绪检查不要求 beats.npz",
          not any("beats" in m for m in r.missing),
          "缺失项：" + ("、".join(r.missing) or "无"))

    # 直接把 BEATS_NPZ 指向不存在的路径，就绪状态不应受影响。
    # 这是"服务器只部署运行最小集"场景的回归保护。
    saved = C.BEATS_NPZ
    try:
        C.BEATS_NPZ = TMP / "does-not-exist.npz"
        r2 = ready_check()
        check("beats.npz 不存在时就绪检查仍通过", r2.ok, r2.message)
    finally:
        C.BEATS_NPZ = saved


# ================================================================ 2 MD5
def test_hashes() -> None:
    print("\n[2] 改进前基线构件的 MD5 与当前构件存在性")
    for rel, want in BASELINE_MD5.items():
        path = ROOT / rel
        if not path.exists():
            check(f"{rel} 存在", False, "文件缺失")
            continue
        got = md5(path)
        check(f"{rel} 基线未被覆盖", got == want, got if got == want else f"期望 {want}，实际 {got}")
    for rel in ("models/ecg_cnn.pt", "models/metrics.json", "data/processed/beats.npz"):
        check(f"当前构件 {rel} 存在", (ROOT / rel).exists())


# ================================================================ 3 推理一致
def _independent_inference():
    """不经 src.inference，直接用原始文件与权重独立复算一遍。

    输入张量的构造严格按 src/inference.py 的预处理方式重写：
    按 R 峰前后 90/162 采样点截取 → 去均值除标准差 → float32。
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
        seg = signal[a["sample"] - C.PRE_SAMPLES: a["sample"] + C.POST_SAMPLES]
        std = float(seg.std())
        norm_beats.append((seg - seg.mean()).astype(np.float32) if std < 1e-8
                          else ((seg - seg.mean()) / std).astype(np.float32))
    x = torch.from_numpy(np.stack(norm_beats)[:, None, :].astype(np.float32))

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


def test_inference_consistency() -> None:
    print("\n[3] 接口结果 vs 独立复算（同一时间窗）")
    client = new_client()
    with no_rate_limit():
        resp = post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC,
            "duration_sec": DURATION_SEC, "with_cam": True,
        })
    check("分析接口返回 200", resp.status_code == 200, f"实际 {resp.status_code}")
    if resp.status_code != 200:
        return
    result = resp.get_json()

    in_win, _x, _rb, probs = _independent_inference()
    beats = result["beats"]

    check("搏动数一致", len(beats) == len(in_win),
          f"接口 {len(beats)}，复算 {len(in_win)}")

    names = C.AAMI_CLASSES
    pred_ok = conf_ok = True
    max_diff = 0.0
    for i, b in enumerate(beats):
        if b["pred"] != names[int(probs[i].argmax())]:
            pred_ok = False
        if abs(b["confidence"] - float(probs[i].max())) >= 1e-3:
            conf_ok = False
        for k, code in enumerate(names):
            max_diff = max(max_diff, abs(b["probs"][code] - float(probs[i][k])))

    check("逐搏预测类别与独立复算一致", pred_ok)
    check("五类概率与独立复算一致（误差 < 1e-3）", max_diff < 1e-3, f"最大偏差 {max_diff:.2e}")
    check("置信度等于预测类概率", conf_ok)
    check("R 峰位置与标注一致",
          all(b["abs_sample"] == a["sample"] for b, a in zip(beats, in_win)))
    check("RR 节律字段存在",
          all(k in beats[0] for k in
              ("rr_prev_sec", "rr_next_sec", "rr_baseline_sec",
               "rr_prev_ratio", "rr_next_ratio")))
    check("把预测类概率写进了 probs 字典",
          all(b["probs"][b["pred"]] == b["confidence"] for b in beats))


# ================================================================ 4 Grad-CAM
def test_gradcam() -> None:
    print("\n[4] Grad-CAM")
    client = new_client()
    with no_rate_limit():
        with_cam = post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC,
            "duration_sec": DURATION_SEC, "with_cam": True,
        }).get_json()
        without = post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC,
            "duration_sec": DURATION_SEC, "with_cam": False,
        }).get_json()

    cams = [b.get("cam") for b in with_cam["beats"]]
    check("每个搏动都带 cam", all(c is not None for c in cams))
    check(f"cam 长度恒为 {C.BEAT_LEN}（与心搏采样点对齐）",
          all(len(c) == C.BEAT_LEN for c in cams if c),
          f"实际长度集合 {sorted({len(c) for c in cams if c})}")
    check("cam 取值落在 [0, 1]",
          all(0.0 <= v <= 1.0 for c in cams if c for v in c))
    check("关闭 Grad-CAM 时不含 cam 字段",
          all("cam" not in b for b in without["beats"]))
    check("关闭 Grad-CAM 不影响预测类别",
          [b["pred"] for b in with_cam["beats"]] == [b["pred"] for b in without["beats"]])
    check("关闭 Grad-CAM 不影响概率",
          all(abs(a["confidence"] - b["confidence"]) < 1e-9
              for a, b in zip(with_cam["beats"], without["beats"])))


# ================================================================ 5 汇总
def test_summary() -> None:
    print("\n[5] 汇总算术自洽")
    data = post_json(new_client(), "/api/analyze", {
        "record_id": RECORD, "start_sec": START_SEC, "duration_sec": DURATION_SEC,
    }).get_json()
    s, beats = data["summary"], data["beats"]

    check("n_beats 与逐搏条数一致", s["n_beats"] == len(beats))
    counts = {}
    for b in beats:
        counts[b["pred"]] = counts.get(b["pred"], 0) + 1
    check("五类计数与逐搏结果一致",
          all(s["counts"].get(k, 0) == counts.get(k, 0) for k in C.AAMI_CLASSES),
          f"汇总 {s['counts']} / 实算 {counts}")
    check("异常数 = 总数 - N 类数",
          s["abnormal_count"] == s["n_beats"] - counts.get("N", 0))
    check("异常占比 = 异常数 / 总数",
          abs(s["abnormal_ratio"] - s["abnormal_count"] / s["n_beats"]) < 1e-3)
    agree = sum(1 for b in beats if b["agree"])
    check("一致率 = 一致搏动数 / 总数",
          abs(s["agreement"] - agree / s["n_beats"]) < 1e-3)
    check("平均置信度与逐搏均值一致",
          abs(s["mean_confidence"] - sum(b["confidence"] for b in beats) / len(beats)) < 1e-3)
    check("风险等级字段齐备",
          all(k in s["risk_level"] for k in ("code", "label", "color", "desc")))
    check("包含免责声明且为项目原文", data["disclaimer"] == C.DISCLAIMER)
    check("包含五分类说明", len(data["classes"]) == 5)
    check("训练/测试划分标记存在",
          data["split"].startswith(("DS1", "DS2"))
          and data["in_training_set"] == data["split"].startswith("DS1"))


# ================================================================ 6 schema
def test_schema() -> None:
    print("\n[6] 数据库 schema")
    conn = sqlite3.connect(C.DB_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(analyses)")]
    expected = [
        "id", "owner", "title", "record_id", "start_sec", "duration_sec", "n_beats",
        "abnormal_count", "abnormal_ratio", "risk_code", "risk_label", "agreement",
        "mean_conf", "counts_json", "payload_json", "created_at",
    ]
    check("列名与顺序符合新 schema（owner 在第 2 位）", cols == expected,
          f"实际 {cols}")
    idx = {r[1] for r in conn.execute(
        "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='analyses'")}
    check("(owner, id) 索引存在", "idx_analyses_owner" in idx, f"实际 {sorted(idx)}")
    check("(created_at) 索引存在", "idx_analyses_created" in idx)
    check("数据库落在临时目录内", str(C.DB_PATH).startswith(str(TMP)))
    conn.close()


# ================================================================ 7 历史 CRUD
def test_history_crud() -> None:
    print("\n[7] 历史记录增删查")
    client = new_client()
    with no_rate_limit():
        saved = post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC, "duration_sec": DURATION_SEC,
            "save": True, "title": "自检用报告",
        }).get_json()
        aid = saved.get("saved_id")
        check("保存后返回 saved_id", isinstance(aid, int), str(aid))

        items = client.get("/api/history").get_json()["items"]
        check("保存后出现在列表中", any(i["id"] == aid for i in items))
        check("列表过滤生效（只返回本人记录）", len(items) == 1, f"实际 {len(items)} 条")

        detail = client.get(f"/api/history/{aid}").get_json()
        check("详情可读且标题正确", detail.get("title") == "自检用报告")
        check("详情带完整 payload", bool(detail.get("payload", {}).get("beats")))
        check("详情带 created_at_ts（供前端算相对时间）",
              isinstance(detail.get("created_at_ts"), int))

        check("删除返回成功", client.delete(f"/api/history/{aid}").status_code == 200)
        check("删除后详情返回 404", client.get(f"/api/history/{aid}").status_code == 404)

        post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC, "duration_sec": DURATION_SEC,
            "save": True,
        })
        cleared = post_json(client, "/api/history/clear", {}).get_json()
        check("清空返回删除条数", cleared.get("deleted") == 1, str(cleared.get("deleted")))
        check("清空后列表为空", client.get("/api/history").get_json()["items"] == [])


# ================================================================ 8 会话隔离
def test_session_isolation() -> None:
    """跨会话隔离：逐一覆盖历史记录的每个端点。

    测试设计上的三点要求，都是为了避开"看起来通过但实际没证明任何事"：

    1. **必须有正向对照**。如果只断言"B 访问 A 的记录拿到 404"，那这个 404
       也可能意味着"这个端点本来就坏的"。因此先证明 A 能读自己的、B 也能读
       自己的，再证明 B 读不到 A 的——这样 404 才能归因于归属关系。

    2. **必须断言响应体内容**，而不只是状态码。404 的响应体里若混进了 A 的
       标题或记录内容，状态码再对也仍然是泄露。

    3. **不能把 405 当作隔离证据**。`/api/history/<id>` 只注册了 GET 与 DELETE，
       用 POST 去请求会得到 405，那只是"方法不存在"，与会话隔离无关。
       本测试只用**路由实际允许的方法**发起跨会话请求。
    """
    print("\n[8] 会话隔离（跨会话逐一覆盖历史记录的每个端点）")
    a, b = new_client(), new_client()

    # 用于识别"内容是否泄露"的独特标记
    secret_title = "A-SECRET-7f3a91"

    with no_rate_limit():
        # ---------- 准备：A 与 B 各自创建自己的记录 ----------
        a_first = post_json(a, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC, "duration_sec": DURATION_SEC,
            "save": True, "title": secret_title,
        }).get_json()["saved_id"]
        a_saved = post_json(a, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC + 1,
            "duration_sec": DURATION_SEC, "save": True, "title": "A 的第二份报告",
        }).get_json()["saved_id"]
        a_items = a.get("/api/history").get_json()["items"]
        a_ids = [i["id"] for i in a_items]
        assert len(a_ids) == 2, f"A 应有 2 条记录，实际 {len(a_ids)}"
        assert a_first in a_ids and a_saved in a_ids

        b_saved = post_json(b, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC + 2,
            "duration_sec": DURATION_SEC, "save": True, "title": "B 自己的报告",
        }).get_json()["saved_id"]

        # A 的标题（第二份）需要单独取一次以做内容断言
        a_title = a.get(f"/api/history/{a_saved}").get_json()["title"]

        # ---------- 正向对照 ----------
        # 没有这一组，后面的 404 就无法归因于归属关系
        r = a.get(f"/api/history/{a_saved}")
        check("正向对照：A 能读自己的记录（GET 详情 → 200）",
              r.status_code == 200, f"HTTP {r.status_code}")
        check("正向对照：A 读到的正是自己的那条（标题一致）",
              r.get_json().get("title") == a_title)
        check("正向对照：A 的详情含完整逐搏 payload",
              bool(r.get_json().get("payload", {}).get("beats")))

        r = b.get(f"/api/history/{b_saved}")
        check("正向对照：B 能读自己的记录（证明端点对 B 可用）",
              r.status_code == 200, f"HTTP {r.status_code}")

        check("A 的列表含自己的 2 条", len(a_items) == 2, f"{len(a_items)} 条")
        check("B 的列表只含自己的 1 条",
              len(b.get("/api/history").get_json()["items"]) == 1)

        # ---------- 列表端点：B 看不到 A 的任何一条 ----------
        b_list = b.get("/api/history").get_json()
        b_ids = [i["id"] for i in b_list["items"]]
        check("B 的列表中不含 A 的任何记录 id",
              not (set(b_ids) & set(a_ids)), f"B 看到 {b_ids}，A 的是 {a_ids}")
        check("B 的列表中不含 A 的标题",
              a_title not in json.dumps(b_list, ensure_ascii=False))

        # ---------- 详情端点：GET（路由允许的方法）----------
        r = b.get(f"/api/history/{a_saved}")
        check("B 读 A 的记录 → 404（而非 403，不泄露存在性）",
              r.status_code == 404, f"HTTP {r.status_code}")
        raw = r.get_data(as_text=True)
        check("B 的 404 响应体不含 A 的任何标题",
              a_title not in raw and secret_title not in raw)
        check("B 的 404 响应体不含逐搏数据", "beats" not in raw)
        check("B 的 404 响应体不含 payload 字段", "payload" not in raw)

        # ---------- 删除端点：DELETE ----------
        r = b.delete(f"/api/history/{a_saved}")
        check("B 删 A 的记录 → 404", r.status_code == 404, f"HTTP {r.status_code}")
        check("B 的删除响应体不含 A 的任何标题",
              a_title not in r.get_data(as_text=True)
              and secret_title not in r.get_data(as_text=True))
        # 关键：删除请求之后必须重新确认 A 的数据确实还在
        r = a.get(f"/api/history/{a_saved}")
        check("B 删除后 A 的记录仍然存在且可读",
              r.status_code == 200 and r.get_json().get("title") == a_title,
              f"HTTP {r.status_code}")

        # ---------- 清空端点：POST /api/history/clear ----------
        cleared = post_json(b, "/api/history/clear", {}).get_json()
        check("B 清空只删掉自己的那 1 条", cleared.get("deleted") == 1,
              f"deleted={cleared.get('deleted')}")
        check("B 清空后自己的列表为空",
              b.get("/api/history").get_json()["items"] == [])
        after = a.get("/api/history").get_json()["items"]
        check("B 清空后 A 的 2 条记录一条不少",
              [i["id"] for i in after] == a_ids, f"实际 {[i['id'] for i in after]}")
        r = a.get(f"/api/history/{a_saved}")
        check("B 清空后 A 仍能读到自己的记录",
              r.status_code == 200, f"HTTP {r.status_code}")

        # ---------- 统计口径按会话隔离 ----------
        check("A 的统计只含自己的 2 条",
              a.get("/api/status").get_json()["history"]["total_analyses"] == 2)
        check("B 的统计为空（刚清空）",
              b.get("/api/status").get_json()["history"]["total_analyses"] == 0)

        # ---------- 明确排除"用错方法"这类假证据 ----------
        # POST 到 /api/history/<id> 会得到 405，因为该路径只注册了 GET/DELETE。
        # 这只能说明方法用错了，**不能**用来证明会话隔离。
        r = post_json(b, f"/api/history/{a_saved}", {})
        check("405（方法不存在）不是隔离证据——此处仅记录事实",
              r.status_code in (404, 405),
              f"HTTP {r.status_code}（该值不作为隔离结论的依据）")

        # ---------- 凭据不外泄 ----------
        for resp in (a.get("/api/history"), a.get(f"/api/history/{a_saved}"),
                     a.get("/api/status"), post_json(a, "/api/analyze", {
                         "record_id": RECORD, "start_sec": START_SEC,
                         "duration_sec": DURATION_SEC})):
            keys = _all_keys(resp.get_json())
            check(f"{resp.request.path} 响应不含 owner 字段", "owner" not in keys)
            check(f"{resp.request.path} 响应不含任何 64 位十六进制串",
                  not any(isinstance(v, str) and len(v) == 64
                          and all(c in "0123456789abcdef" for c in v)
                          for v in _walk_values(resp.get_json())))

        # oid 稳定且不写日志
        oid1 = _owner_of(a)
        oid2 = _owner_of(a)
        check("同一会话的标识稳定", oid1 == oid2 and len(oid1) == 64)
        check("两个会话的标识不同", _owner_of(a) != _owner_of(b))

        # 注意：正常的请求路径**不写日志**，因此直接对普通请求做捕获很可能是 0 条。
        # 如果不加下面这段，`oid not in messages` 就成了空断言——
        # 它之所以成立，只是因为压根没有日志，而不是因为标识被正确排除。
        # 因此改用一条**确实会写日志**的路径（未捕获异常经 errors.py 记录），
        # 用同一个捕获器确认它真能收到日志，再断言标识不在其中。
        # 这同时也覆盖了此前缺失的 500 兜底路径。
        probe = new_client()
        captured = _capture_logs(lambda: probe.get("/api/_log_probe"))
        check("日志捕获机制有效：未捕获异常确实产生了日志记录",
              any("未捕获异常" in r.getMessage() for r in captured),
              f"捕获 {len(captured)} 条")
        check("未捕获异常不会把会话标识写进日志",
              not any(oid1 in r.getMessage() for r in captured))

        # 500 兜底：响应体不得泄露任何内部细节（此前只有人工验证，未纳入自动测试）
        r = probe.get("/api/_log_probe")
        check("未捕获异常返回 500 且为 JSON", r.status_code == 500 and r.is_json,
              f"HTTP {r.status_code}")
        body_text = r.get_data(as_text=True)
        check("500 响应为中文文案",
              "服务器内部错误" in (r.get_json() or {}).get("error", ""))
        check("500 响应不含 traceback", "Traceback" not in body_text)
        check("500 响应不含异常原文", "日志探针" not in body_text)
        check("500 响应不含文件路径或模块名",
              ".py" not in body_text and "RuntimeError" not in body_text)


def _walk_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_values(v)
    else:
        yield obj


def _owner_of(client) -> str:
    """从会话 Cookie 中取出 owner（仅测试使用）。"""
    from web.session import OWNER_KEY
    with client.session_transaction() as sess:
        return sess[OWNER_KEY]


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _capture_logs(fn):
    handler = _Capture()
    targets = [logging.getLogger(), logging.getLogger("cardiolens")]
    for t in targets:
        t.addHandler(handler)
    try:
        fn()
    finally:
        for t in targets:
            t.removeHandler(handler)
    return handler.records


# ================================================================ 9 负向校验
NEGATIVE_CASES = [
    ("记录号不存在", {"record_id": "999"}),
    ("缺少 record_id", {"start_sec": 0}),
    ("缺省 record_id 为空串", {"record_id": ""}),
    ("时长为负数", {"record_id": "100", "duration_sec": -5}),
    ("时长过短（<3s）", {"record_id": "100", "duration_sec": 1}),
    ("时长超上限（>30s）", {"record_id": "100", "duration_sec": 60}),
    ("起始时间为负", {"record_id": "100", "start_sec": -5}),
    ("起始时间非数字", {"record_id": "100", "start_sec": "abc"}),
    ("时长非数字", {"record_id": "100", "duration_sec": "abc"}),
    ("标题过长", {"record_id": "100", "duration_sec": 10, "save": True,
                  "title": "长" * 200}),
    ("起始时间非有限值", {"record_id": "100", "start_sec": float("nan")}),
    ("预览的记录号不存在", {"__preview__": True, "record_id": "999"}),
]

# 注意：inference._resolve_window 对「起始时间超出记录末尾」的处理是
# **向左回退对齐**而不是报错（见 src/inference.py 的 _resolve_window）。
# 这是有意为之：用户在滑块上拖到接近末尾时，不该因为差几个采样点就报错。
# 因此它不是负向用例，而由 test_window_alignment 正向验证。
#
# 另一个分支「时长 > 记录总长」在接口层不可达：时长上限 30 秒，
# 而数据集里最短的记录也有约 30 分钟。

RAW_NEGATIVE_CASES = [
    ("时长为 NaN", b'{"record_id":"100","duration_sec":NaN}'),
    ("时长为 +Infinity", b'{"record_id":"100","duration_sec":Infinity}'),
    ("时长为 -Infinity", b'{"record_id":"100","duration_sec":-Infinity}'),
    ("起始为 NaN", b'{"record_id":"100","start_sec":NaN}'),
    ("起始为 +Infinity", b'{"record_id":"100","start_sec":Infinity}'),
]


def test_negative_validation() -> None:
    print("\n[9] 输入校验（负向分支）")
    client = new_client()
    with no_rate_limit():
        for name, payload in NEGATIVE_CASES:
            if payload.pop("__preview__", False):
                r = client.get("/api/preview?record_id=999&start=0&duration=10")
            else:
                r = post_json(client, "/api/analyze", payload)
            ok = r.status_code == 400
            body = r.get_json() or {}
            check(f"拒绝：{name}", ok and body.get("ok") is False,
                  f"HTTP {r.status_code} {body.get('error', '')}")

        for name, raw in RAW_NEGATIVE_CASES:
            r = client.post("/api/analyze", data=raw, content_type="application/json")
            check(f"拒绝：{name}", r.status_code == 400, f"HTTP {r.status_code}")

        r = client.post("/api/analyze", data="不是 JSON", content_type="application/json")
        check("拒绝：非法 JSON", r.status_code == 400, f"HTTP {r.status_code}")

        r = post_json(client, "/api/analyze", [1, 2, 3])
        check("拒绝：JSON 数组而不是对象", r.status_code == 400, f"HTTP {r.status_code}")

        r = post_json(client, "/api/analyze", {"record_id": "100", "title": 123,
                                               "duration_sec": 10, "save": True})
        check("拒绝：标题不是字符串", r.status_code == 400, f"HTTP {r.status_code}")


# ================================================================ 9b 窗口对齐
def test_window_alignment() -> None:
    """起始时间超出记录末尾时向左回退对齐，而不是报错。

    这是引擎的有意设计（src/inference.py 的 _resolve_window）：用户在滑块上
    拖到接近末尾时，不该因为超出几个采样点就被拒绝。但它带来一个前端约束——
    响应的 start_sec 可能与你请求的不同，界面必须回显**响应值**，
    否则波形标题与十字线读数会整体偏移。这里把这条契约固定下来。
    """
    print("\n[9b] 窗口越界时的回退对齐")
    client = new_client()
    with no_rate_limit():
        r = post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": 99999, "duration_sec": 10,
        })
    check("起始时间远超记录末尾时不是报错，而是回退对齐",
          r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.get_json()
        check("响应里的 start_sec 已被回退到合法位置",
              data["start_sec"] < 99999, f"实际 {data['start_sec']}")
        check("回退后窗口落在记录范围内且有搏动",
              data["summary"]["n_beats"] > 0)
        check("响应回显的 start_sec 与信号长度自洽",
              data["n_samples"] == round(data["duration_sec"] * data["fs"]),
              f"n_samples={data['n_samples']}")


# ================================================================ 10 HTTP 语义
def test_http_semantics() -> None:
    print("\n[10] HTTP 语义")
    client = new_client()

    r = client.get("/api/does-not-exist")
    check("未知接口返回 404", r.status_code == 404)
    check("未知接口返回 JSON 而非 HTML", r.is_json, r.content_type)

    r = client.get("/api/analyze")
    check("接口方法用错返回 405（而不是被 SPA 壳吞成 404）",
          r.status_code == 405, f"实际 {r.status_code}")
    check("405 返回 JSON", r.is_json)

    for path in ("/", "/analyze", "/history", "/history/12", "/about"):
        r = client.get(path)
        check(f"{path} 返回 SPA 壳", r.status_code == 200
              and "text/html" in r.content_type)
    r = client.get("/analyze")
    html = r.get_data(as_text=True)
    check("壳内含 importmap", "importmap" in html)
    check("壳内内联了首屏数据", "window.__BOOT__" in html)

    # 内联 JSON 必须是合法可解析的（写坏了会让整个前端白屏）
    import re
    m = re.search(r"window\.__BOOT__ = (.*?);\n", html, re.S)
    check("能定位到内联的首屏数据", m is not None)
    if m:
        try:
            payload = json.loads(m.group(1))
            check("内联数据是合法 JSON 且含就绪标记", payload.get("ok") is True)
        except json.JSONDecodeError as exc:
            check("内联数据是合法 JSON", False, str(exc))

    # 内联转义：数据里若出现 </script> 会提前闭合脚本标签，必须转义掉
    from web.views.pages import _json_for_inline
    danger = {"x": "</script><script>alert(1)</script>", "y": "<!--", "z": "a&b"}
    escaped = _json_for_inline(danger)
    check("内联 JSON 转义了尖括号，无法提前闭合脚本标签",
          "</script" not in escaped and "<" not in escaped)
    check("转义后仍是合法 JSON 且内容无损", json.loads(escaped) == danger)

    r = client.get("/no-such-page")
    check("未知页面返回 SPA 壳但状态码为 404", r.status_code == 404
          and b"__BOOT__" in r.data)

    r = client.get("/static/missing-file.js")
    check("缺失的静态资源返回空 404（不塞 HTML）",
          r.status_code == 404 and not r.data)


# ================================================================ 11 请求体
def test_body_limits() -> None:
    print("\n[11] 请求体上限与类型")
    client = new_client()

    big = {"record_id": "100", "duration_sec": 10, "title": "x" * (70 * 1024)}
    r = post_json(client, "/api/analyze", big)
    check("超过 64 KB 的请求体被拒绝", r.status_code == 413, f"实际 {r.status_code}")
    check("413 返回 JSON 且文案为中文",
          r.is_json and "请求体过大" in (r.get_json() or {}).get("error", ""))

    r = post_json(client, "/api/history/clear", {})
    check("正常大小的请求体可通过", r.status_code == 200, f"实际 {r.status_code}")


# ================================================================ 12 限流
def test_rate_limit() -> None:
    print("\n[12] 限流")
    guard.reset_rate_limits()
    client = new_client()
    limit = app.config["RATE_LIMITS"]["analyze"][0]

    codes = []
    for _ in range(limit + 1):
        codes.append(post_json(client, "/api/analyze", {
            "record_id": RECORD, "start_sec": START_SEC,
            "duration_sec": DURATION_SEC, "with_cam": False,
        }).status_code)

    check(f"前 {limit} 次分析请求通过", all(c == 200 for c in codes[:limit]), str(codes))
    check("超限后返回 429", codes[-1] == 429, str(codes))

    r = post_json(client, "/api/analyze", {"record_id": RECORD, "duration_sec": 10})
    check("429 文案为中文", "频繁" in (r.get_json() or {}).get("error", ""))
    guard.reset_rate_limits()


# ================================================================ 13 并发槽位
def test_concurrency_gate() -> None:
    print("\n[13] 并发槽位")
    slots = guard._slots()
    size = app.config["MAX_CONCURRENT_ANALYSES"]
    saved_timeout = app.config["ANALYSIS_SLOT_TIMEOUT"]
    app.config["ANALYSIS_SLOT_TIMEOUT"] = 0.3      # 缩短等待，避免自检卡 8 秒

    acquired = 0
    try:
        for _ in range(size):
            if slots.acquire(blocking=False):
                acquired += 1
        r = new_client().get(f"/api/preview?record_id={RECORD}&start=0&duration=10")
        check("槽位占满时返回 503", r.status_code == 503, f"实际 {r.status_code}")
        check("503 文案友好且不含堆栈",
              "Traceback" not in r.get_data(as_text=True)
              and "请稍后重试" in (r.get_json() or {}).get("error", ""))
    finally:
        for _ in range(acquired):
            slots.release()
        app.config["ANALYSIS_SLOT_TIMEOUT"] = saved_timeout

    r = new_client().get(f"/api/preview?record_id={RECORD}&start=0&duration=10")
    check("槽位释放后恢复可用", r.status_code == 200, f"实际 {r.status_code}")


# ================================================================ 14 media 白名单
def test_media_whitelist() -> None:
    print("\n[14] /media 白名单")
    client = new_client()
    for name in ("confusion_matrix.png", "training_curve.png"):
        r = client.get(f"/media/{name}")
        check(f"{name} 可访问", r.status_code == 200, f"HTTP {r.status_code}")
    for name in ("ecg_cnn.pt", "_train.log", "train_run4.log",
                 "archive/ecg_cnn_run2.pt", "../README.md", "%2e%2e/README.md"):
        r = client.get(f"/media/{name}")
        check(f"{name} 被拒绝（防止权重/训练日志外泄）", r.status_code == 404,
              f"HTTP {r.status_code}")


# ================================================================ 15 静态审计
def test_static_audit() -> None:
    """静态审计。

    注意这类检查的**边界**：它证明的是"源码里没有出现这些模式"，
    是源代码层面的证据，不等于对运行时行为的绝对保证
    （依赖库内部的网络调用、动态导入等都不在扫描范围内）。
    结论表述时必须保持这一限定。
    """
    print("\n[15] 静态审计")
    py_files = list((ROOT / "web").rglob("*.py"))
    py_text = "\n".join(p.read_text(encoding="utf-8") for p in py_files)
    check("后端不含 PySide6/Qt 引用", "PySide6" not in py_text and "QtWidgets" not in py_text,
          f"扫描 {len(py_files)} 个文件")

    # 服务运行路径是否引入了对外 HTTP 客户端。
    # 用 AST 解析而不是字符串匹配：字符串匹配会被注释与文档字符串误伤，
    # 也可能漏掉 `import urllib.request` 这类写法。
    import ast
    offline_ok = True
    offenders: list[str] = []
    targets = list((ROOT / "web").rglob("*.py")) + [ROOT / "wsgi.py"]
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m.split(".")[0] in ("requests", "httpx", "aiohttp", "urllib",
                                       "http", "socket", "ftplib", "smtplib"):
                    offline_ok = False
                    offenders.append(f"{path.name}: {m}")
    check("服务运行路径（web/ 与 wsgi.py）未引入任何对外 HTTP/套接字客户端",
          offline_ok, "、".join(offenders) if offenders else
          f"AST 扫描 {len(targets)} 个文件，均未 import requests/urllib/http.client 等")

    # 后端工具脚本（prepare_data 需要下载数据集）不在服务运行路径内，
    # 这里单独确认它们没有被 web/ 引用
    check("离线工具（src/prepare_data.py 等）未被服务运行路径 import",
          "prepare_data" not in py_text and "import train" not in py_text
          and "from src.train" not in py_text)

    js_files = list((ROOT / "web" / "static" / "js").rglob("*.js"))
    js_text = "\n".join(p.read_text(encoding="utf-8") for p in js_files)
    check("前端不使用 v-html（CSP 放宽了 unsafe-eval，注入链必须堵死）",
          "v-html" not in js_text)
    check("前端不用 innerHTML 拼接服务端内容", "innerHTML" not in js_text,
          f"扫描 {len(js_files)} 个文件")

    vendor = list((ROOT / "web" / "static" / "vendor").glob("*.js"))
    check("前端依赖已本地分发（不走 CDN）", len(vendor) >= 2,
          "、".join(p.name for p in vendor))
    check("没有引用任何外部 CDN",
          "cdn.jsdelivr" not in js_text and "unpkg.com" not in js_text
          and "cdnjs" not in js_text)
    # 精确检查 <script src> 与 <link href>：只认真正会发起网络请求的属性值，
    # 不扫整个 HTML（favicon 里内联的 SVG 命名空间是 http://www.w3.org/2000/svg，
    # 那是 XML 命名空间而非网络地址，粗暴匹配会误报）。
    import re as _re
    html = (ROOT / "web/templates/index.html").read_text(encoding="utf-8")
    refs = _re.findall(r'<(?:script|link)\b[^>]*?\b(?:src|href)\s*=\s*"([^"]+)"', html)
    external = [r for r in refs if r.startswith(("http://", "https://", "//"))]
    check("页面模板的脚本/样式引用均为站内相对路径（无外部 CDN）",
          not external, f"外部引用：{external}" if external
          else f"检查 {len(refs)} 处引用：{'、'.join(refs)}")


# ================================================================ 16 文案
def test_user_facing_copy() -> None:
    print("\n[16] 用户可见文案")
    client = new_client()
    boot = client.get("/api/bootstrap").get_json()
    check("接口返回项目原文免责声明", boot["disclaimer"] == C.DISCLAIMER)

    html = client.get("/").get_data(as_text=True)
    assets = html + "\n" + "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "web" / "static" / "js").rglob("*.js"))

    for term in ("CardioLens.exe", "%LOCALAPPDATA%", "双击运行", "PyInstaller", "QThread"):
        check(f"文案不含桌面版遗留表述：{term}", term not in assets)

    errs = []
    with no_rate_limit():
        for payload in ({"record_id": "999"}, {"record_id": "100", "duration_sec": 1}):
            errs.append(post_json(client, "/api/analyze", payload).get_json()["error"])
    check("错误文案为中文且不含堆栈",
          all("Traceback" not in e and any("一" <= ch <= "鿿" for ch in e)
              for e in errs), str(errs))

    # 免责声明必须在首页、结果区、关于页都出现
    check("首页展示免责声明", "课程作业演示" in html or boot["disclaimer"][:8] in html)
    about = client.get("/about").get_data(as_text=True)
    check("关于页随壳返回", about.count("__BOOT__") == 1)


# ================================================================ 17 迁移回归
OLD_SCHEMA = """
CREATE TABLE analyses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT    NOT NULL,
    record_id      TEXT    NOT NULL,
    start_sec      REAL    NOT NULL,
    duration_sec   REAL    NOT NULL,
    n_beats        INTEGER NOT NULL,
    abnormal_count INTEGER NOT NULL,
    abnormal_ratio REAL    NOT NULL,
    risk_code      TEXT    NOT NULL,
    risk_label     TEXT    NOT NULL,
    agreement      REAL    NOT NULL,
    mean_conf      REAL    NOT NULL,
    counts_json    TEXT    NOT NULL,
    payload_json   TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
"""


def test_migration_regression() -> None:
    """迁移逻辑只在真实服务器的老库上跑一次。

    不在离线测试里显式构造一份旧 schema，这条路径就永远不会被执行，
    出问题必然是上线那一刻。
    """
    print("\n[17] 旧库迁移回归")
    old_dir = TMP / "oldstore"
    old_dir.mkdir(parents=True, exist_ok=True)
    old_db = old_dir / "app.db"

    conn = sqlite3.connect(old_db)
    conn.executescript(OLD_SCHEMA)
    for i in range(3):
        conn.execute(
            """INSERT INTO analyses
               (title, record_id, start_sec, duration_sec, n_beats, abnormal_count,
                abnormal_ratio, risk_code, risk_label, agreement, mean_conf,
                counts_json, payload_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"老记录 {i}", "100", 0.0, 10.0, 11, 2, 0.18, "medium", "存在少量异常搏动",
             0.9, 0.85, '{"N":9,"S":1,"V":1,"F":0,"Q":0}',
             '{"beats":[]}', "2026-01-01 10:00:00"),
        )
    conn.commit()
    conn.close()

    saved_db, saved_store = C.DB_PATH, C.STORE_DIR
    C.STORE_DIR = old_dir
    C.DB_PATH = old_db
    try:
        db.init_db()

        conn = sqlite3.connect(old_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(analyses)")]
        check("迁移后列序与新建库一致（owner 在第 2 位）",
              cols[:3] == ["id", "owner", "title"], f"实际 {cols[:3]}")
        n = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        check("原有 3 行一条不少", n == 3, f"实际 {n}")
        owners = {r[0] for r in conn.execute("SELECT DISTINCT owner FROM analyses")}
        check("迁移行全部落到 LEGACY_OWNER", owners == {db.LEGACY_OWNER}, str(owners))
        idx = {r[1] for r in conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='analyses'")}
        check("迁移后重建了两个索引",
              {"idx_analyses_created", "idx_analyses_owner"} <= idx, str(sorted(idx)))
        conn.close()

        check("任何真实会话都查不到迁移前的记录",
              len(db.list_analyses(owner="someone")) == 0)
        check("孤儿计数正确", db.count_orphans() == 3, str(db.count_orphans()))

        moved = db.adopt_orphans("someone")
        check("认领后归属正确", moved == 3 and len(db.list_analyses(owner="someone")) == 3)
        check("认领后不再有孤儿", db.count_orphans() == 0)

        db.init_db()
        check("重复执行 init_db 是幂等的（再迁移一次不报错）",
              db.count_orphans() == 0 and len(db.list_analyses(owner="someone")) == 3)
    finally:
        C.DB_PATH, C.STORE_DIR = saved_db, saved_store


# ================================================================ 主流程
def main() -> int:
    print("=" * 70)
    print("  CardioLens Web 版自检")
    print(f"  临时数据目录：{TMP}")
    print("=" * 70)

    for fn in (
        test_readiness, test_hashes, test_inference_consistency, test_gradcam,
        test_summary, test_schema, test_history_crud, test_session_isolation,
        test_negative_validation, test_window_alignment, test_http_semantics,
        test_body_limits, test_rate_limit, test_concurrency_gate,
        test_media_whitelist, test_static_audit, test_user_facing_copy,
        test_migration_regression,
    ):
        try:
            fn()
        except Exception as exc:                        # noqa: BLE001 - 自检脚本
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 执行未抛异常", False, f"{type(exc).__name__}: {exc}")

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
    C.force_utf8_stdout()
    sys.exit(main())
