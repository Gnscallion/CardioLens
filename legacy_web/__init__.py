"""旧版 Web 实现（已退役，仅作留存与对照）。

CardioLens 已从 Flask + HTML/CSS/JavaScript 的 Web 应用迁移为纯 PySide6
原生桌面软件。原项目根目录下的 app.py、templates/、static/ 原封不动地
移动到这里，**不参与桌面软件的任何运行路径**：

    * desktop/ 下的桌面程序不导入本包的任何模块；
    * 打包 dist/CardioLens.exe 时明确排除 legacy_web/；
    * 本包只是把 Web 版代码留档，方便对照迁移前后的实现差异。

如需在开发机上跑起旧版（仅用于对照，不是交付入口）：

    python -m legacy_web.app

注意：这样启动会占用本机 5000 端口并监听 0.0.0.0，属于旧版行为，
与桌面版无关；桌面版不监听任何端口。
"""
