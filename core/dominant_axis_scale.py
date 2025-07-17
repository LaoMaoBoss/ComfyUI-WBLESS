import torch
from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY

class DominantAxisScale(CozyBaseNode):
    NAME = "Dominant Axis Scale"
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "width_a": (COZY_TYPE_ANY,),
                "height_a": (COZY_TYPE_ANY,),
                "width_b": (COZY_TYPE_ANY,),
                "height_b": (COZY_TYPE_ANY,),
                "ratio": ("FLOAT", {"default": 0.5, "min": 0.01, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "FLOAT")
    RETURN_NAMES = ("width", "height", "scale_ratio")
    FUNCTION = "scale"
    
    def scale(self, width_a, height_a, width_b, height_b, ratio: float):
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

        width_a_int, height_a_int = int(width_a), int(height_a)
        width_b_int, height_b_int = int(width_b), int(height_b)

        if height_a_int == 0 and width_a_int == 0:
            return (0, 0, 1.0)

        if width_a_int > height_a_int:
            output_width_float = width_b_int * ratio
            
            aspect_ratio_a = width_a_int / height_a_int if height_a_int != 0 else 0
            if aspect_ratio_a == 0:
                output_height_float = 0
            else:
                output_height_float = output_width_float / aspect_ratio_a
        else:
            output_height_float = height_b_int * ratio
            
            aspect_ratio_a = width_a_int / height_a_int
            output_width_float = output_height_float * aspect_ratio_a

        output_width = int(round(output_width_float))
        output_height = int(round(output_height_float))

        scale_ratio = 1.0
        if width_a_int > 0:
            scale_ratio = output_width_float / width_a_int
        elif height_a_int > 0:
            scale_ratio = output_height_float / height_a_int
        
        return (output_width, output_height, scale_ratio) 