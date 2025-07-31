import math
import torch
from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY

class AreaBasedScale(CozyBaseNode):
    NAME = "Area Based Scale"
    
    @classmethod
    def INPUT_TYPES(s):
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
        if isinstance(width_a, list) and width_a:
            width_a = width_a[0]
        if isinstance(height_a, list) and height_a:
            height_a = height_a[0]
        if isinstance(width_b, list) and width_b:
            width_b = width_b[0]
        if isinstance(height_b, list) and height_b:
            height_b = height_b[0]
        
        if isinstance(ratio, list) and ratio:
            ratio = ratio[0]
        
        if isinstance(cap_threshold, list) and cap_threshold:
            cap_threshold = cap_threshold[0]
        if isinstance(enable_cap, list) and enable_cap:
            enable_cap = enable_cap[0]

        width_a_int, height_a_int = int(width_a), int(height_a)
        width_b_int, height_b_int = int(width_b), int(height_b)

        if width_a_int <= 0 or height_a_int <= 0:
            return (0, 0, 1.0)

        aspect_ratio_a = width_a_int / height_a_int
        
        area_b = width_b_int * height_b_int
        
        target_area = area_b * ratio
        if target_area <= 0:
            return (0, 0, 1.0)

        output_height_float = math.sqrt(target_area / aspect_ratio_a)
        output_width_float = output_height_float * aspect_ratio_a

        if enable_cap:
            cap_width = width_b_int * cap_threshold
            cap_height = height_b_int * cap_threshold

            if output_width_float > cap_width or output_height_float > cap_height:
                width_scale_down_ratio = cap_width / output_width_float if output_width_float > 0 else 1.0
                height_scale_down_ratio = cap_height / output_height_float if output_height_float > 0 else 1.0
                
                final_downscale_ratio = min(width_scale_down_ratio, height_scale_down_ratio)
                
                output_width_float *= final_downscale_ratio
                output_height_float *= final_downscale_ratio

        output_width = int(round(output_width_float))
        output_height = int(round(output_height_float))

        scale_ratio = 1.0
        if width_a_int > 0:
            scale_ratio = output_width_float / width_a_int
        elif height_a_int > 0:
            scale_ratio = output_height_float / height_a_int
        
        return (output_width, output_height, scale_ratio)