"""
WBLESS 渐变工具节点

这个模块实现了强大的渐变生成功能，支持多种渐变类型和自定义参数。
"""

import time
import numpy as np
import torch
from PIL import Image, ImageDraw
import math
from typing import Tuple, List, Dict, Any

from cozy_comfyui.node import CozyBaseNode

# 颜色映射，参考 Text Block 节点的实现
COLOR_MAPPING = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "brown": (160, 85, 15),
    "gray": (128, 128, 128),
    "lightgray": (211, 211, 211),
    "darkgray": (102, 102, 102),
    "olive": (128, 128, 0),
    "lime": (0, 128, 0),
    "teal": (0, 128, 128),
    "navy": (0, 0, 128),
    "maroon": (128, 0, 0),
    "fuchsia": (255, 0, 128),
    "aqua": (0, 255, 128),
    "silver": (192, 192, 192),
    "gold": (255, 215, 0),
    "turquoise": (64, 224, 208),
    "lavender": (230, 230, 250),
    "violet": (238, 130, 238),
    "coral": (255, 127, 80),
    "indigo": (75, 0, 130),
    "custom": (255, 255, 255)  # 自定义颜色的占位符
}


class GradientNode(CozyBaseNode):
    """
    渐变工具节点 - 生成各种类型的渐变图像
    
    支持的渐变类型：
    - 线性渐变 (Linear)
    - 径向渐变 (Radial) 
    - 角度渐变 (Angular)
    - 菱形渐变 (Diamond)
    - 椭圆渐变 (Elliptical)
    
    输出说明：
    - image: 渐变与输入图像混合后的结果
    - mask: 基于渐变透明度的遮罩，可用于后处理
    
    反转选项：
    - invert_alpha: 反转透明度渐变（交换起始和结束透明度）
    - invert_colors: 反转渐变颜色（交换起始和结束颜色）
    """
    
    NAME = "Gradient"
    
    # 渐变类型选项
    GRADIENT_TYPES = [
        "linear",      # 线性渐变
        "radial",      # 径向渐变
        "angular",     # 角度渐变
        "diamond",     # 菱形渐变
        "elliptical"   # 椭圆渐变
    ]
    

    


    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        # 定义颜色选项，custom放在第一位
        COLORS = ["custom"] + [color for color in COLOR_MAPPING.keys() if color != "custom"]
        
        return {
            "required": {
                # 渐变类型
                "gradient_type": (cls.GRADIENT_TYPES, {
                    "default": "linear"
                }),
                
                # 旋转角度（度）
                "rotation_angle": ("FLOAT", {
                    "default": 0.0,
                    "min": -360.0,
                    "max": 360.0,
                    "step": 1.0,
                    "display": "number"
                }),
                
                # 渐变位置设置
                "start_position": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "display": "number"
                }),
                "end_position": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "display": "number"
                }),
                "center_position": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "display": "number"
                }),
                
                # 起始颜色参数
                "start_color": (COLORS, {"default": "custom"}),
                "start_color_hex": ("STRING", {
                    "default": "#000000",
                    "multiline": False
                }),
                
                # 结束颜色参数
                "end_color": (COLORS, {"default": "custom"}),
                "end_color_hex": ("STRING", {
                    "default": "#FFFFFF", 
                    "multiline": False
                }),
                
                # 透明度参数
                "start_alpha": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "display": "number"
                }),
                "end_alpha": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "display": "number"
                }),
                
                # 输入图像，用于获取尺寸
                "image": ("IMAGE", {}),
                
                # 反转选项
                "invert_alpha": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false"
                }),
                "invert_colors": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false"
                }),
            },
            "optional": {
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "generate_gradient"
    CATEGORY = f"🌈WBLESS"
    
    OUTPUT_NODE = False
    
    # 输出说明:
    # - image: 渐变与输入图像混合后的结果
    # - mask: 基于渐变透明度的遮罩
    # 反转选项:
    # - invert_alpha: 反转透明度渐变（交换起始和结束透明度）
    # - invert_colors: 反转渐变颜色（交换起始和结束颜色）

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        """强制禁用缓存，确保每次都重新生成渐变"""
        return time.time()

    def hex_to_rgb(self, hex_color) -> Tuple[int, int, int]:
        """将十六进制颜色转换为RGB"""
        # 处理列表格式的输入
        if isinstance(hex_color, list):
            hex_color = hex_color[0] if hex_color else "#000000"
        
        # 确保是字符串类型
        if not isinstance(hex_color, str):
            hex_color = str(hex_color)
            
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            # 默认颜色
            return (0, 0, 0)
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    def get_color_values(self, color_name, color_hex) -> Tuple[int, int, int]:
        """获取颜色的RGB值，支持预设颜色和自定义十六进制颜色"""
        # 处理可能的列表类型输入
        if isinstance(color_name, list):
            color_name = color_name[0] if color_name else "black"
        if isinstance(color_hex, list):
            color_hex = color_hex[0] if color_hex else "#000000"
        
        if color_name == "custom":
            return self.hex_to_rgb(color_hex)
        else:
            return COLOR_MAPPING.get(color_name, (0, 0, 0))  # 默认为黑色



    def interpolate_color(self, color1: Tuple[int, int, int], alpha1: float, 
                         color2: Tuple[int, int, int], alpha2: float, 
                         t: float) -> Tuple[int, int, int, int]:
        """在两种颜色之间进行RGBA线性插值"""
        r = int(color1[0] * (1 - t) + color2[0] * t)
        g = int(color1[1] * (1 - t) + color2[1] * t)
        b = int(color1[2] * (1 - t) + color2[2] * t)
        a = int((alpha1 * (1 - t) + alpha2 * t) * 255)
        return (r, g, b, a)



    def get_gradient_value(self, x: int, y: int, width: int, height: int, 
                          gradient_type: str, rotation_angle: float, 
                          start_position: float, end_position: float, center_position: float) -> float:
        """计算指定位置的渐变值（0-1）"""
        
        if gradient_type == "linear":
            # 线性渐变 - 类似PS的渐变工具
            angle_rad = math.radians(rotation_angle)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            
            # 图像中心点
            img_cx, img_cy = width / 2, height / 2
            
            # 将坐标转换到图像中心为原点的系统
            dx, dy = x - img_cx, y - img_cy
            
            # 投影到渐变方向
            projection = dx * cos_a + dy * sin_a
            
            # 根据角度确定主要方向的尺寸
            # 0度=水平，90度=垂直
            angle_normalized = abs(rotation_angle % 180)
            if angle_normalized <= 45 or angle_normalized >= 135:
                # 主要是水平方向
                main_dimension = width
            else:
                # 主要是垂直方向
                main_dimension = height
            
            # 计算起始和结束的实际位置
            half_dim = main_dimension / 2
            start_pos = (start_position - 0.5) * main_dimension
            end_pos = (end_position - 0.5) * main_dimension
            
            # 计算在起始和结束位置之间的比例
            if abs(end_pos - start_pos) < 1e-6:
                # 避免除零
                raw_t = 0.5
            else:
                raw_t = (projection - start_pos) / (end_pos - start_pos)
            
            # 应用中心点偏移（类似PS中的中间拉杆）
            if center_position != 0.5:
                if raw_t <= center_position:
                    # 在中心点左侧，压缩到0-0.5
                    if center_position > 0:
                        t = (raw_t / center_position) * 0.5
                    else:
                        t = 0.0
                else:
                    # 在中心点右侧，压缩到0.5-1.0
                    if center_position < 1.0:
                        t = 0.5 + ((raw_t - center_position) / (1.0 - center_position)) * 0.5
                    else:
                        t = 1.0
            else:
                t = raw_t
        
        elif gradient_type == "radial":
            # 径向渐变 - 从图像中心向外
            img_cx, img_cy = width / 2, height / 2
            max_radius = math.sqrt(width**2 + height**2) / 2
            distance = math.sqrt((x - img_cx)**2 + (y - img_cy)**2)
            
            # 应用起始和结束位置
            start_radius = start_position * max_radius
            end_radius = end_position * max_radius
            
            if abs(end_radius - start_radius) < 1e-6:
                raw_t = 0.5
            else:
                raw_t = (distance - start_radius) / (end_radius - start_radius)
            
            # 应用中心点偏移
            if center_position != 0.5:
                if raw_t <= center_position:
                    if center_position > 0:
                        t = (raw_t / center_position) * 0.5
                    else:
                        t = 0.0
                else:
                    if center_position < 1.0:
                        t = 0.5 + ((raw_t - center_position) / (1.0 - center_position)) * 0.5
                    else:
                        t = 1.0
            else:
                t = raw_t
        
        elif gradient_type == "angular":
            # 角度渐变 - 围绕图像中心
            img_cx, img_cy = width / 2, height / 2
            angle = math.atan2(y - img_cy, x - img_cx)
            raw_t = (angle + math.pi) / (2 * math.pi)
            
            # 角度渐变的起始和结束位置表示角度范围
            start_angle = start_position * 2 * math.pi
            end_angle = end_position * 2 * math.pi
            current_angle = raw_t * 2 * math.pi
            
            if abs(end_angle - start_angle) < 1e-6:
                raw_t = 0.5
            else:
                raw_t = (current_angle - start_angle) / (end_angle - start_angle)
            
            # 应用中心点偏移
            if center_position != 0.5:
                if raw_t <= center_position:
                    if center_position > 0:
                        t = (raw_t / center_position) * 0.5
                    else:
                        t = 0.0
                else:
                    if center_position < 1.0:
                        t = 0.5 + ((raw_t - center_position) / (1.0 - center_position)) * 0.5
                    else:
                        t = 1.0
            else:
                t = raw_t
        
        elif gradient_type == "diamond":
            # 菱形渐变 - 从图像中心
            img_cx, img_cy = width / 2, height / 2
            dx = abs(x - img_cx) / (width / 2)
            dy = abs(y - img_cy) / (height / 2)
            raw_t = max(dx, dy)
            
            # 应用起始和结束位置
            if abs(end_position - start_position) < 1e-6:
                raw_t = 0.5
            else:
                raw_t = (raw_t - start_position) / (end_position - start_position)
            
            # 应用中心点偏移
            if center_position != 0.5:
                if raw_t <= center_position:
                    if center_position > 0:
                        t = (raw_t / center_position) * 0.5
                    else:
                        t = 0.0
                else:
                    if center_position < 1.0:
                        t = 0.5 + ((raw_t - center_position) / (1.0 - center_position)) * 0.5
                    else:
                        t = 1.0
            else:
                t = raw_t
        
        elif gradient_type == "elliptical":
            # 椭圆渐变 - 从图像中心
            img_cx, img_cy = width / 2, height / 2
            dx = (x - img_cx) / (width / 2)
            dy = (y - img_cy) / (height / 2)
            raw_t = math.sqrt(dx**2 + dy**2)
            
            # 应用起始和结束位置
            if abs(end_position - start_position) < 1e-6:
                raw_t = 0.5
            else:
                raw_t = (raw_t - start_position) / (end_position - start_position)
            
            # 应用中心点偏移
            if center_position != 0.5:
                if raw_t <= center_position:
                    if center_position > 0:
                        t = (raw_t / center_position) * 0.5
                    else:
                        t = 0.0
                else:
                    if center_position < 1.0:
                        t = 0.5 + ((raw_t - center_position) / (1.0 - center_position)) * 0.5
                    else:
                        t = 1.0
            else:
                t = raw_t
        
        else:
            t = 0.0
        
        # 限制在[0, 1]范围内
        return max(0.0, min(1.0, t))

    def generate_gradient(self, gradient_type: str, rotation_angle: float, 
                         start_position: float, end_position: float, center_position: float,
                         start_color: str, start_color_hex: str, end_color: str, end_color_hex: str,
                         start_alpha: float, end_alpha: float, image, 
                         invert_alpha: bool, invert_colors: bool) -> Tuple[torch.Tensor, torch.Tensor]:
        """生成渐变图像，支持透明度和颜色反转"""
        
        # 从输入图像获取尺寸
        if isinstance(image, list):
            # 如果是列表，取第一个元素
            img_tensor = image[0]
        else:
            img_tensor = image
        
        # 处理不同的张量形状
        if len(img_tensor.shape) == 4:
            # 形状: (batch, height, width, channels)
            img_tensor = img_tensor[0]  # 取第一个批次
            height, width = img_tensor.shape[:2]
        elif len(img_tensor.shape) == 3:
            # 形状: (height, width, channels)
            height, width = img_tensor.shape[:2]
        else:
            raise ValueError(f"Unsupported image tensor shape: {img_tensor.shape}")
        
        # 处理可能是列表格式的参数
        if isinstance(start_alpha, list):
            start_alpha = start_alpha[0] if start_alpha else 1.0
        if isinstance(end_alpha, list):
            end_alpha = end_alpha[0] if end_alpha else 1.0
        if isinstance(gradient_type, list):
            gradient_type = gradient_type[0] if gradient_type else "linear"
        if isinstance(rotation_angle, list):
            rotation_angle = rotation_angle[0] if rotation_angle else 0.0
        if isinstance(start_position, list):
            start_position = start_position[0] if start_position else 0.0
        if isinstance(end_position, list):
            end_position = end_position[0] if end_position else 1.0
        if isinstance(center_position, list):
            center_position = center_position[0] if center_position else 0.5
        if isinstance(invert_alpha, list):
            invert_alpha = invert_alpha[0] if invert_alpha else False
        if isinstance(invert_colors, list):
            invert_colors = invert_colors[0] if invert_colors else False
        
        # 解析颜色
        start_rgb = self.get_color_values(start_color, start_color_hex)
        end_rgb = self.get_color_values(end_color, end_color_hex)
        
        # 应用颜色反转 - 交换起始和结束颜色
        if invert_colors:
            start_rgb, end_rgb = end_rgb, start_rgb
        
        # 应用透明度反转 - 交换起始和结束透明度
        if invert_alpha:
            start_alpha, end_alpha = end_alpha, start_alpha
        
        # 将输入图像转换为numpy数组
        # 确保张量在CPU上并且形状正确
        if img_tensor.device.type != 'cpu':
            img_tensor = img_tensor.cpu()
        
        # 确保张量是3维的 (height, width, channels)
        if len(img_tensor.shape) == 4:
            img_tensor = img_tensor[0]  # 移除批次维度
        
        input_array = (img_tensor.numpy() * 255).astype(np.uint8)
        
        # 创建渐变遮罩数组 - 使用RGBA格式
        gradient_array = np.zeros((height, width, 4), dtype=np.uint8)
        
        # 生成渐变
        for y in range(height):
            for x in range(width):
                # 获取渐变值
                t = self.get_gradient_value(
                    x, y, width, height, gradient_type, rotation_angle, 
                    start_position, end_position, center_position
                )
                
                # 计算颜色 - 使用完整的RGBA渐变
                color = self.interpolate_color(start_rgb, start_alpha, end_rgb, end_alpha, t)
                gradient_array[y, x] = color
        
        # 将输入图像转换为RGBA格式（如果需要）
        if input_array.shape[2] == 3:
            # RGB转RGBA，添加完全不透明的alpha通道
            alpha_channel = np.full((height, width, 1), 255, dtype=np.uint8)
            input_array = np.concatenate([input_array, alpha_channel], axis=2)
        
        # 执行alpha混合：将渐变叠加到输入图像上
        # 使用标准的alpha混合公式：result = foreground * alpha + background * (1 - alpha)
        gradient_alpha = gradient_array[:, :, 3:4] / 255.0  # 渐变的alpha通道
        input_alpha = input_array[:, :, 3:4] / 255.0        # 输入图像的alpha通道
        
        # 计算最终的颜色
        blended_rgb = (gradient_array[:, :, :3] * gradient_alpha + 
                      input_array[:, :, :3] * (1 - gradient_alpha))
        
        # 计算最终的alpha通道
        blended_alpha = gradient_alpha + input_alpha * (1 - gradient_alpha)
        
        # 合并RGB和Alpha
        final_array = np.concatenate([blended_rgb, blended_alpha * 255], axis=2).astype(np.uint8)
        
        # 转换为torch张量
        image_tensor = torch.from_numpy(final_array).float() / 255.0
        image_tensor = image_tensor.unsqueeze(0)  # 添加批次维度
        
        # 生成遮罩 - 基于渐变的透明度
        # 提取渐变的alpha通道作为遮罩
        mask_array = gradient_array[:, :, 3]  # 只取alpha通道
        mask_tensor = torch.from_numpy(mask_array).float() / 255.0
        mask_tensor = mask_tensor.unsqueeze(0)  # 添加批次维度
        
        return (image_tensor, mask_tensor)



