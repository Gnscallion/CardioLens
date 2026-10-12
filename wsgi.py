"""WSGI 入口。

用法：

    # 本地 / 单机
    python wsgi.py

    # 生产（由 systemd 或进程管理器拉起）
    waitress-serve --host=127.0.0.1 --port=8001 --threads=4 wsgi:app

**为什么用 waitress 而不是 gunicorn -w N**

本应用的限流计数器和并发信号量都是**进程内**状态。开多个 worker 会让
限额按 worker 数放大，信号量也各算各的，等于把保护措施架空；同时每个
worker 都会独立加载一份 PyTorch 与模型，内存成倍上涨。而单次分析实测只有
0.3 秒量级，单进程多线程的吞吐（约 3 次/秒）对课程演示场景绰绰有余。

因此：**必须单进程多线程运行**。waitress 纯 Python、跨平台（Windows 上
gunicorn 根本跑不起来，它依赖 fork），是这个约束下最省心的选择。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web import create_app          # noqa: E402

app = create_app()


def main() -> int:
    host = os.environ.get("CARDIOLENS_HOST", "127.0.0.1")
    port = int(os.environ.get("CARDIOLENS_PORT", "5000"))
    threads = int(os.environ.get("CARDIOLENS_THREADS", "4"))

    try:
        from waitress import serve
    except ImportError:
        print("缺少 waitress。请先安装依赖：pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    serve(app, host=host, port=port, threads=threads, ident="CardioLens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
