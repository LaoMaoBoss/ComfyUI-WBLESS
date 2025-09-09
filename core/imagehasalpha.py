"""
WBLESS 图像透明通道检测节点

这个模块实现了图像透明通道检测功能，用于检测输入图像是否包含透明通道（Alpha通道）。
"""

import time
import torch
from typing import Tuple, Dict, Any

from cozy_comfyui.node import CozyBaseNode


class ImageHasAlphaNode(CozyBaseNode):
    """
    图像透明通道检测节点 - 检测图像是否包含透明通道
    
    功能说明：
    - 接收输入图像
    - 检测图像是否包含透明通道（Alpha通道）
    - 输出布尔值结果：True表示有透明通道，False表示无透明通道
    - 支持批量图像处理，返回第一张图像的检测结果
    """
    
    NAME = "ImageHasAlpha"
    
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                # 输入图像
                "image": ("IMAGE", {
                    "tooltip": "要检测透明通道的输入图像"
                }),
            },
            "optional": {}
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("has_alpha",)
    FUNCTION = "check_alpha"
    CATEGORY = f"🌈WBLESS"
    
    OUTPUT_NODE = False
    
    # 功能说明:
    # - has_alpha: 布尔值，表示图像是否包含透明通道

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        """强制禁用缓存，确保每次都重新检测"""
        return time.time()

    def check_alpha(self, image) -> Tuple[bool]:
        """检测图像是否包含透明通道"""
        
        # 处理输入图像
        if isinstance(image, list):
            img_tensor = image[0]
        else:
            img_tensor = image
        
        # 获取图像张量的形状
        # ComfyUI中的图像张量通常格式为 [batch, height, width, channels]
        if len(img_tensor.shape) == 4:
            # 批量图像，取第一张图像进行检测
            channels = img_tensor.shape[3]
        elif len(img_tensor.shape) == 3:
            # 单张图像
            channels = img_tensor.shape[2]
        else:
            raise ValueError(f"Unsupported image tensor shape: {img_tensor.shape}")
        
        # 检查通道数
        # 通道数为4表示包含Alpha通道（RGBA格式）
        # 通道数为3表示不包含Alpha通道（RGB格式）
        # 通道数为1表示灰度图（无Alpha通道）
        has_alpha = channels == 4
        
        # 如果有4个通道，进一步检查Alpha通道是否真的包含透明信息
        if has_alpha:
            # 提取Alpha通道
            if len(img_tensor.shape) == 4:
                alpha_channel = img_tensor[0, :, :, 3]  # 取第一张图像的Alpha通道
            else:
                alpha_channel = img_tensor[:, :, 3]
            
            # 检查Alpha通道是否包含透明信息
            # 如果Alpha通道中有任何值小于1.0，说明有透明效果
            alpha_min = torch.min(alpha_channel)
            
            # 使用小的容差值来处理浮点数精度问题
            tolerance = 1e-6
            if alpha_min < (1.0 - tolerance):
                # Alpha通道包含小于1.0的值，确实有透明效果
                has_alpha = True
            else:
                # Alpha通道全为1.0，虽然有4个通道但没有实际透明效果
                has_alpha = False
        
        return (has_alpha,)
