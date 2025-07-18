import torch
from cozy_comfyui.node import CozyBaseNode

class GetImageSize(CozyBaseNode):
    NAME = "Get Image Size"
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "get_size"
    
    def get_size(self, image: torch.Tensor):
        if isinstance(image, list):
            if not image:
                return (0, 0)
            image = image[0]

        _batch_size, height, width, _channels = image.shape
        
        return (width, height)


class GetMaskSize(CozyBaseNode):
    NAME = "Get Mask Size"
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "get_size"
    
    def get_size(self, mask: torch.Tensor):
        if isinstance(mask, list):
            if not mask:
                return (0, 0)
            mask = mask[0]

        threshold = 0.01
        
        if not torch.any(mask > threshold):
            return (0, 0)

        nonzero_indices = torch.nonzero(mask > threshold, as_tuple=False)

        dim = mask.dim()
        if dim == 3:
            y_indices = nonzero_indices[:, 1]
            x_indices = nonzero_indices[:, 2]
        elif dim == 4:
            if mask.shape[1] == 1:
                y_indices = nonzero_indices[:, 2]
                x_indices = nonzero_indices[:, 3]
            else:
                y_indices = nonzero_indices[:, 1]
                x_indices = nonzero_indices[:, 2]
        else:
            return (0, 0)

        y_min, y_max = y_indices.min(), y_indices.max()
        x_min, x_max = x_indices.min(), x_indices.max()

        width = (x_max - x_min + 1).item()
        height = (y_max - y_min + 1).item()
        
        return (width, height)
