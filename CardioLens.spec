# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：CardioLens 桌面版。

刻意不使用 --collect-all：那会把 torch / PySide6 的全部子模块与测试数据
一股脑塞进包里，体积翻几倍且容易带入无用依赖。这里改为显式列出
"只读资源" 与 "明确排除" 两侧清单，让包内容一目了然。

打包：
    pyinstaller CardioLens.spec --noconfirm

产物：
    dist/CardioLens.exe   —— 单文件、无控制台，可单独拷走到任意目录运行
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()

# ---------------------------------------------------------------- 只读资源
# 注意：data/processed/beats.npz（91 MB）是训练用的心搏样本集，
# 桌面端推理只读 signals/ 与 annots/，因此**不打包**该文件。
DATAS = [
    (str(ROOT / "models" / "ecg_cnn.pt"), "models"),
    (str(ROOT / "models" / "metrics.json"), "models"),
    (str(ROOT / "models" / "confusion_matrix.png"), "models"),
    (str(ROOT / "models" / "training_curve.png"), "models"),
    (str(ROOT / "data" / "processed" / "record_meta.json"), "data/processed"),
    (str(ROOT / "data" / "processed" / "signals"), "data/processed/signals"),
    (str(ROOT / "data" / "processed" / "annots"), "data/processed/annots"),
]

# ---------------------------------------------------------------- 明确排除
# 桌面版运行路径只用到 torch / numpy / PySide6 / sqlite3；
# 下面这些要么是旧 Web 版遗留，要么只在训练与开发时才用得到。
EXCLUDES = [
    "legacy_web",          # 旧 Web 实现，绝不能参与桌面版运行
    "flask",               # 旧 Web 版的服务端框架
    "werkzeug",
    "jinja2",
    "matplotlib",          # About 页直接显示已生成的 PNG，不需要绘图库
    "pandas",
    "pyarrow",
    "sklearn",
    "playwright",
    "tkinter",
    "PIL",
    "IPython",
    "pytest",
    "notebook",
    "torchvision",
    "torchaudio",
    # 本机同时装了 TensorFlow 全家桶。PyInstaller 的 torch 钩子会去探测
    # tensorflow 是否存在并可能把它带进依赖图，而桌面版只用 PyTorch。
    # 不排除掉的话包体积会从几百 MB 涨到 1 GB 以上。
    "tensorflow",
    "tensorboard",
    "keras",
    "tensorflow_io",
    "tf_keras",
    "h5py",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtBluetooth",
]

HIDDEN = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

a = Analysis(
    [str(ROOT / "desktop" / "main.py")],
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
    name="CardioLens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX 压缩会拖慢启动且可能触发杀软误报
    runtime_tmpdir=None,
    console=False,             # 窗口程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
