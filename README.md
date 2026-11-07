# CardioLens · 心电节律智能分析平台

> **ECG Rhythm Intelligent Analysis Platform**
>
> 基于深度学习与可解释 AI 的 **Web 应用** —— 一维卷积神经网络（1D-CNN）心电搏动自动分类与 Grad-CAM 可解释性分析
>
> 前端：**Vue 3 + 原生 Canvas 2D** · 后端：**Flask + Waitress** · 数据集：MIT-BIH Arrhythmia Database（PhysioNet mitdb） · 分类标准：AAMI EC57 五分类
>
> ![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab)
> ![PyTorch](https://img.shields.io/badge/PyTorch-2.x%20CPU-ee4c2c)
> ![Flask](https://img.shields.io/badge/Flask-3.x-000000)
> ![Vue](https://img.shields.io/badge/Vue-3.x%20(%E6%97%A0%E6%9E%84%E5%BB%BA)-42b883)
> ![License](https://img.shields.io/badge/%E7%94%A8%E9%80%94-%E8%AF%BE%E7%A8%8B%E4%BD%9C%E4%B8%9A%E6%BC%94%E7%A4%BA-important)

---

## ⚠️ 重要声明

**本系统为软件工程课程作业演示项目，不是医疗器械，也不是临床诊断工具。**

> 以上结果由机器学习模型自动生成，仅用于课程项目演示与辅助分析，不构成医疗诊断依据，不能用于任何临床决策。如有健康问题请及时就医。

该声明在**首页、分析结果页与关于页**均显著展示，并在页脚常驻，不可关闭、不可隐藏。

---

## 一、项目简介

心电信号（ECG）是临床上最基础、最普及的心脏检查手段之一。一次 24 小时动态心电监测会产生约 **10 万次心搏**，
而专业医师人工判读耗时且存在主观差异。本项目实现了一套**可在普通笔记本（纯 CPU）上完整运行**的心电搏动自动分析服务：

- 读取 MIT-BIH 心律失常数据库的真实心电记录
- 对信号做带通滤波与逐搏切分，按 **AAMI EC57 标准**归类为 5 类心搏
- 用 **1D-CNN** 逐搏分类，输出每一搏的类别与置信度
- 用 **Grad-CAM** 给出模型关注的时间片段，回答"模型凭什么这么判断"
- 在**浏览器**中完成"选记录 → 看波形 → 跑分析 → 读结果 → 存历史"的完整操作闭环

### 分类目标（AAMI EC57 五分类）

| 类别 | 中文名称 | 说明 | 演示风险等级 |
|:---:|---|---|:---:|
| **N** | 正常搏动 | 窦性心律来源的正常心搏，含束支传导阻滞搏动 | 正常 |
| **S** | 室上性早搏 | 起源位于心室以上的异位搏动（房早、交界性早搏） | 关注 |
| **V** | 室性早搏 | 起源于心室的异位搏动，临床关注度最高 | 警示 |
| **F** | 融合搏动 | 正常搏动与室性搏动融合形成 | 警示 |
| **Q** | 未分类/起搏搏动 | 无法归入上述类别的搏动，含起搏器搏动 | 关注 |

---

## 二、功能特性

顶栏提供五项主要入口：**首页 / ECG 分析 / 分析历史 / 关于 / 科研实验**，并提供账号、科研实验和系统通知等
快捷操作。单页应用，视图间无刷新切换。

| 视图 | 功能 |
|---|---|
| 🏠 首页 | 项目介绍、模型关键指标、数据集概览、系统就绪状态、医学免责声明 |
| 📊 ECG 分析 | 记录选择（标注推荐记录）、时间窗与时长调节、波形预览、一键分析；分析期间显示不确定进度条，页面全程可滚动可切换 |
| 🫀 波形可视化 | Canvas 自绘心电条带：心电网格与坐标轴刻度、R 峰标注、异常搏动高亮、**滚轮缩放、拖拽平移、双击复位、悬停十字线读数**；Grad-CAM 热力图叠加 |
| 🔍 逐搏分析 | 逐搏结果表（序号 / 位置 / 预测类别 / 置信度 / 专家标注 / 是否一致），点击任意一搏联动查看单搏波形、五类概率与 RR 节律特征 |
| 🔥 可解释性 | Grad-CAM 热力图（252 点，与心搏采样点严格对齐），以填充面积图呈现模型关注的时间片段 |
| 💾 结果保存 | 一键保存报告到服务端 SQLite；历史页支持列表、详情回看、单条删除与清空（均带确认） |
| 🏷️ 划分提示 | 自动标注该记录属于训练集还是测试集；训练集记录会明确警告"一致率偏高、不能当作泛化能力" |
| 📁 ECG 文件上传 | 支持 CSV/TXT 数值序列上传，先做信号质量检查，也可直接进入上传数据分析；单文件不超过 5 MB |
| 👤 账号体系 | 支持注册、登录、修改密码、密码找回与邮箱验证；登录后历史记录按账号保存，可跨浏览器访问 |
| 🔒 数据隔离 | 已登录用户按账号隔离；未登录用户按浏览器隔离，看不到别人的记录 |
| 🔔 系统通知 | 注册、密码修改等安全事件生成通知，支持未读数量、单条已读和全部已读 |
| 🧪 科研实验 | 支持异步实验任务、进度查询、ECE/Brier Score 校准指标与实验结果保存 |
| 📤 结果导出 | 分析结果支持 TXT、JSON 和逐搏 CSV 导出 |
| 🛡️ 生产安全 | 支持生产密钥、HTTPS 安全响应头、Secure Cookie 与 CSRF 校验 |
| 📱 响应式 | 桌面与移动端视口均可正常使用 |
| 🛡️ 异常兜底 | 任何异常都以友好中文提示呈现，详细堆栈只写服务端日志，**使用者永远看不到 traceback** |

### 当前运行界面

以下截图由当前版本本地服务实际生成，覆盖首页、分析、波形交互、历史记录、科研页面和移动端布局：

<p><strong>首页</strong></p>
<img src="https://i.postimg.cc/yxj2M037/01-shou-ye.png" alt="首页">

<p><strong>分析工作台（参数与预览）</strong></p>
<img src="https://i.postimg.cc/5ygDh8QL/02-fen-xi-gong-zuo-tai-can-shu-yu-yu-lan.png" alt="分析工作台（参数与预览）">

<p><strong>波形预览</strong></p>
<img src="https://i.postimg.cc/4yPjDpHz/03-bo-xing-yu-lan.png" alt="波形预览">

<p><strong>分析过程</strong></p>
<img src="https://i.postimg.cc/rsj7B5R1/04-fen-xi-guo-cheng.png" alt="分析过程">

<p><strong>分析结果（整体）</strong></p>
<img src="https://i.postimg.cc/MZYkfJPh/05-fen-xi-jie-guo-zheng-ti.png" alt="分析结果（整体）">

<p><strong>逐搏明细</strong></p>
<img src="https://i.postimg.cc/v8vRxw2F/06-zhu-bo-ming-xi.png" alt="逐搏明细">

<p><strong>单搏详情与 Grad-CAM</strong></p>
<img src="https://i.postimg.cc/jqhVnY3Y/07-dan-bo-xiang-qing-yu-Grad-CAM.png" alt="单搏详情与 Grad-CAM">

<p><strong>波形缩放</strong></p>
<img src="https://i.postimg.cc/nV189fSn/08-bo-xing-suo-fang.png" alt="波形缩放">

<p><strong>波形平移</strong></p>
<img src="https://i.postimg.cc/dQ9MZcNs/09-bo-xing-ping-yi.png" alt="波形平移">

<p><strong>悬停十字线读数</strong></p>
<img src="https://i.postimg.cc/ZYLkvzsR/10-xuan-ting-shi-zi-xian-du-shu.png" alt="悬停十字线读数">

<p><strong>数据划分提示：训练集记录</strong></p>
<img src="https://i.postimg.cc/fTWGxq1T/11-shu-ju-hua-fen-ti-shi-xun-lian-ji-ji-lu.png" alt="数据划分提示：训练集记录">

<p><strong>保存报告</strong></p>
<img src="https://i.postimg.cc/025TpXhy/12-bao-cun-bao-gao.png" alt="保存报告">

<p><strong>数据划分提示：测试集记录</strong></p>
<img src="https://i.postimg.cc/qMBP8DWg/13-shu-ju-hua-fen-ti-shi-ce-shi-ji-ji-lu.png" alt="数据划分提示：测试集记录">

<p><strong>历史记录</strong></p>
<img src="https://i.postimg.cc/gkcCvt1x/14-li-shi-ji-lu.png" alt="历史记录">

<p><strong>历史详情</strong></p>
<img src="https://i.postimg.cc/656kdbFL/15-li-shi-xiang-qing.png" alt="历史详情">

<p><strong>关于：项目与技术原理</strong></p>
<img src="https://i.postimg.cc/15Rkp7bv/16-guan-yu-xiang-mu-yu-ji-shu-yuan-li.png" alt="关于：项目与技术原理">

<p><strong>关于：评估结果与混淆矩阵</strong></p>
<img src="https://i.postimg.cc/sDfkpHbJ/17-guan-yu-ping-gu-jie-guo-yu-hun-xiao-ju-zhen.png" alt="关于：评估结果与混淆矩阵">

<p><strong>关于：已知局限</strong></p>
<img src="https://i.postimg.cc/hPCHMbq8/18-guan-yu-yi-zhi-ju-xian.png" alt="关于：已知局限">

<p><strong>会话隔离提示</strong></p>
<img src="https://i.postimg.cc/Pr6BKzkK/19-hui-hua-ge-li-ti-shi.png" alt="会话隔离提示">

<p><strong>新会话空历史</strong></p>
<img src="https://i.postimg.cc/X72Txc0Q/20-xin-hui-hua-kong-li-shi.png" alt="新会话空历史">

<p><strong>移动端首页</strong></p>
<img src="https://i.postimg.cc/fTH65jhP/21-yi-dong-duan-shou-ye.png" alt="移动端首页">

<p><strong>移动端分析页</strong></p>
<img src="https://i.postimg.cc/bN6KLHj7/22-yi-dong-duan-fen-xi-ye.png" alt="移动端分析页">

<p><strong>科研实验</strong></p>
<img src="https://i.postimg.cc/J4T9KcLw/23-ke-yan-shi-yan.png" alt="科研实验">

---

## 三、快速开始

### 3.1 访问已部署的服务（使用者）

打开浏览器访问部署地址即可。**客户端不需要安装任何东西**，也不需要联网加载第三方 CDN
（前端依赖随服务端分发）。

| 项目 | 要求 |
|---|---|
| 浏览器 | 任意现代浏览器（Chrome / Edge / Firefox / Safari 近两年的版本） |
| 客户端依赖 | 无 |
| 本地数据 | 无。分析历史保存在服务端 |

> **关于分析历史**：登录后，历史记录与账号绑定，可以在其他浏览器或设备登录同一账号后继续访问。
> 未登录时，历史记录仅与当前浏览器绑定；换浏览器、换设备或清除浏览器数据后，
> 未登录记录将无法在此浏览器中访问（数据仍在服务端，只是没有账号入口）。

### 3.2 本地运行

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python wsgi.py
```

打开 `http://127.0.0.1:5000`。

首次启动会自动建库并把模型加载进内存（约 3 秒），日志中会打印监听地址与数据目录。

### 3.3 重新训练模型 / 重建数据集（可选，日常使用不需要）

`models/` 与 `data/processed/` 中已包含训练好的模型与处理好的数据，直接运行即可。
只有在需要**从零复现**时才执行：

```bash
# 第 1 步：下载并预处理 MIT-BIH 数据（约 87 MB，首次约 1~3 分钟）
python -m src.prepare_data

# 第 2 步：训练模型（改进版纯 CPU 实测约 13.6 分钟；产出 models/ecg_cnn.pt 与 models/metrics.json）
python -m src.train
```

> ⚠️ 重新训练会覆盖 `models/ecg_cnn.pt`。当前权重是已验证版本，**请勿随意替换**。

### 3.4 部署到服务器

#### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CARDIOLENS_ENV` | `development` | **生产环境必须设为 `production`**，否则使用开发用固定密钥 |
| `CARDIOLENS_SECRET_KEY` | 无 | **生产环境必填**。用于签名会话 Cookie，**必须保持稳定**——一旦改变，所有使用者的历史入口会立即失效 |
| `CARDIOLENS_STORE` | 代码目录下的 `store/` | 可写数据目录（SQLite 与日志）。建议指到持久化卷，使代码目录可以整体只读 |
| `CARDIOLENS_HOST` / `CARDIOLENS_PORT` | `127.0.0.1` / `5000` | 监听地址。生产环境应只监听回环，由反向代理对外。下面的 systemd 示例显式设为 `8001`，只是为了与 nginx 的 `upstream` 书写一致，并非另一个默认值 |
| `CARDIOLENS_THREADS` | `4` | WSGI 工作线程数 |
| `CARDIOLENS_MAX_CONCURRENT` | `4` | 同时允许排队的分析请求数上限 |
| `CARDIOLENS_SLOT_TIMEOUT` | `8.0` | 等待并发槽位的秒数，超时返回 503 |
| `CARDIOLENS_TORCH_THREADS` | `1` | PyTorch 线程数。**不要调大**，见下方"并发"说明 |
| `CARDIOLENS_ENFORCE_CSRF` | `0`（生产自动开启） | 是否强制校验写请求的 CSRF Token |
| `CARDIOLENS_PUBLIC_URL` | `http://127.0.0.1:5000` | 邮件验证和密码找回链接的公网地址 |
| `SMTP_HOST` 等 | 无 | 配置后启用真实密码找回/邮箱验证邮件；未配置时仅记录开发邮件日志 |

生成密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### systemd 单元示例

```ini
[Unit]
Description=CardioLens ECG Analysis Platform
After=network.target

[Service]
User=cardiolens
WorkingDirectory=/srv/cardiolens
Environment=CARDIOLENS_ENV=production
Environment=CARDIOLENS_SECRET_KEY=<你的密钥>
Environment=CARDIOLENS_STORE=/var/lib/cardiolens
Environment=CARDIOLENS_HOST=127.0.0.1
Environment=CARDIOLENS_PORT=8001
Environment=OMP_NUM_THREADS=1
Environment=MKL_NUM_THREADS=1
ExecStart=/srv/cardiolens/.venv/bin/python /srv/cardiolens/wsgi.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

> **⚠️ 为什么 `ExecStart` 用 `python wsgi.py` 而不是 `waitress-serve wsgi:app`**
>
> `waitress-serve` 是 waitress 自带的命令行入口，它**只认自己的 `--host` / `--port` 参数**，
> 不读 `CARDIOLENS_HOST` / `CARDIOLENS_PORT` 环境变量。写成
> `ExecStart=... waitress-serve --threads=4 wsgi:app` 会静默地使用 waitress 的默认值，
> **监听在 `0.0.0.0:8080`** —— 一方面 nginx 转发到 `127.0.0.1:8001` 会连不上，
> 另一方面应用会直接暴露在所有网卡上，绕过下面"只监听回环"的设计。
>
> 若确实想用命令行入口，必须把监听地址显式写全：
> `waitress-serve --host=127.0.0.1 --port=8001 --threads=4 wsgi:app`。
> `python wsgi.py` 则直接读取上表的环境变量，是更不容易出错的方式。

#### nginx 反向代理要点

```nginx
upstream cardiolens { server 127.0.0.1:8001; }

server {
    listen 443 ssl http2;
    server_name your.domain;
    # ssl_certificate ... 略

    # ECG 上传接口允许 CSV/TXT 文件，应用层限制为 5 MB
    client_max_body_size 6m;

    location /static/ {
        alias /srv/cardiolens/web/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://cardiolens;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # 这一行不可少：缺了它 Flask 会以为请求是 http，
        # 导致 SESSION_COOKIE_SECURE 的 Cookie 根本发不出去
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    gzip on;
    gzip_types application/json text/css application/javascript;
    gzip_min_length 1024;          # 30 秒窗口的响应约 163 KB，压缩比约 3~4 倍

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

> **CSP 说明**：前端使用 Vue 的运行时模板编译（这是"免构建"的代价），因此需要
> `script-src 'self' 'unsafe-eval'`。为配合这一点，前端**硬性禁止使用 `v-html`**，
> 所有服务端文本一律走 `{{ }}` 由 Vue 自动转义；测试里有对应的静态审计用例。

#### 为什么必须单进程多线程

限流计数器与并发信号量都是**进程内**状态。开多个 worker 会：

- 让限额按 worker 数放大，保护措施形同虚设
- 每个 worker 独立加载一份 PyTorch 与模型，内存成倍上涨

而单次分析多次实测保持在亚秒级，单进程多线程的吞吐已经远超课程演示场景的需要。
因此**不要用 `gunicorn -w 4`**，也不要用 waitress 之外的进程模型。

### 3.5 验证

```bash
python scripts/test_web.py        # 离线自测（Flask test_client），170 个断言
python scripts/test_web_e2e.py    # 端到端（真实 HTTP + 真实 waitress 进程），83 个断言
python scripts/test_web_ui.py     # 前端验收（真实浏览器 + 画布像素判据），23 个断言
python scripts/screenshot.py      # 重新生成界面截图到 docs/screenshots_web/
```

三套测试实测 **170 / 170**、**83 / 83** 与 **23 / 23 全部通过**。端到端脚本会自己拉起一个 waitress 进程，
并把可写数据目录指向临时位置，**不会污染真实数据库**。

### 3.6 运维工具

```bash
python scripts/migrate_owner.py --status    # 查看无归属的历史记录与全站概况
python scripts/prune_db.py --status         # 查看数据库占用
python scripts/prune_db.py --keep 50        # 每个会话只保留最近 50 条
```

### 3.7 主要 API 能力

| 能力 | 接口示例 |
|---|---|
| 系统状态与公开数据 | `GET /api/health`、`GET /api/status`、`GET /api/records`、`GET /api/metrics` |
| 公开记录分析 | `GET /api/preview`、`POST /api/analyze` |
| ECG 文件上传 | `POST /api/upload-ecg`、`POST /api/upload-ecg/analyze` |
| 历史报告 | `GET /api/history`、`GET /api/history/{id}`、`DELETE /api/history/{id}`、`POST /api/history/clear` |
| 账号与安全 | `GET /api/auth/captcha`、`POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/logout`、`POST /api/auth/password` |
| 密码找回与邮箱验证 | `/api/auth/password-reset/*`、`/api/auth/email-verification/*` |
| 系统通知 | `GET /api/notifications`、`POST /api/notifications/{id}/read`、`POST /api/notifications/read-all` |
| 科研实验 | `GET/POST /api/research/experiments`、`POST /api/research/experiments/{id}/run`、`GET /api/research/jobs/{job_id}` |

上传接口只接受 CSV/TXT 数值序列，服务端会限制文件大小并返回信号质量结果；不会把任意文件作为静态资源公开。

---

## 四、项目结构

```
medicalAI/
├── wsgi.py                     # ★ 生产入口：app = create_app()
│
├── web/                        # ★ Web 应用
│   ├── __init__.py             #   应用工厂：装配、注册蓝图、错误处理
│   ├── config.py               #   配置：会话 Cookie 策略、并发与限流阈值（均可用环境变量覆盖）
│   ├── session.py              #   会话标识：签名 Cookie 里的随机 owner
│   ├── guard.py                #   请求守卫：限流、并发槽位、Content-Type 校验
│   ├── readiness.py            #   就绪检查与指标/元信息加载
│   ├── bootstrap.py            #   启动装配：日志、线程数、数据库、模型热身
│   ├── errors.py               #   统一错误响应：接口一律 JSON，用户永远看不到堆栈
│   ├── views/                  #   蓝图：状态/记录/分析/历史/认证/通知/科研/上传/SPA 壳
│   ├── templates/index.html    #   SPA 壳（内联首屏数据，深链不白屏）
│   └── static/
│       ├── css/app.css         #   样式表
│       ├── vendor/             #   Vue 3 与 vue-router（本地分发，不走 CDN）
│       └── js/
│           ├── main.js  router.js  api.js  store.js  format.js
│           ├── wave/           #   viewport(视图区间数学) / render(绘制) / interaction(交互)
│           ├── components/     #   EcgStrip BeatChart BeatTable ResultPanel 等
│           └── views/          #   首页 / 分析 / 历史 / 历史详情 / 关于 / 认证 / 科研实验
│
├── src/                        # ★ AI 推理引擎与账号/通知/实验持久化
│   ├── config.py               #   全局配置：路径、信号参数、AAMI 映射、RR 特征定义、免责声明
│   ├── prepare_data.py         #   数据下载 → 带通滤波 → R 峰对齐切分 → beats.npz
│   ├── rr.py                   #   RR 间期特征计算（训练与推理共用，杜绝特征漂移）
│   ├── signal_quality.py       #   信号质量评估与提示
│   ├── model.py                #   ECGNet：1D-CNN 形态分支 + RR 节律 MLP 双分支网络
│   ├── train.py                #   训练脚本：类权重、数据增强、早停、评估、绘图
│   ├── gradcam.py              #   Grad-CAM 可解释性（1D 信号版本）
│   ├── inference.py            #   推理服务：窗口校验、逐搏预测、RR 明细、风险分级
│   ├── db.py                   #   SQLite 持久化：按账号/会话隔离、自愈式 schema 迁移
│   ├── auth_db.py              #   账号、密码哈希、重置令牌、邮箱验证令牌
│   ├── notifications_db.py     #   系统通知与已读状态
│   ├── research_db.py          #   科研实验与异步任务状态
│   └── mailer.py               #   SMTP 邮件适配器与开发日志模式
│
├── scripts/
│   ├── test_web.py             # ★ 离线自测（170 个断言）
│   ├── test_web_e2e.py         # ★ 端到端测试（真实 HTTP + 真实 WSGI）
│   ├── test_web_ui.py          # ★ 前端验收（Playwright 驱动真实浏览器）
│   ├── screenshot.py           #   界面截图（生成 docs/screenshots_web/）
│   ├── migrate_owner.py        #   处理无归属的遗留历史记录
│   └── prune_db.py             #   数据库清理
│
├── data/                       # 数据目录
│   ├── raw/hf/mitdb.parquet    #   原始数据（可由 prepare_data 重新下载，不纳入版本控制）
│   └── processed/
│       ├── beats.npz           #   切分好的心搏张量 (N, 252) 与标签（仅训练需要）
│       ├── record_meta.json    #   各记录元信息
│       ├── signals/            #   滤波后完整信号（推理时读取）
│       └── annots/             #   专家标注（用于与模型结果对照）
│
├── models/                     # 训练产物
│   ├── ecg_cnn.pt              #   模型权重（103,109 参数）
│   ├── metrics.json            #   测试集指标（由实际测试集计算）
│   ├── confusion_matrix.png    #   混淆矩阵
│   ├── training_curve.png      #   训练曲线
│   ├── train_run2/3/4.log      #   训练日志（过程记录）
│   └── archive/                #   历史版本留存（早期无 RR 分支的模型与指标）
│
├── store/                      # 运行时数据（数据库与日志，不纳入版本控制）
└── docs/
    ├── screenshots_web/        # ★ Web 版界面截图（23 张）
    └── desktop_era_evidence.md #   桌面版时代的产物与验收证据留存
```

> **运行时最小部署集**：`web/` + `src/` + `models/` + `data/processed/{signals,annots,record_meta.json}`，
> 合计约 **115 MB**。**不需要** `data/processed/beats.npz`（91 MB，仅训练用）与 `data/raw/`。
> 就绪检查刻意不要求前者——否则只部署运行最小集时整个应用会表现为不可用。

---

## 五、核心实现要点

### 5.1 数据划分：inter-patient（跨患者）而非随机切分

很多公开实现把全部心搏**随机**划分为训练/测试集，但同一患者的不同心搏形态高度相似，
随机切分会让同一患者的心搏同时出现在训练集和测试集，**指标被显著高估**。

本项目严格采用文献 *de Chazal et al., 2004* 提出的 **DS1 / DS2 跨患者划分**：

- **DS1**（22 条记录）→ 再按固定间隔抽出验证记录 → 训练集 + 验证集
- **DS2**（22 条记录）→ **完全留作测试集**，训练全程不可见
- 两集合患者完全不重叠，指标更接近真实临床场景

同时按 AAMI 惯例剔除 4 条起搏搏动记录（102 / 104 / 107 / 217）。

### 5.2 类别不平衡处理

MIT-BIH 中正常搏动占比超过 88%，直接训练会让模型"全猜正常"也能拿到高准确率。
本项目采用**平方根逆频率加权 + 上限截断**：

```
w_c = sqrt(N / (C · n_c))      然后 clip 到 10.0，最后归一化到均值为 1
```

- 用**平方根**而非直接逆频率：直接逆频率会让极少数类（如 Q 类）权重高达 1300+，几个样本就能主导梯度
- **截断上限 10.0**：避免极小样本类破坏训练稳定性
- **归一化到均值 1**：不改变整体学习率量级

### 5.3 数据增强

单搏分类中同类搏动形态高度一致，模型极易"记住"训练样本 → 训练损失降到 0.08 而验证损失反而上升到 0.9 上下。
本项目在训练期施加三类扰动，分别对应真实场景的变异来源：

| 扰动 | 参数 | 模拟的真实情况 |
|---|---|---|
| 随机时移 | ±12 采样点（≈±33 ms） | R 峰检测的定位误差 |
| 幅度缩放 | 0.9 ~ 1.1 倍 | 不同患者体表电位与电极阻抗差异 |
| 高斯噪声 | σ = 0.08 | 采集链路噪声 |

时移使用 `replicate` 边缘填充，避免补零在波形两端造成虚假的陡变。

### 5.4 RR 间期特征：为什么用相对比值而不是绝对值

仅凭单搏波形难以区分"室上性早搏"与"正常搏动"——两者 QRS 形态接近。真正的判别信息在
**节律**里：早搏的特征是"提前出现"，即该搏与前一心搏的间期明显短于该患者的基线间期。

最初版本直接把前后 RR 间期的**绝对值**（秒）送进网络。但在真实数据上做判别力分析后发现：
不同患者的基线心率差异极大（MIT-BIH 各记录的中位 RR 从 **0.533 s 到 1.197 s**，即 50~113 bpm），
绝对间期被"患者基线"严重混淆，同一段 0.6 s 的 RR 在一个心动过速患者身上是正常，
在心动过缓患者身上却是明显提前。用 AUC 量化：

| 判别任务 | 绝对 RR 的 AUC | 加入相对比值后的 AUC |
|---|:---:|:---:|
| V（室性早搏）vs N | 0.615 | **0.811** |

> 上表数值与 `src/rr.py` 中记录的实测结果一致；其他类别的单特征 AUC 未在产物中留存，故不列出。

因此本项目最终采用 **4 维 RR 特征**，同时保留绝对值与相对于基线的比值：

| 序号 | 特征名 | 含义 |
|:---:|---|---|
| 1 | `rr_prev_sec` | 与**前一**心搏的间期（秒），归一化到 [0,1] |
| 2 | `rr_next_sec` | 与**后一**心搏的间期（秒），归一化到 [0,1] |
| 3 | `rr_prev_ratio` | 前间期 ÷ **该记录中位 RR**（基线），提供心率无关的"提前/延迟"判据 |
| 4 | `rr_next_ratio` | 后间期 ÷ 该记录中位 RR |

这 4 维特征不是直接拼到卷积特征上，而是先经一层 **4→16 的 MLP 升维**再与形态分支拼接，
让网络有机会学习 RR 特征之间的非线性组合。

> 为什么用**中位数**做基线：早搏会使少数 RR 明显偏离，均值容易被拉偏，中位数对离群值稳健。

为确保**训练与推理使用完全一致的特征**，RR 计算被抽出为独立模块 `src/rr.py`，
由 `prepare_data.py`（训练侧）与 `inference.py`（推理侧）共同调用，
从代码结构上杜绝"训练用一套特征、上线用另一套"的隐性 Bug。

边界处理：窗口内**第一个**心搏会向前回溯取窗口外的真实间期，**最后一个**心搏同理向后取，
因此边界搏动的 RR 特征同样真实有效，不会用 0 或默认值填充。

### 5.5 Grad-CAM 可解释性

心电判别高度依赖 QRS 波群的局部形态，因此网络最后一层卷积**不做下采样**，保留 31 个时间步的分辨率。
Grad-CAM 将分类头对特征图的梯度在时间维取平均作为通道权重，加权求和后 ReLU 并上采样回 252 点，
叠加在波形上即可直观看到"模型在看哪一段"——正常情况下热力图应集中在 **QRS 波群**附近。

Grad-CAM 只解释波形分支，不参与推理：热力图在推理完成后单独计算，**不影响分类结果**；
即使计算失败，分析流程也不会中断（仅不显示热力图）。

### 5.6 Web 架构要点

| 关键点 | 做法 | 原因 |
|---|---|---|
| **账号与会话隔离** | 登录用户按账号 ID 过滤历史；未登录用户使用签名 Cookie 保存 256 位随机标识 | 登录后可跨浏览器访问，匿名用户仍可直接使用；两种模式都不会互相看到记录 |
| **越权不可探测** | 访问非本人的记录返回 404 而不是 403 | 403 会泄露"这个 id 存在"这一信息，可被用来探测别的会话有多少条记录 |
| **并发不失控** | 引擎内部有互斥锁串行化推理；外层再限制排队人数，超时快速返回 503 | 真正的风险不是锁竞争而是 CPU 超订——多个请求各自拉起线程会互相抢核 |
| **异步实验队列** | 科研批量实验返回任务 ID，后台线程执行，前端轮询状态 | 不阻塞浏览器请求；保留轻量部署特性，生产多进程时建议替换为 Redis + Celery/RQ |
| **不造假进度** | 分析期间显示不确定进度条 | 推理是一次同步调用，拿不到阶段进度；编一个百分比是在骗用户 |
| **前端免构建但本地分发** | Vue 与 vue-router 两个文件随仓库走 | 目标部署环境在国内，第三方 CDN 抖动会造成首屏白页而服务端一切正常，排查成本极高 |
| **不泄露模型目录** | `/media` 用白名单，只放行两张图 | 原实现会把整个 `models/` 暴露出去，公网可直接下载模型权重与训练日志 |

### 5.7 波形渲染与交互（前端最有技术含量的部分）

桌面版的波形用 `QPainter` 自绘，具备缩放、平移、悬停读数等能力。Web 版用 Canvas 2D 重写并补齐了同样四项：

**核心是把"视图区间"建模为采样点区间 `{a, b}`，而不是像素区间。**
所有坐标换算都经过一对纯函数：

```js
xOf(vp, idx)   // 采样点 -> 画布 x
idxOf(vp, x)   // 画布 x -> 采样点
```

缩放与平移只改 `{a, b}`，绘图层按当前区间重算：

| 交互 | 做法 |
|---|---|
| 滚轮缩放 | 以**光标处采样点**为锚点。先记录锚点到两端的距离，再按比例缩放这两段距离，锚点自然不动 |
| 拖拽平移 | 记下按下时的视图，按像素位移换算成采样点位移。从按下时的视图推算而非累加，避免误差累积 |
| 双击复位 | 区间恢复为整段 |
| 悬停读数 | 由反函数得采样点，画虚线十字线并显示绝对时间与幅值 |
| 边界夹取 | 跨度限制在 `max(60, n/200)` 与 `n` 之间，且不越出 `[0, n]` |
| 纵轴重标定 | 按**可见区间**的值域计算，放大后局部波动不会被整段极值压平 |

## 六、模型效果

> 以下指标均在**跨患者测试集 DS2** 上评估，测试集在训练全程不可见。

**总体指标**（改进版测试集 DS2，共 **54,037** 个心搏）

| 指标 | 数值 |
|---|:---:|
| 准确率 Accuracy | **86.13%** |
| Macro-F1（N/S/V/F 四类，与基线可比） | **0.520** |
| Macro-F1（含 Q 的五类） | **0.435** |

**逐类指标**

| 类别 | 名称 | 精确率 PPV | 召回率 Se | F1 | 测试样本数 |
|:---:|---|:---:|:---:|:---:|:---:|
| **N** | 正常搏动 | 0.892 | 0.961 | **0.925** | 44,484 |
| **S** | 室上性早搏 | 0.352 | **0.193** | 0.250 | 1,837 |
| **V** | 室性早搏 | 0.834 | 0.925 | **0.877** | 3,441 |
| **F** | 融合搏动 | 0.024 | **0.034** | 0.028 | 388 |
| **Q** | 未分类/起搏搏动 | 0.324 | **0.058** | 0.098 | **3,887** |

**混淆矩阵**（行 = 真实类别，列 = 模型预测）

| 真实＼预测 | N | S | V | F | Q |
|---|:---:|:---:|:---:|:---:|:---:|
| **N** | **42,767** | 1,155 | 469 | 88 | 5 |
| **S** | 1,031 | **355** | 48 | 396 | 7 |
| **V** | 1,073 | 118 | **3,182** | 61 | 7 |
| **F** | 359 | 8 | 8 | **13** | 0 |
| **Q** | 3,719 | 20 | 1 | 1 | **224** |

### 改进结果与剩余限制

本次改进保留 4 条起搏记录，并使用少数类平衡采样和 S/F/Q 召回导向的选模指标：

1. **S 类召回率从 0.082 提升到 0.193**，精确率为 0.352；相比第一轮候选，当前版本选择了更好的整体平衡。
2. **F 类不再完全预测为 N**，召回率达到 0.034、F1 达到 0.028；由于 F 类仍只有 388 个测试样本，
   该结果仍然有限。
3. **Q 类测试样本从 7 个增加到 3,887 个**，召回率为 0.058、F1 为 0.098，已经可以进行有意义的重新评估，
   但大量 Q 仍被判为 N，后续需要继续优化起搏信号特征或引入专门的 Q 类模型。
4. 当前版四类 Macro-F1 为 0.520，高于基线 0.504；这是在提高 S/F/Q 可见性的同时恢复整体性能后的候选版本。

**改进版训练配置**：模型参数量 103,109；训练集 42,401 搏 / 验证集 13,014 搏 / 测试集 54,037 搏；
第 5 轮为最佳轮次，连续 6 轮未提升触发早停；优化器 AdamW，学习率 1e-3，weight_decay 5e-4，
启用数据增强和温和的少数类平衡采样；纯 CPU 训练耗时约 **12.9 分钟**。

改进前基线保存在 `models/baseline/`，第一轮候选保存在 `models/experiments/`，便于继续做消融实验和回滚比较。

> 完整指标见 `models/metrics.json`，也可在应用**关于**页直接查看。

---

## 七、常见问题

**Q1：使用者需要安装什么吗？需要联网吗？**
A：只需要一个现代浏览器，不需要安装任何东西。前端依赖（Vue、vue-router）由服务端本地提供，
不依赖任何第三方 CDN，因此在网络受限的环境里也能正常打开。

**Q2：登录后可以在其他浏览器看到历史记录吗？**
A：可以。登录后历史记录按账号 ID 保存，在其他浏览器或设备登录同一账号即可访问。
未登录时使用浏览器标识隔离记录，换浏览器或清除浏览器数据后，匿名记录将失去访问入口，
但数据仍保存在服务端。

**Q3：忘记密码或需要验证邮箱怎么办？**
A：登录页提供密码找回入口；系统会生成限时重置令牌。注册时填写邮箱后，可在账户中心申请邮箱验证。
生产部署需配置 SMTP_HOST、SMTP_PORT、SMTP_USER、SMTP_PASSWORD、MAIL_FROM 和
CARDIOLENS_PUBLIC_URL，开发环境则会把测试令牌写入服务日志。

**Q4：`python -m src.prepare_data` 下载很慢或失败？**
A：脚本默认使用 HuggingFace 镜像站（`hf-mirror.com`）下载 MIT-BIH 的完整 parquet 镜像，
国内实测可达 400 KB/s ~ 1.8 MB/s。若仍失败，可手动下载该 parquet 文件并放置到
`data/raw/hf/mitdb.parquet` 后重新运行。

**Q5：训练要多久？**
A：改进版纯 CPU（无 GPU）实测约 13.6 分钟。脚本带**早停机制**，本次训练在第 12 轮停止、
第 4 轮为最佳模型。想快速体验可执行 `python -m src.train --epochs 5`。

**Q6：可以关掉数据增强做对照实验吗？**
A：可以。`python -m src.train --no-augment` 即可关闭，便于在报告中做消融对比。

**Q7：为什么 Q 类（未分类/起搏搏动）的指标很差？**
A：当前改进版已经保留 102、104、107、217 四条起搏记录，测试集中有 **3,887 个 Q 类样本**。
Q 类召回率为 0.085，仍有大量样本被判为 N，说明起搏信号的特征区分仍不足。
`models/baseline/` 中保存了剔除起搏记录的改进前基线，`models/metrics.json` 保存当前结果。

**Q8：F 类（融合搏动）和 S 类的指标仍不理想，是 Bug 吗？**
A：改进前不是接口 Bug，而是类别不平衡和样本不足造成的模型能力问题。当前版本已将 S 类召回率提升到 0.270，
并使 F 类召回率达到 0.054，但仍需继续增加有效样本和改进特征，详见第六节的"改进结果与剩余限制"。

**Q9：分析时长为什么限制在 3~30 秒？**
A：逐搏 Grad-CAM 需要逐样本反向传播，计算量与窗口内搏动数成正比。
上限 30 秒（约 30~60 次心搏）可在 CPU 上于亚秒级返回结果，保证交互流畅；
下限 3 秒确保窗口内至少包含若干次心搏，统计才有意义。

**Q10：波形上那些标记是什么意思？怎么操作？**
A：绿色折线是心电波形，顶部圆点是逐搏判定（颜色对应类别），橙色面积是该搏的 Grad-CAM 显著性。
**滚轮缩放、按住拖动平移、双击复位、鼠标悬停可读数**（显示时间与幅值）。点击搏动可联动下方明细。

**Q11：多人同时分析会不会卡？**
A：不会。单次分析多次实测为亚秒级；服务端限制同时排队的请求数，超时会返回"当前分析请求较多"，
而不是让请求无限堆积。实测 8 个并发分析请求全部成功，总耗时不到 1 秒。

**Q12：怎么备份或清理服务端的历史数据？**
A：数据库是 `CARDIOLENS_STORE` 下的 `app.db`（SQLite 单文件），直接复制即可备份。
清理用 `python scripts/prune_db.py --keep N`（每个会话保留最近 N 条）或 `--before 日期`。

---

## 八、技术栈

| 层次 | 技术选型 | 选择理由 |
|---|---|---|
| 前端框架 | **Vue 3（ESM 构建，本地分发）** | 免构建：不引入 npm 与打包工具，部署时服务器只需 Python |
| 图形绘制 | **原生 Canvas 2D** | 波形需要自定义网格、刻度、缩放平移与热力图叠加，自绘最直接且无额外依赖 |
| 路由 | **vue-router 4（history 模式）** | URL 与传统多页应用一致，深链可分享 |
| 状态管理 | **Vue `reactive()` 单例** | 需要跨视图共享的只有六项，引入 Pinia 收益为负 |
| 后端 | **Flask 3（应用工厂 + 蓝图）** | 与推理引擎同为 Python，零跨语言成本 |
| WSGI 服务器 | **Waitress（单进程多线程）** | 跨平台（gunicorn 不支持 Windows）；单进程使限流与并发控制的内存状态保持正确 |
| 反向代理 | **nginx** | TLS 终止、静态资源直出、gzip、请求体上限 |
| 深度学习 | PyTorch 2.x（**CPU 版**） | 动态图易调试，CPU 版体积可控，无需显卡 |
| 信号处理 | SciPy（Butterworth 带通 + `filtfilt`） | 零相位滤波，不引入时间偏移 |
| 数据处理 | NumPy / pandas / PyArrow | parquet 读取快，仅训练阶段需要 |
| 评估 | scikit-learn | 混淆矩阵、逐类 PPV/Se/F1 |
| 可视化图表 | Matplotlib | 训练曲线与混淆矩阵静态图（由关于页显示 PNG） |
| 持久化 | SQLite（WAL 模式） | 免安装、免配置；WAL 让多人读写不互相阻塞 |
| 自动化测试 | 自研三套脚本（离线 / 端到端 / 前端验收） | 离线与端到端只用标准库；前端验收用 Playwright 驱动真实浏览器，因为波形交互只在浏览器里才存在 |

---

## 九、文档索引

| 文档 | 内容 |
|---|---|
| `README.md` | 本文件：快速开始、项目结构、核心实现、常见问题 |
| `docs/screenshots_web/` | Web 版各功能界面截图（23 张，当前交付形态） |
| `docs/desktop_era_evidence.md` | 桌面版时代的产物 MD5、验收证据与截图清单（留档） |

---

**再次声明**：以上结果由机器学习模型自动生成，仅用于课程项目演示与辅助分析，
不构成医疗诊断依据，不能用于任何临床决策。如有健康问题请及时就医。
