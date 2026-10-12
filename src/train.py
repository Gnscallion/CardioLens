"""训练 ECGNet 并输出评估指标。

划分方式遵循 de Chazal 的 inter-patient 方案：
  DS1 -> 再切出验证集用于早停 / 选模型
  DS2 -> 完全留作测试集，训练过程中不可见
这样得到的指标比"同患者随机切分"更接近真实临床场景（跨患者泛化）。

用法：python -m src.train
"""
from __future__ import annotations

import json
import time

import matplotlib
matplotlib.use("Agg")               # 无界面后端，避免在服务器/终端环境报错
import matplotlib.pyplot as plt

# matplotlib 默认字体不含中文字形，不设置会导致图表里的中文变成方块
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from torch.utils.data import DataLoader, TensorDataset

from . import config as C
from .model import build_model
from .prepare_data import DS1

# 从 DS1 中按固定间隔抽出验证记录，保证验证集与训练集患者不重叠
VAL_RECORDS = set(sorted(DS1)[::5])

SEED = 42


def set_seed(seed: int = SEED) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_split():
    if not C.BEATS_NPZ.exists():
        raise SystemExit("未找到 data/processed/beats.npz，请先运行：python -m src.prepare_data")

    d = np.load(C.BEATS_NPZ, allow_pickle=True)
    X, y, rec = d["X"], d["y"], d["rec"]
    if "R" not in d:
        raise SystemExit(
            "beats.npz 缺少节律特征 R，请重新运行：python -m src.prepare_data --force"
        )
    R = d["R"]

    is_ds1 = np.isin(rec, list(DS1))
    is_val = np.isin(rec, list(VAL_RECORDS))

    def pack(mask):
        return X[mask][:, None, :], R[mask], y[mask]     # (N, 1, L), (N, 4), (N,)

    return pack(is_ds1 & ~is_val), pack(is_ds1 & is_val), pack(~is_ds1)


# 「Q 类」在按 AAMI 惯例剔除起搏记录（102/104/107/217）后仅剩十余个样本，
# 无论怎么加权都无法学到，反而会因权重过大破坏训练稳定性，故对其设权重上限。
WEIGHT_CAP = 10.0


def compute_class_weights(y: np.ndarray) -> torch.Tensor:
    """类别权重，缓解正常搏动占绝大多数导致的类别不平衡。

    采用「平方根逆频率」而非直接逆频率：直接逆频率会让 Q 类权重高达 1300+，
    少数几个样本就能主导梯度；平方根后梯度比例更温和，再把上限截到
    ``WEIGHT_CAP``，最后归一化到均值为 1（不改变整体学习率量级）。
    """
    counts = np.bincount(y, minlength=len(C.AAMI_CLASSES)).astype(np.float64)
    counts = np.maximum(counts, 1.0)
    weights = np.sqrt(len(y) / (len(C.AAMI_CLASSES) * counts))
    weights = np.clip(weights, None, WEIGHT_CAP)
    weights = weights / weights.mean()
    return torch.tensor(weights, dtype=torch.float32)


def augment_batch(xb: torch.Tensor, shift_max: int = 12, noise_std: float = 0.08,
                  scale_range: tuple[float, float] = (0.9, 1.1)) -> torch.Tensor:
    """训练期数据增强：随机时移 + 幅度缩放 + 高斯噪声。

    单搏分类中同类搏动的形态高度一致，模型很容易靠"记住"训练样本把训练损失
    压到 0.03 左右，但验证损失反而上升（实测从 1.0 涨到 2.9）——典型过拟合。
    三类扰动分别对应真实场景中的变异来源：
      * 时移 ±12 采样点（≈±33 ms）：模拟 R 峰检测的定位误差
      * 幅度缩放：模拟不同患者体表电位与电极阻抗差异
      * 高斯噪声：模拟采集链路噪声
    """
    B, _, L = xb.shape
    device = xb.device

    if shift_max > 0:
        shifts = torch.randint(-shift_max, shift_max + 1, (B,), device=device)
        # 边缘用 replicate 填充，避免补零在波形两端造成虚假的陡变
        padded = F.pad(xb, (shift_max, shift_max), mode="replicate")
        idx = torch.arange(L, device=device).unsqueeze(0) + (shift_max - shifts).unsqueeze(1)
        xb = padded.gather(2, idx.unsqueeze(1))

    if scale_range is not None:
        lo, hi = scale_range
        scales = torch.empty(B, 1, 1, device=device).uniform_(lo, hi)
        xb = xb * scales

    if noise_std > 0:
        xb = xb + torch.randn_like(xb) * noise_std

    return xb


def evaluate(model, X, R, y, device, batch_size=512):
    model.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(X), batch_size):
            xb = torch.from_numpy(X[i:i + batch_size]).to(device)
            rb = torch.from_numpy(R[i:i + batch_size]).to(device)
            preds.append(model(xb, rb).argmax(dim=1).cpu().numpy())
    pred = np.concatenate(preds) if preds else np.array([], dtype=np.int64)

    acc = float((pred == y).mean()) if len(y) else 0.0
    p, r, f1, sup = precision_recall_fscore_support(
        y, pred, labels=list(range(len(C.AAMI_CLASSES))), zero_division=0
    )
    # 主指标：Q 类样本过少（十余个）不具统计意义，Macro-F1 按 N/S/V/F 四类计算。
    # 同时也保留五类 Macro-F1，便于对照。
    main_idx = [i for i, c in enumerate(C.AAMI_CLASSES) if c != "Q"]
    return {
        "accuracy": acc,
        "macro_f1": float(f1[main_idx].mean()),
        "macro_f1_5class": float(f1.mean()),
        "per_class": {
            C.AAMI_CLASSES[i]: {
                "precision": float(p[i]),   # PPV
                "recall": float(r[i]),      # Se / 敏感度
                "f1": float(f1[i]),
                "support": int(sup[i]),
            }
            for i in range(len(C.AAMI_CLASSES))
        },
        "confusion": confusion_matrix(
            y, pred, labels=list(range(len(C.AAMI_CLASSES)))
        ).tolist(),
        "pred": pred,
    }


def plot_confusion(cm: list[list[int]], path):
    cm = np.asarray(cm)
    fig, ax = plt.subplots(figsize=(6.2, 5.2), dpi=140)
    row_sum = cm.sum(axis=1, keepdims=True)
    norm = np.divide(cm, row_sum, out=np.zeros_like(cm, dtype=float), where=row_sum != 0)

    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(C.AAMI_CLASSES)), C.AAMI_CLASSES)
    ax.set_yticks(range(len(C.AAMI_CLASSES)), C.AAMI_CLASSES)
    ax.set_xlabel("模型预测")
    ax.set_ylabel("专家标注")
    ax.set_title("AAMI 五分类混淆矩阵（行归一化）")

    for i in range(len(C.AAMI_CLASSES)):
        for j in range(len(C.AAMI_CLASSES)):
            ax.text(j, i, f"{cm[i, j]}\n{norm[i, j]:.0%}", ha="center", va="center",
                    fontsize=8, color="white" if norm[i, j] > 0.5 else "#1f2937")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_curves(history: dict, path):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), dpi=140)
    axes[0].plot(history["epoch"], history["train_loss"], label="训练损失", color="#2563eb")
    axes[0].plot(history["epoch"], history["val_loss"], label="验证损失", color="#dc2626")
    axes[0].set_xlabel("轮次"); axes[0].set_ylabel("损失"); axes[0].legend(); axes[0].set_title("损失曲线")

    axes[1].plot(history["epoch"], history["val_acc"], label="验证准确率", color="#059669")
    axes[1].plot(history["epoch"], history["val_macro_f1"], label="验证 Macro-F1", color="#d97706")
    axes[1].set_xlabel("轮次"); axes[1].set_ylabel("指标"); axes[1].legend(); axes[1].set_title("验证指标")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main(epochs: int = 45, batch_size: int = 256, lr: float = 1e-3,
         patience: int = 12, use_augment: bool = True) -> None:
    C.force_utf8_stdout()
    set_seed()
    C.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    (Xtr, Rtr, ytr), (Xva, Rva, yva), (Xte, Rte, yte) = load_split()
    print(f"[训练] 设备={device}  训练集={len(ytr)}  验证集={len(yva)}  测试集={len(yte)}")
    print(f"[训练] 验证记录（与训练集患者不重叠）：{sorted(VAL_RECORDS)}")

    def dist(y):
        c = np.bincount(y, minlength=len(C.AAMI_CLASSES))
        return " ".join(f"{C.AAMI_CLASSES[i]}={c[i]}" for i in range(len(c)))
    print(f"[训练] 训练集分布 {dist(ytr)}")
    print(f"[训练] 验证集分布 {dist(yva)}")

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(Rtr), torch.from_numpy(ytr)),
        batch_size=batch_size, shuffle=True, drop_last=False,
    )

    model = build_model().to(device)
    print(f"[训练] 模型参数量 {model.count_params():,}")

    weights = compute_class_weights(ytr).to(device)
    print(f"[训练] 类别权重 " + " ".join(
        f"{C.AAMI_CLASSES[i]}={weights[i]:.2f}" for i in range(len(weights))
    ))
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=5e-4)
    print(f"[训练] 数据增强：{'开启' if use_augment else '关闭'}")
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=3
    )

    history = {"epoch": [], "train_loss": [], "val_loss": [], "val_acc": [], "val_macro_f1": []}
    best_f1, best_state, best_epoch, wait = -1.0, None, 0, 0
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for xb, rb, yb in train_loader:
            xb, rb, yb = xb.to(device), rb.to(device), yb.to(device)
            # 只对波形做增强：RR 间期是节律事实，扰动它会破坏标签语义
            if use_augment:
                xb = augment_batch(xb)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(xb, rb), yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            total_loss += loss.item() * len(yb)
        train_loss = total_loss / max(len(ytr), 1)

        val = evaluate(model, Xva, Rva, yva, device)
        val_loader_loss = 0.0
        model.eval()
        with torch.no_grad():
            for i in range(0, len(Xva), 512):
                xb = torch.from_numpy(Xva[i:i + 512]).to(device)
                rb = torch.from_numpy(Rva[i:i + 512]).to(device)
                yb = torch.from_numpy(yva[i:i + 512]).to(device)
                val_loader_loss += criterion(model(xb, rb), yb).item() * len(yb)
        val_loss = val_loader_loss / max(len(yva), 1)

        scheduler.step(val["macro_f1"])

        history["epoch"].append(epoch)
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_acc"].append(val["accuracy"])
        history["val_macro_f1"].append(val["macro_f1"])

        flag = ""
        if val["macro_f1"] > best_f1:
            best_f1, best_epoch, wait = val["macro_f1"], epoch, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            flag = "  <- 最优"
        else:
            wait += 1

        print(f"  Epoch {epoch:2d}/{epochs} | 训练损失 {train_loss:.4f} | "
              f"验证损失 {val_loss:.4f} | 验证准确率 {val['accuracy']:.4f} | "
              f"验证 Macro-F1 {val['macro_f1']:.4f}{flag}")

        if wait >= patience:
            print(f"[训练] 验证指标连续 {patience} 轮未提升，提前停止")
            break

    elapsed = time.time() - t0
    print(f"[训练] 完成，用时 {elapsed / 60:.1f} 分钟，最优轮次 {best_epoch}")

    if best_state is not None:
        model.load_state_dict(best_state)

    test = evaluate(model, Xte, Rte, yte, device)
    print(f"\n[测试集 DS2 结果] 准确率 {test['accuracy']:.4f}")
    print(f"                  Macro-F1（N/S/V/F 四类，主指标） {test['macro_f1']:.4f}")
    print(f"                  Macro-F1（含 Q 五类，供对照）    {test['macro_f1_5class']:.4f}")
    print("  类别      精确率(PPV)   召回率(Se)   F1     样本数")
    for code in C.AAMI_CLASSES:
        m = test["per_class"][code]
        print(f"  {code:2s} {C.CLASS_NAMES_ZH[code]:<8s} "
              f"{m['precision']:.4f}      {m['recall']:.4f}    {m['f1']:.4f}   {m['support']}")

    torch.save(
        {
            "state_dict": model.state_dict(),
            "classes": C.AAMI_CLASSES,
            "beat_len": C.BEAT_LEN,
            "fs": C.FS,
            "val_records": sorted(VAL_RECORDS),
            "count_params": model.count_params(),
        },
        C.MODEL_PATH,
    )

    test.pop("pred")
    payload = {
        "test": test,
        "history": history,
        "best_epoch": best_epoch,
        "train_seconds": round(elapsed, 1),
        "n_params": model.count_params(),
        "n_train": int(len(ytr)), "n_val": int(len(yva)), "n_test": int(len(yte)),
        "val_records": sorted(VAL_RECORDS),
        "class_weights": {c: float(weights[i]) for i, c in enumerate(C.AAMI_CLASSES)},
        "class_names": C.CLASS_NAMES_ZH,
        "main_metric": "macro_f1",
        "use_augment": bool(use_augment),
        "dropout": 0.4,
        "weight_decay": 5e-4,
        "lr": lr,
        "metric_note": (
            "Q 类（未分类/起搏搏动）在按 AAMI 惯例剔除 4 条起搏记录后，"
            "测试集仅剩极少样本，不具统计意义，故主指标 Macro-F1 按 N/S/V/F 四类计算；"
            "macro_f1_5class 为含 Q 的五类 Macro-F1，仅供对照。"
        ),
    }
    C.METRICS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    plot_confusion(test["confusion"], C.MODEL_DIR / "confusion_matrix.png")
    plot_curves(history, C.MODEL_DIR / "training_curve.png")
    print(f"\n[保存] 模型 -> {C.MODEL_PATH}")
    print(f"[保存] 指标 -> {C.METRICS_PATH}")
    print(f"[保存] 图表 -> models/confusion_matrix.png, models/training_curve.png")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="训练心电搏动分类模型")
    ap.add_argument("--epochs", type=int, default=45)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=12)
    ap.add_argument("--no-augment", action="store_true",
                    help="关闭数据增强（用于对照实验）")
    a = ap.parse_args()
    main(epochs=a.epochs, batch_size=a.batch_size, lr=a.lr,
         patience=a.patience, use_augment=not a.no_augment)
