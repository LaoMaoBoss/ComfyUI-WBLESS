"""
WBLESS 遮罩应用节点

这个模块实现了遮罩应用功能，将遮罩作为透明度应用到输入图像上。
"""

import time
import numpy as np
import torch
from PIL import Image
from typing import Tuple, Dict, Any

from cozy_comfyui.node import CozyBaseNode


class MaskApplyNode(CozyBaseNode):
    """
    遮罩应用节点 - 将遮罩作为透明度应用到输入图像
    
    功能说明：
    - 接收输入图像和遮罩
    - 将遮罩作为透明度通道应用到图像上
    - 支持遮罩反转功能
    - 输出带有透明度的图像
    """
    
    NAME = "ApplyMaskToAlpha"
    
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                # 输入图像
                "image": ("IMAGE", {
                    "tooltip": "要应用遮罩的输入图像"
                }),
                
                # 输入遮罩
                "mask": ("MASK", {
                    "tooltip": "作为透明度使用的遮罩"
                }),
                
                # 反转遮罩选项
                "invert_mask": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false"
                }),
            },
            "optional": {
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "apply_mask"
    CATEGORY = f"🌈WBLESS"
    
    OUTPUT_NODE = False
    
    # 功能说明:
    # - image: 应用遮罩后的图像，包含透明度信息
    # - invert_mask: 反转遮罩（黑白颠倒）

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        """强制禁用缓存，确保每次都重新处理"""
        return time.time()

    def apply_mask(self, image, mask, invert_mask: bool) -> Tuple[torch.Tensor]:
        """将遮罩作为透明度应用到输入图像"""
        
        # 处理输入图像
        if isinstance(image, list):
            img_tensor = image[0]
        else:
            img_tensor = image
        
        # 处理输入遮罩
        if isinstance(mask, list):
            mask_tensor = mask[0]
        else:
            mask_tensor = mask
        
        # 处理反转遮罩参数
        if isinstance(invert_mask, list):
            invert_mask = invert_mask[0] if invert_mask else False
        
        # 获取图像尺寸
        if len(img_tensor.shape) == 4:
            img_tensor = img_tensor[0]  # 移除批次维度
            height, width = img_tensor.shape[:2]
        elif len(img_tensor.shape) == 3:
            height, width = img_tensor.shape[:2]
        else:
            raise ValueError(f"Unsupported image tensor shape: {img_tensor.shape}")
        
        # 确保张量在CPU上
        if img_tensor.device.type != 'cpu':
            img_tensor = img_tensor.cpu()
        if mask_tensor.device.type != 'cpu':
            mask_tensor = mask_tensor.cpu()
        
        # 处理遮罩维度
        if len(mask_tensor.shape) == 3:
            mask_tensor = mask_tensor[0]  # 移除批次维度
        
        # 将张量转换为numpy数组
        input_array = (img_tensor.numpy() * 255).astype(np.uint8)
        mask_array = (mask_tensor.numpy() * 255).astype(np.uint8)
        
        # 确保遮罩尺寸与图像匹配
        if mask_array.shape != (height, width):
            # 如果尺寸不匹配，调整遮罩大小
            mask_pil = Image.fromarray(mask_array, mode='L')
            mask_pil = mask_pil.resize((width, height), Image.Resampling.LANCZOS)
            mask_array = np.array(mask_pil)
        
        # 应用遮罩反转
        if invert_mask:
            mask_array = 255 - mask_array
        
        # 将输入图像转换为RGBA格式（如果需要）
        if input_array.shape[2] == 3:
            # RGB转RGBA，添加完全不透明的alpha通道
            alpha_channel = np.full((height, width, 1), 255, dtype=np.uint8)
            input_array = np.concatenate([input_array, alpha_channel], axis=2)
        
        # 创建输出数组
        output_array = input_array.copy()
        
        # 将遮罩应用为透明度通道
        output_array[:, :, 3] = mask_array
        
        # 转换为torch张量
        output_tensor = torch.from_numpy(output_array).float() / 255.0
        output_tensor = output_tensor.unsqueeze(0)  # 添加批次维度
        
        return (output_tensor,)
