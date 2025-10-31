"""
图像遮罩混合节点
Image Mask Blend Node
"""

import torch
import copy
import numpy as np
from PIL import Image, ImageDraw
from cozy_comfyui.node import CozyBaseNode
from .util.blendmodes import BLEND_MODES

# ==================== 工具函数 ====================

def log(message: str, message_type: str = 'info'):
    """
    日志输出函数
    
    参数:
        message: 日志消息
        message_type: 消息类型 (info/warning/error/finish)
    """
    name = 'WBLESS'
    
    if message_type == 'error':
        message = '\033[1;41m' + message + '\033[m'
    elif message_type == 'warning':
        message = '\033[1;31m' + message + '\033[m'
    elif message_type == 'finish':
        message = '\033[1;32m' + message + '\033[m'
    else:
        message = '\033[1;33m' + message + '\033[m'
    print(f"# WBLESS: {name} -> {message}")


def pil2tensor(image: Image) -> torch.Tensor:
    """
    将PIL图像转换为PyTorch张量
    
    参数:
        image: PIL图像对象
    返回:
        PyTorch张量，形状为[1, H, W, C]，值范围[0, 1]
    """
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)


def tensor2pil(t_image: torch.Tensor) -> Image:
    """
    将PyTorch张量转换为PIL图像
    
    参数:
        t_image: PyTorch张量
    返回:
        PIL图像对象
    """
    return Image.fromarray(np.clip(255.0 * t_image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))


def image2mask(image: Image) -> torch.Tensor:
    """
    将PIL图像转换为遮罩张量
    
    参数:
        image: PIL图像对象
    返回:
        遮罩张量，形状为[1, H, W]
    """
    if image.mode == 'L':
        return torch.tensor([pil2tensor(image)[0, :, :].tolist()])
    else:
        image = image.convert('RGB').split()[0]
        return torch.tensor([pil2tensor(image)[0, :, :].tolist()])


def get_mask_bounds(mask: Image) -> tuple:
    """
    获取遮罩的边界框
    
    参数:
        mask: PIL灰度遮罩图像
    返回:
        (x, y, width, height) - 遮罩内容的边界框，如果遮罩为空则返回 (0, 0, 0, 0)
    """
    # 转换为numpy数组
    mask_array = np.array(mask)
    
    # 找到非零像素（考虑到可能是软遮罩，使用阈值）
    threshold = 1  # 大于1的值被认为是有效的
    coords = np.argwhere(mask_array > threshold)
    
    if coords.size == 0:
        # 遮罩为空
        return (0, 0, 0, 0)
    
    # 获取边界框
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    
    # 计算宽度和高度
    width = x_max - x_min + 1
    height = y_max - y_min + 1
    
    return (int(x_min), int(y_min), int(width), int(height))


def RGB2RGBA(image: Image, mask: Image) -> Image:
    """
    将RGB图像和遮罩合并为RGBA图像
    
    参数:
        image: RGB图像
        mask: 灰度遮罩
    返回:
        RGBA图像
    """
    (R, G, B) = image.convert('RGB').split()
    return Image.merge('RGBA', (R, G, B, mask.convert('L')))


def chop_image_v2(background_image: Image, layer_image: Image, blend_mode: str, opacity: int) -> Image:
    """
    应用混合模式将图层合成到背景图像上
    
    参数:
        background_image: 背景图像
        layer_image: 图层图像
        blend_mode: 混合模式名称
        opacity: 不透明度 (0-100)
    返回:
        混合后的图像
    """
    backdrop_prepped = np.asarray(background_image.convert('RGBA'), dtype=float)
    source_prepped = np.asarray(layer_image.convert('RGBA'), dtype=float)
    blended_np = BLEND_MODES[blend_mode](backdrop_prepped, source_prepped, opacity / 100)
    
    return Image.fromarray(np.uint8(blended_np)).convert('RGB')


def __rotate_expand(image: Image, angle: float, SSAA: int = 0, method: str = "lanczos") -> Image:
    """
    旋转图像并扩展画布以适应
    支持超采样抗锯齿(SSAA)
    
    参数:
        image: 输入图像
        angle: 旋转角度
        SSAA: 超采样倍数，0表示禁用
        method: 重采样方法
    返回:
        旋转后的图像
    """
    images = pil2tensor(image)
    height, width = images[0, :, :, 0].shape

    def rotate_tensor(tensor):
        # 根据方法选择重采样算法
        resize_sampler = Image.LANCZOS
        rotate_sampler = Image.BICUBIC
        if method == "bicubic":
            resize_sampler = Image.BICUBIC
            rotate_sampler = Image.BICUBIC
        elif method == "hamming":
            resize_sampler = Image.HAMMING
            rotate_sampler = Image.BILINEAR
        elif method == "bilinear":
            resize_sampler = Image.BILINEAR
            rotate_sampler = Image.BILINEAR
        elif method == "box":
            resize_sampler = Image.BOX
            rotate_sampler = Image.NEAREST
        elif method == "nearest":
            resize_sampler = Image.NEAREST
            rotate_sampler = Image.NEAREST
        
        img = tensor2pil(tensor)
        
        # 应用超采样抗锯齿
        if SSAA > 1:
            img_us_scaled = img.resize((width * SSAA, height * SSAA), resize_sampler)
            img_rotated = img_us_scaled.rotate(angle, rotate_sampler, expand=True, fillcolor=(0, 0, 0, 0))
            img_down_scaled = img_rotated.resize((img_rotated.width // SSAA, img_rotated.height // SSAA), resize_sampler)
            result = pil2tensor(img_down_scaled)
        else:
            img_rotated = img.rotate(angle, rotate_sampler, expand=True, fillcolor=(0, 0, 0, 0))
            result = pil2tensor(img_rotated)
        return result

    # 如果角度为0或360度，直接返回原图
    if angle == 0.0 or angle == 360.0:
        return tensor2pil(images)
    else:
        rotated_tensor = torch.stack([rotate_tensor(images[i]) for i in range(len(images))])
        return tensor2pil(rotated_tensor).convert('RGB')


def image_rotate_extend_with_alpha(image: Image, angle: float, alpha: Image = None, method: str = "lanczos", SSAA: int = 0) -> tuple:
    """
    旋转图像和Alpha通道
    
    参数:
        image: 输入图像
        angle: 旋转角度
        alpha: Alpha通道图像
        method: 重采样方法
        SSAA: 超采样倍数
    返回:
        (旋转后的RGB图像, 旋转后的Alpha通道, 旋转后的RGBA图像)
    """
    _image = __rotate_expand(image.convert('RGB'), angle, SSAA, method)
    if alpha is not None:
        _alpha = __rotate_expand(alpha.convert('RGB'), angle, SSAA, method)
        ret_image = RGB2RGBA(_image, _alpha)
    else:
        ret_image = _image
        _alpha = Image.new('L', _image.size, 255)
    return (_image, _alpha.convert('L'), ret_image)


# 从BLEND_MODES字典生成可用的混合模式列表
chop_mode_v2 = list(BLEND_MODES.keys())

# ==================== 节点类 ====================

class ImageMaskBlend(CozyBaseNode):
    """
    图像遮罩混合节点（简化版）
    
    核心功能：
    - 使用 mask 的边界框来确定 layer_image 的缩放目标尺寸和位置
    - 将 layer_image 自动缩放到 mask 边界框的大小（Cover模式）
    - 保持 layer_image 的原始纵横比不变
    - 确保 layer_image 完全覆盖 mask 边界框区域（可以大于但不能小于）
    - 将缩放后的完整图像混合到背景上（不使用mask形状裁剪）
    
    缩放模式（Cover模式）：
    - 保持 layer_image 的原始宽高比
    - 计算能够完全覆盖 mask 边界框的最小缩放比例
    - 如果比例不一致，允许超出 mask 边界框
    - 确保 layer_image 的任何一边都不会小于 mask 边界框
    
    主要特性：
    - 支持 30+ 种 Photoshop 风格的混合模式
    - 自动根据 mask 边界框定位和缩放
    - 智能居中对齐
    - 额外缩放控制
    - 批处理支持
    
    参数说明：
    - layer_mask: 必需，用于确定混合区域的位置和大小
    - blend_mode: 混合模式（normal, multiply, screen等）
    - scale: 在自动计算的基础上额外缩放（1.0 = 刚好覆盖mask边界框）
    - x_percent/y_percent: 相对于 mask 边界框中心的偏移百分比（50 = 居中对齐）
    - transform_method: 重采样方法（lanczos, bicubic等）
    """
    
    NAME = "Image Mask Blend"

    @classmethod
    def INPUT_TYPES(cls):
        method_mode = ['lanczos', 'bicubic', 'hamming', 'bilinear', 'box', 'nearest']
        
        return {
            "required": {
                "background_image": ("IMAGE", ),  # 背景图像（目标画布）
                "layer_image": ("IMAGE",),  # 图层图像（将被缩放到mask大小）
                "layer_mask": ("MASK",),  # 遮罩（定义混合区域的位置和大小）
                "blend_mode": (chop_mode_v2,),  # 混合模式（30+种Photoshop风格）
                "x_percent": ("FLOAT", {"default": 50, "min": -999, "max": 999, "step": 0.01}),  # X偏移百分比 (50=居中)
                "y_percent": ("FLOAT", {"default": 50, "min": -999, "max": 999, "step": 0.01}),  # Y偏移百分比 (50=居中)
                "scale": ("FLOAT", {"default": 1, "min": 0.01, "max": 100, "step": 0.01}),  # 额外缩放倍数 (1.0=mask大小)
                "transform_method": (method_mode,),  # 重采样方法
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = 'blend_images'
    CATEGORY = f"🌈WBLESS"

    def blend_images(self, background_image, layer_image, layer_mask,
                    blend_mode, x_percent, y_percent,
                    scale, transform_method
                    ):
        """
        执行基于遮罩边界框的图像混合操作（简化版，Cover模式缩放）
        
        处理流程:
        1. 批处理准备：将输入图像分离为独立批次
        2. 遮罩分析：获取遮罩并计算其边界框
        3. 智能缩放（Cover模式）：
           - 保持 layer_image 的原始纵横比
           - 计算能够完全覆盖 mask 边界框的最小缩放比例
           - 确保 layer_image 不会小于 mask 边界框（任何一边）
        4. 精确定位：居中对齐到 mask 边界框并应用偏移调整
        5. 混合合成：使用指定混合模式将完整的矩形区域混合到背景上（100%不透明度）
        6. 输出结果：返回混合后的图像
        
        核心特性：
        - mask 仅用于确定位置和大小，不用于形状裁剪
        - layer_image 保持原始纵横比，自动适配 mask 边界框大小
        - 使用 Cover 模式确保完全覆盖（类似 CSS object-fit: cover）
        - 输出完整的矩形混合区域
        - 固定100%不透明度
        - scale 参数控制额外缩放倍数（1.0 = 刚好覆盖）
        - x_percent/y_percent 控制偏移（50 = 居中对齐）
        - 支持 30+ 种 Photoshop 风格的混合模式
        """
        # CozyBaseNode 可能以列表形式传递标量参数，需要先提取
        if isinstance(blend_mode, list):
            blend_mode = blend_mode[0] if blend_mode else "normal"
        if isinstance(x_percent, list):
            x_percent = x_percent[0] if x_percent else 50
        if isinstance(y_percent, list):
            y_percent = y_percent[0] if y_percent else 50
        if isinstance(scale, list):
            scale = scale[0] if scale else 1
        if isinstance(transform_method, list):
            transform_method = transform_method[0] if transform_method else 'lanczos'
        
        b_images = []
        l_images = []
        l_masks = []
        ret_images = []
        
        # 分离批次中的每个背景图像
        for b in background_image:
            b_images.append(torch.unsqueeze(b, 0))
        
        # 分离批次中的每个图层图像
        for l in layer_image:
            l_images.append(torch.unsqueeze(l, 0))
        
        # 处理遮罩输入
        if isinstance(layer_mask, list):
            if len(layer_mask) > 0:
                layer_mask = layer_mask[0]
            else:
                raise ValueError("layer_mask is empty")
        
        # 确保遮罩有正确的维度
        if layer_mask.dim() == 2:
            layer_mask = torch.unsqueeze(layer_mask, 0)
        
        # 转换遮罩为PIL图像
        for m in layer_mask:
            l_masks.append(tensor2pil(torch.unsqueeze(m, 0)).convert('L'))

        # 确定最大批次大小，用于批处理
        max_batch = max(len(b_images), len(l_images), len(l_masks))
        
        # 处理每个批次
        for i in range(max_batch):
            # 如果某个列表元素不足，使用最后一个元素
            background_image = b_images[i] if i < len(b_images) else b_images[-1]
            layer_image = l_images[i] if i < len(l_images) else l_images[-1]
            _mask = l_masks[i] if i < len(l_masks) else l_masks[-1]
            
            # 预处理：转换为PIL图像
            _canvas = tensor2pil(background_image).convert('RGB')
            _layer = tensor2pil(layer_image).convert('RGB')
            
            # 确保遮罩是灰度图像
            if _mask.mode != 'L':
                _mask = _mask.convert('L')
            
            # 确保遮罩尺寸与背景图像匹配
            if _mask.size != _canvas.size:
                log(f"Info: {self.__class__.NAME} resizing mask from {_mask.size} to {_canvas.size}", message_type='info')
                _mask = _mask.resize(_canvas.size, Image.LANCZOS)

            # ===== 新逻辑：根据 mask 的边界框来缩放和定位 layer_image =====
            
            # 1. 获取 mask 的边界框
            mask_x, mask_y, mask_width, mask_height = get_mask_bounds(_mask)
            
            # 检查 mask 是否为空
            if mask_width == 0 or mask_height == 0:
                log(f"Warning: {self.__class__.NAME} mask is empty, skipping!", message_type='warning')
                # 如果 mask 为空，直接返回原始背景
                ret_images.append(pil2tensor(_canvas))
                continue
            
            # 2. 计算目标尺寸 - 使用"cover"模式缩放
            # 保持 layer_image 的原始纵横比，确保完全覆盖 mask 区域
            
            # 获取 layer_image 的原始尺寸
            layer_width = _layer.width
            layer_height = _layer.height
            
            # 计算 mask 的目标尺寸（考虑 scale 参数）
            target_mask_width = mask_width * scale
            target_mask_height = mask_height * scale
            
            # 计算需要的缩放比例，使用"cover"模式
            # 确保 layer_image 至少覆盖整个 mask 区域（可以大于但不能小于）
            scale_x = target_mask_width / layer_width
            scale_y = target_mask_height / layer_height
            
            # 使用较大的缩放比例，确保完全覆盖
            cover_scale = max(scale_x, scale_y)
            
            # 计算最终尺寸（保持 layer_image 的纵横比）
            final_width = int(layer_width * cover_scale)
            final_height = int(layer_height * cover_scale)
            
            # 3. 缩放 layer_image 到计算出的尺寸
            # 使用高质量的重采样方法
            resample_methods = {
                'lanczos': Image.LANCZOS,
                'bicubic': Image.BICUBIC,
                'hamming': Image.HAMMING,
                'bilinear': Image.BILINEAR,
                'box': Image.BOX,
                'nearest': Image.NEAREST
            }
            resample = resample_methods.get(transform_method, Image.LANCZOS)
            _layer_scaled = _layer.resize((final_width, final_height), resample)
            
            # 4. 计算放置位置
            # 由于使用了"cover"模式，_layer_scaled 可能比 mask 大
            # 需要居中对齐，使 layer_image 覆盖整个 mask 区域
            
            # 计算居中对齐时的偏移（如果 layer 大于 mask，会有负偏移）
            center_offset_x = (int(target_mask_width) - _layer_scaled.width) // 2
            center_offset_y = (int(target_mask_height) - _layer_scaled.height) // 2
            
            # 应用用户指定的百分比偏移（相对于mask尺寸）
            user_offset_x = int((x_percent - 50) / 100 * mask_width)
            user_offset_y = int((y_percent - 50) / 100 * mask_height)
            
            # 最终位置 = mask位置 + 居中偏移 + 用户偏移
            final_x = mask_x + center_offset_x + user_offset_x
            final_y = mask_y + center_offset_y + user_offset_y
            
            # 6. 计算实际可见的区域（处理负坐标和超出边界的情况）
            visible_x1 = max(0, final_x)
            visible_y1 = max(0, final_y)
            visible_x2 = min(_canvas.width, final_x + _layer_scaled.width)
            visible_y2 = min(_canvas.height, final_y + _layer_scaled.height)
            
            # 如果图像完全超出画布范围，跳过
            if visible_x1 >= visible_x2 or visible_y1 >= visible_y2:
                log(f"Warning: {self.__class__.NAME} layer is completely outside canvas, skipping!", message_type='warning')
                ret_images.append(pil2tensor(_canvas))
                continue
            
            # 7. 计算图像在画布上的裁剪区域
            # 如果 final_x/y 为负，需要裁剪 _layer_scaled 的起始部分
            crop_x = max(0, -final_x)
            crop_y = max(0, -final_y)
            crop_width = visible_x2 - visible_x1
            crop_height = visible_y2 - visible_y1
            
            # 裁剪出实际要显示的图像部分
            _layer_cropped = _layer_scaled.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
            
            # 8. 提取对应的背景区域
            background_region = _canvas.crop((visible_x1, visible_y1, visible_x2, visible_y2))
            
            # 9. 创建与裁剪区域相同大小的图层用于混合
            layer_for_blend = Image.new("RGB", (crop_width, crop_height))
            layer_for_blend.paste(_layer_cropped, (0, 0))
            
            # 10. 应用混合模式到裁剪区域
            blended_region = chop_image_v2(background_region, layer_for_blend, blend_mode, 100)
            
            # 11. 将混合后的区域粘贴回画布
            _canvas.paste(blended_region, (visible_x1, visible_y1))
            
            # 添加到结果列表
            ret_images.append(pil2tensor(_canvas))

        log(f"{self.__class__.NAME} Processed {len(ret_images)} image(s).", message_type='finish')
        return (torch.cat(ret_images, dim=0),)

