import execution
import nodes
from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY
import time

MAX_OUTPUTS = 64
MAX_INPUTS = 64

class WBLESSExecutionBlocker:
    def __init__(self):
        pass

def is_execution_blocked(values):
    if not isinstance(values, list):
        return False
    return any(isinstance(v, WBLESSExecutionBlocker) for v in values)

_original_get_output_data = execution.get_output_data

def _hooked_get_output_data(obj, input_data_all, *args, **kwargs):
    if not isinstance(input_data_all, dict):
        return _original_get_output_data(obj, input_data_all, *args, **kwargs)
    
    if isinstance(obj, Switch):
        path_list = input_data_all.get("Path")
        
        if not path_list:
            return _original_get_output_data(obj, input_data_all, *args, **kwargs)

        path_val = path_list[0]
        selected_input_name = f"Input_{path_val}"
        
        selected_input_data = input_data_all.get(selected_input_name)
        if selected_input_data and is_execution_blocked(selected_input_data):
            return ([[WBLESSExecutionBlocker()]] * len(obj.RETURN_TYPES), {}, False)
        else:
            return _original_get_output_data(obj, input_data_all, *args, **kwargs)

    for an_input in input_data_all.values():
        if is_execution_blocked(an_input):
            return ([[WBLESSExecutionBlocker()]] * len(obj.RETURN_TYPES), {}, False)
    
    return _original_get_output_data(obj, input_data_all, *args, **kwargs)

execution.get_output_data = _hooked_get_output_data


class InversedSwitch(CozyBaseNode):
    NAME = "Inversed Switch"
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "Input": (COZY_TYPE_ANY,),
                "Path": ("INT", {"default": 1, "min": 1, "max": MAX_OUTPUTS}),
            }
        }

    RETURN_TYPES = (COZY_TYPE_ANY,) * MAX_OUTPUTS
    RETURN_NAMES = tuple([f"Output_{i+1}" for i in range(MAX_OUTPUTS)])

    def run(self, Input, Path, **kw):
        if isinstance(Path, list) and len(Path) == 1:
            Path = Path[0]

        value_to_route = Input
        if isinstance(Input, list) and len(Input) > 0:
            value_to_route = Input[0]

        results = [WBLESSExecutionBlocker()] * MAX_OUTPUTS
        
        if 1 <= Path <= MAX_OUTPUTS:
            results[Path - 1] = value_to_route
        
        return tuple(results)

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time()
        

class Switch(CozyBaseNode):
    NAME = "Switch"
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "Path": ("INT", {"default": 1, "min": 1, "max": MAX_INPUTS}),
            },
            "optional": {
                "Input_1": (COZY_TYPE_ANY,),
            }
        }

    RETURN_TYPES = (COZY_TYPE_ANY,)
    RETURN_NAMES = ("output",)

    def run(self, Path, **kw):
        if isinstance(Path, list) and len(Path) == 1:
            Path = Path[0]
            
        selected_input_name = f"Input_{Path}"
        value = kw.get(selected_input_name)

        if isinstance(value, list) and len(value) > 0:
            value = value[0]

        return (value,)

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time()

NODE_CLASS_MAPPINGS = {
    "Inversed Switch": InversedSwitch,
    "Switch": Switch
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Inversed Switch": "Inversed Switch",
    "Switch": "Switch"
}
