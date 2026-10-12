"""ECGNet：用于单心搏 AAMI 五分类的双分支神经网络。

设计取舍：心电单搏只有 252 个采样点、数万条样本，属于典型的小规模时序分类问题。
因此刻意采用浅层 1D-CNN（约 10 万参数）而非深层残差网络——参数量小、CPU 训练
分钟级完成，且最后一层卷积保留 31 个时间步的空间分辨率，便于做 Grad-CAM 可解释性。

网络分为两路：
  * 形态分支（1D-CNN）—— 从 252 点波形中学习 QRS/T 波的形态特征
  * 节律分支（MLP）  —— 输入前后 RR 间期，提供"这一搏是否提前出现"的信息
两路特征拼接后送入分类头。加入节律分支的原因见 config.RR_MIN_SEC 处的说明。
"""
from __future__ import annotations

import torch
import torch.nn as nn

from . import config as C

# Grad-CAM 需要挂在这层卷积的输出上
CAM_LAYER_NAME = "conv_block4"


class ECGNet(nn.Module):
    def __init__(self, n_classes: int = len(C.AAMI_CLASSES), dropout: float = 0.4):
        super().__init__()

        def block(in_ch, out_ch, kernel):
            return nn.Sequential(
                nn.Conv1d(in_ch, out_ch, kernel, padding=kernel // 2),
                nn.BatchNorm1d(out_ch),
                nn.ReLU(inplace=True),
                nn.MaxPool1d(2),
            )

        # 252 -> 126 -> 63 -> 31
        self.conv_block1 = block(1, 32, 7)
        self.conv_block2 = block(32, 64, 5)
        self.conv_block3 = block(64, 128, 5)

        # 最后一层卷积不下采样，作为 Grad-CAM 的特征图来源
        self.conv_block4 = nn.Sequential(
            nn.Conv1d(128, 128, 3, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(inplace=True),
        )

        # 全局平均池化反映整段波形的平均能量，全局最大池化则保留最突出的
        # 局部形态（如 R 波尖峰）。心电判别高度依赖尖峰形态，只用平均池化
        # 会把 QRS 的尖锐特征摊平，因此这里把两者拼接后送入分类头。
        self.pool_avg = nn.AdaptiveAvgPool1d(1)
        self.pool_max = nn.AdaptiveMaxPool1d(1)

        # 节律分支：4 维 RR 特征（前后绝对间期 + 相对基线比值）。形态分支看不到"这一搏是否提前出现"，
        # 而这恰是区分室上性早搏（S）与正常搏动（N）的唯一依据，故单开一路。
        self.rr_mlp = nn.Sequential(
            nn.Linear(C.RR_DIM, 16),
            nn.ReLU(inplace=True),
            nn.BatchNorm1d(16),
        )

        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(256 + 16, n_classes)

    def forward(self, x: torch.Tensor, rr: torch.Tensor | None = None) -> torch.Tensor:
        """x: (B, 1, 252)，rr: (B, 4) -> logits (B, 5)

        rr 允许缺省：为 None 时以 0 填充（对应归一化区间的最小值）。
        这样即便调用方暂时拿不到节律信息，前向传播依然可用，只是退化为纯形态模型。
        """
        x = self.conv_block1(x)
        x = self.conv_block2(x)
        x = self.conv_block3(x)
        x = self.conv_block4(x)
        x = torch.cat([
            self.pool_avg(x).squeeze(-1),
            self.pool_max(x).squeeze(-1),
        ], dim=1)

        if rr is None:
            rr = torch.zeros(x.shape[0], C.RR_DIM, device=x.device, dtype=x.dtype)
        return self.fc(self.dropout(torch.cat([x, self.rr_mlp(rr)], dim=1)))

    def count_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def build_model(**kwargs) -> ECGNet:
    return ECGNet(**kwargs)


if __name__ == "__main__":
    C.force_utf8_stdout()
    net = build_model()
    dummy = torch.randn(4, 1, C.BEAT_LEN)
    dummy_rr = torch.rand(4, C.RR_DIM)
    print(f"参数量: {net.count_params():,}")
    print(f"输入 {tuple(dummy.shape)} + {tuple(dummy_rr.shape)} -> 输出 {tuple(net(dummy, dummy_rr).shape)}")
    print(f"缺省节律特征时 -> 输出 {tuple(net(dummy).shape)}")
