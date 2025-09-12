import math
import torch
from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY

class AreaBasedScale(CozyBaseNode):
    """
    一个根据"面积"进行缩放的节点（基于尺寸输入）。
    - 最终输出的宽高比由输入A决定。
    - 最终输出的面积由输入B的面积和指定的比例（Ratio）共同决定。
    """
    NAME = "Area Based Scale"
    
    @classmethod
    def INPUT_TYPES(s):
        """
        定义节点的输入类型。
        - 两组宽高尺寸 (a 和 b) 作为计算的基准。
        - 一个比例滑块 (ratio) 用于控制最终面积与B面积的比例。
        """
        return {
            "required": {
                "width_a": (COZY_TYPE_ANY,),
                "height_a": (COZY_TYPE_ANY,),
                "width_b": (COZY_TYPE_ANY,),
                "height_b": (COZY_TYPE_ANY,),
                "ratio": ("FLOAT", {"default": 0.5, "min": 0.01, "max": 1.0, "step": 0.01}),
                "cap_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.01}),
                "enable_cap": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "FLOAT")
    RETURN_NAMES = ("width", "height", "scale_ratio")
    FUNCTION = "scale"
    
    def scale(self, width_a, height_a, width_b, height_b, ratio: float, enable_cap: bool, cap_threshold: float):
        """
        根据“面积缩放”逻辑计算最终尺寸。
        """
        # ComfyUI 的输入有时会以列表形式提供，即使只有一个项目。
        # 我们在这里处理这种情况，通过获取列表中的第一个元素。
        if isinstance(width_a, list) and width_a:
            width_a = width_a[0]
        if isinstance(height_a, list) and height_a:
            height_a = height_a[0]
        if isinstance(width_b, list) and width_b:
            width_b = width_b[0]
        if isinstance(height_b, list) and height_b:
            height_b = height_b[0]
        
        # 对 ratio 也进行同样的处理，因为它也可以作为输入端口连接
        if isinstance(ratio, list) and ratio:
            ratio = ratio[0]
        
        # 对新增的输入也进行同样的处理
        if isinstance(cap_threshold, list) and cap_threshold:
            cap_threshold = cap_threshold[0]
        if isinstance(enable_cap, list) and enable_cap:
            enable_cap = enable_cap[0]

        # --- 核心逻辑：基于面积的缩放 ---

        width_a_int, height_a_int = int(width_a), int(height_a)
        width_b_int, height_b_int = int(width_b), int(height_b)

        # 1. 如果 A 的尺寸无效（无法确定宽高比），则无法继续，返回零尺寸。
        if width_a_int <= 0 or height_a_int <= 0:
            return (0, 0, 1.0)

        # 2. 计算 A 的宽高比，这是输出尺寸必须保持的比例。
        aspect_ratio_a = width_a_int / height_a_int
        
        # 3. 计算 B 的面积。
        area_b = width_b_int * height_b_int
        
        # 4. 根据 B 的面积和输入的比例，计算出目标面积。
        target_area = area_b * ratio
        if target_area <= 0:
            return (0, 0, 1.0)

        # 5. 基于目标面积和 A 的宽高比，推导出最终的宽度和高度。
        #    - target_area = output_width * output_height
        #    - aspect_ratio_a = output_width / output_height
        #    - 推导 => output_height = sqrt(target_area / aspect_ratio_a)
        #    - 推导 => output_width = output_height * aspect_ratio_a
        output_height_float = math.sqrt(target_area / aspect_ratio_a)
        output_width_float = output_height_float * aspect_ratio_a

        # --- 可选功能：尺寸上限控制 ---
        if enable_cap:
            # 1. 计算基于 B 尺寸和阈值的上限。
            cap_width = width_b_int * cap_threshold
            cap_height = height_b_int * cap_threshold

            # 2. 检查是否有任何一个维度超过了上限。
            if output_width_float > cap_width or output_height_float > cap_height:
                # 3. 计算需要缩小的比例，以确保两个维度都不超过上限。
                #    我们取两个维度各自需要缩小的比例中，更小的那一个，
                #    这样可以保证等比缩放后，所有边都在限制内。
                width_scale_down_ratio = cap_width / output_width_float if output_width_float > 0 else 1.0
                height_scale_down_ratio = cap_height / output_height_float if output_height_float > 0 else 1.0
                
                final_downscale_ratio = min(width_scale_down_ratio, height_scale_down_ratio)
                
                # 4. 应用此缩小比例。
                output_width_float *= final_downscale_ratio
                output_height_float *= final_downscale_ratio

        # 6. 将计算结果四舍五入并转换为整数。
        output_width = int(round(output_width_float))
        output_height = int(round(output_height_float))

        # 7. 计算从 A 到输出尺寸的实际缩放比例，用于调试或信息展示。
        scale_ratio = 1.0
        if width_a_int > 0:
            scale_ratio = output_width_float / width_a_int
        elif height_a_int > 0:
            scale_ratio = output_height_float / height_a_int
        
        return (output_width, output_height, scale_ratio)


class AreaBasedScalePixel(CozyBaseNode):
    """
    一个根据"像素数量比例"计算缩放比例的节点。
    - 缩放image_alpha整个图像，使其实际图像（不透明像素）的像素量 = image总像素量 × ratio
    - scale_ratio表示image_alpha需要缩放的倍数（相对于原始image_alpha尺寸）
    
    计算逻辑：
    1. 计算image_alpha中不透明像素数量
    2. 计算目标不透明像素数量 = image总像素 × ratio
    3. 计算面积缩放比例 = 目标像素数量 / 当前不透明像素数量
    4. 计算线性缩放比例 = sqrt(面积缩放比例)
    5. scale_ratio = 线性缩放比例（即image_alpha需要缩放的倍数）
    6. 同时输出缩放后的image_alpha尺寸
    """
    NAME = "Area Based Scale (Pixel)"
    
    @classmethod
    def INPUT_TYPES(s):
        """
        定义节点的输入类型。
        - image_alpha: 带透明通道的图片，用于计算不透明像素数量
        - image: 用于计算总像素数量作为基准
        - ratio: 目标像素数量与image像素数量的比例
        """
        return {
            "required": {
                "image_alpha": ("IMAGE",),
                "image": ("IMAGE",),
                "ratio": ("FLOAT", {"default": 0.5, "min": 0.01, "max": 10.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("FLOAT", "INT", "INT")
    RETURN_NAMES = ("scale_ratio", "scaled_width", "scaled_height")
    FUNCTION = "scale"
    
    def scale(self, image_alpha, image, ratio: float):
        """
        根据新的"像素数量比例"逻辑计算缩放比例。
        
        新逻辑：
        1. 计算image_alpha中不透明像素数量
        2. 计算目标不透明像素数量 = image总像素 × ratio
        3. 计算面积缩放比例，使image_alpha缩放后的不透明像素数量达到目标
        4. 根据面积缩放比例计算image_alpha的新尺寸
        5. scale_ratio = 缩放后的image_alpha尺寸 / 原始image_alpha尺寸（线性缩放比例）
        """
        # 处理可能的列表类型参数
        if isinstance(ratio, list) and ratio:
            ratio = ratio[0]
        
        # 处理可能的列表类型输入数据
        if isinstance(image, list) and image:
            image = image[0]
        if isinstance(image_alpha, list) and image_alpha:
            image_alpha = image_alpha[0]

        # --- 核心逻辑：基于像素数量比例的缩放 ---
        
        # 获取image的尺寸并计算总像素数量
        if len(image.shape) == 4:  # [batch, height, width, channels]
            batch_size, image_height, image_width, channels = image.shape
        elif len(image.shape) == 3:  # [height, width, channels]
            image_height, image_width, channels = image.shape
        else:
            return (1.0, 0, 0)
            
        # 计算image的总像素数量
        image_total_pixels = image_width * image_height
        
        # 获取image_alpha的尺寸
        if len(image_alpha.shape) == 4:  # [batch, height, width, channels]
            alpha_data = image_alpha[0]  # 取第一个batch
            alpha_height, alpha_width = alpha_data.shape[0], alpha_data.shape[1]
        elif len(image_alpha.shape) == 3:  # [height, width, channels]
            alpha_data = image_alpha
            alpha_height, alpha_width = alpha_data.shape[0], alpha_data.shape[1]
        else:
            return (1.0, 0, 0)

        # 如果image的尺寸无效，返回默认值
        if image_total_pixels <= 0:
            return (1.0, alpha_width, alpha_height)
        
        # 将image_alpha转换为torch tensor以便计算
        if not isinstance(alpha_data, torch.Tensor):
            alpha_tensor = torch.tensor(alpha_data)
        else:
            alpha_tensor = alpha_data
            
        # 提取透明通道并计算不透明像素数量
        if alpha_tensor.shape[-1] >= 4:  # 有透明通道
            alpha_channel = alpha_tensor[:, :, 3]  # 透明通道
            opaque_pixels = torch.sum(alpha_channel > 0).item()
        else:
            # 如果没有透明通道，则所有像素都视为不透明
            opaque_pixels = alpha_tensor.shape[0] * alpha_tensor.shape[1]
        
        # 计算目标不透明像素数量：image总像素 × ratio
        target_opaque_pixels = image_total_pixels * ratio
        
        # 如果当前不透明像素数量为0，避免除零错误
        if opaque_pixels <= 0:
            return (1.0, alpha_width, alpha_height)
        
        # 计算需要的面积缩放比例：要使不透明像素数量从当前值变为目标值
        # 面积缩放比例 = 目标像素数量 / 当前不透明像素数量
        area_scale_ratio = target_opaque_pixels / opaque_pixels
        
        # 计算线性缩放比例（面积缩放比例的平方根）
        # 因为面积 = 宽 × 高，所以线性缩放 = sqrt(面积缩放)
        linear_scale_ratio = math.sqrt(area_scale_ratio)
        
        # 计算image_alpha缩放后的新整体尺寸（注意：这是整个图像的尺寸，不仅仅是不透明部分）
        scaled_alpha_width = alpha_width * linear_scale_ratio
        scaled_alpha_height = alpha_height * linear_scale_ratio
        
        # scale_ratio就是线性缩放比例本身
        # 这表示image_alpha需要缩放多少倍才能达到目标不透明像素数量
        final_scale_ratio = linear_scale_ratio
        
        # 返回最终缩放比例和缩放后的尺寸（四舍五入为整数）
        return (
            final_scale_ratio,
            int(round(scaled_alpha_width)),
            int(round(scaled_alpha_height))
        )