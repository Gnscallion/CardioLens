# -*- mode: python ; coding: utf-8 -*-
"""【仅用于验收自检】打包一个带控制台的冻结自检程序。

这个 spec **不是产品的一部分**，产物 CardioLensSelfTest.exe 也不随软件交付。
它存在的唯一理由：证明 CardioLens.exe 在冻结运行时里不仅能显示「系统就绪」，
而且真的能读包内 .npy、跑完 torch 前向、算出 Grad-CAM、把报告写进用户目录库。

为了不给"自检和产品打包不一致"留下空间，这里不重抄资源/排除清单，而是
用桩对象执行 CardioLens.spec，把它里面的 DATAS / EXCLUDES / HIDDEN 原样
取出来复用——两边的包内容因此在结构上必然一致。

打包：
    pyinstaller CardioLensSelfTest.spec --noconfirm \
        --distpath dist_selftest --workpath build_selftest
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()


class _Stub:
    """吞掉 spec 里的 Analysis/PYZ/EXE 调用，只把参数留下来。"""

    def __init__(self, *a, **kw):
        self.args = a
        self.kwargs = kw
        self.scripts = a[1] if len(a) > 1 else []
        self.binaries = a[2] if len(a) > 2 else []
        self.datas = a[3] if len(a) > 3 else []
        self.pure = a[0] if a else None


def _load_product_lists():
    """执行产品 spec，取出其中的资源与排除清单。"""
    src = (ROOT / "CardioLens.spec").read_text(encoding="utf-8")
    ns = {
        "__name__": "cardiolens_product_spec",
        "__builtins__": __builtins__,
        "SPECPATH": str(ROOT),
        "Analysis": _Stub,
        "PYZ": _Stub,
        "EXE": _Stub,
        "COLLECT": _Stub,
        "BUNDLE": _Stub,
        "Tree": _Stub,
    }
    exec(compile(src, "CardioLens.spec", "exec"), ns)
    return ns["DATAS"], ns["EXCLUDES"], ns["HIDDEN"]


DATAS, EXCLUDES, HIDDEN = _load_product_lists()

# 自检程序比产品多用到 argparse/json/hashlib，都是标准库，无需 hiddenimports。
a = Analysis(
    [str(ROOT / "scripts" / "frozen_selftest.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CardioLensSelfTest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,              # 自检需要看到输出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
