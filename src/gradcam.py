"""一维 Grad-CAM：定位模型做出该判断时，波形上哪些时刻最关键。

原理（Grad-CAM 在一维信号上的推广）：
  1. 取最后一层卷积的特征图 A ∈ R^{C×T}，它保留了 31 个时间步；
  2. 对目标类别得分求梯度 ∂y/∂A，在时间维求平均得到每个通道的权重 α_c；
  3. 加权求和并 ReLU：L = ReLU(Σ_c α_c · A_c)，得到长度为 T 的重要性曲线；
  4. 上采样回原始长度，叠加到心电波形上。

对心电而言，高亮区域通常落在 QRS 波群附近——这与临床医生判读早搏时
关注 QRS 形态（宽大畸形提示室性来源）的经验是一致的。
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from . import config as C
from .model import CAM_LAYER_NAME


class GradCAM1D:
    def __init__(self, model: torch.nn.Module, layer_name: str = CAM_LAYER_NAME):
        self.model = model
        self.activations: torch.Tensor | None = None
        self.gradients: torch.Tensor | None = None

        target = dict(model.named_modules()).get(layer_name)
        if target is None:
            raise ValueError(f"未找到用于 Grad-CAM 的层：{layer_name}")

        target.register_forward_hook(self._save_activation)
        target.register_full_backward_hook(self._save_gradient)

    def _save_activation(self, _module, _inputs, output):
        self.activations = output

    def _save_gradient(self, _module, _grad_input, grad_output):
        self.gradients = grad_output[0]

    def generate(self, x: torch.Tensor, class_idx: torch.Tensor | None = None,
                 rr: torch.Tensor | None = None) -> np.ndarray:
        """x: (B, 1, L) 已标准化心搏；class_idx: (B,) 目标类别，默认取预测类别。

        rr 为节律特征 (B, 4)。注意：Grad-CAM 解释的是**波形分支**，
        节律分支只参与前向计算提供上下文，不对其求显著性（它是 4 维特征，
        本身即具备可读性，无需热力图）。
        返回 (B, L) 的显著性曲线，逐样本归一化到 [0, 1]。
        """
        self.model.eval()
        self.model.zero_grad(set_to_none=True)

        x = x.clone().detach().requires_grad_(True)
        logits = self.model(x, rr)                   # (B, n_classes)

        if class_idx is None:
            class_idx = logits.argmax(dim=1)
        class_idx = class_idx.to(logits.device)

        target = logits.gather(1, class_idx.view(-1, 1)).sum()
        target.backward()

        if self.activations is None or self.gradients is None:
            raise RuntimeError("Grad-CAM 钩子未捕获到激活/梯度，请检查层名与模型前向路径")

        acts = self.activations.detach()             # (B, C, T)
        grads = self.gradients.detach()              # (B, C, T)

        weights = grads.mean(dim=2, keepdim=True)    # (B, C, 1)
        cam = F.relu((weights * acts).sum(dim=1))    # (B, T)

        # 上采样回原始信号长度，便于前端与波形对齐叠加
        cam = F.interpolate(
            cam.unsqueeze(1), size=x.shape[-1], mode="linear", align_corners=False
        ).squeeze(1)

        cam = cam.cpu().numpy()
        # 逐样本 min-max 归一化；若曲线恒为 0（无显著关注区域）则保持全 0
        lo = cam.min(axis=1, keepdims=True)
        hi = cam.max(axis=1, keepdims=True)
        span = np.where(hi - lo < 1e-8, 1.0, hi - lo)
        return ((cam - lo) / span).astype(np.float32)
