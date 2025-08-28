import execution
import nodes
from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY
import time
import logging
import inspect

MAX_OUTPUTS = 64
MAX_INPUTS = 64

# 检测ComfyUI版本是否支持新的执行模型
def is_execution_model_version_supported():
    """检测是否支持新版ComfyUI的执行模型"""
    try:
        import comfy_execution  # noqa: F401
        return True
    except Exception:
        return False

# 获取合适的执行阻断器
def get_execution_blocker():
    """根据ComfyUI版本获取合适的执行阻断器"""
    if is_execution_model_version_supported():
        try:
            from comfy_execution.graph import ExecutionBlocker
            return ExecutionBlocker(None)
        except ImportError as e:
            logging.warning(f"[WBLESS] Failed to import ExecutionBlocker from comfy_execution.graph: {e}")
            return WBLESSExecutionBlocker()
    else:
        return WBLESSExecutionBlocker()

class WBLESSExecutionBlocker:
    """向后兼容的执行阻断器类"""
    def __init__(self):
        pass

def is_execution_blocked(values):
    """检测值列表中是否包含执行阻断器"""
    if not isinstance(values, list):
        return False
    
    # 检查两种类型的阻断器
    for v in values:
        if isinstance(v, WBLESSExecutionBlocker):
            return True
        # 检查新版ComfyUI的ExecutionBlocker
        if is_execution_model_version_supported():
            try:
                from comfy_execution.graph import ExecutionBlocker
                if isinstance(v, ExecutionBlocker):
                    return True
            except ImportError:
                pass
    return False

_original_get_output_data = execution.get_output_data

def _hooked_get_output_data(obj, input_data_all, *args, **kwargs):
    """钩子函数：拦截ComfyUI的节点执行，实现智能的执行阻断机制"""
    if not isinstance(input_data_all, dict):
        return _original_get_output_data(obj, input_data_all, *args, **kwargs)
    
    # Switch节点的特殊处理：只检查活动线路的输入
    if isinstance(obj, Switch):
        path_list = input_data_all.get("Path")
        
        if not path_list:
            return _original_get_output_data(obj, input_data_all, *args, **kwargs)

        path_val = path_list[0]
        selected_input_name = f"Input_{path_val}"
        
        # 只检查被选中的输入线路
        selected_input_data = input_data_all.get(selected_input_name)
        if selected_input_data and is_execution_blocked(selected_input_data):
            # 返回合适的阻断器
            blocker = get_execution_blocker()
            return ([[blocker]] * len(obj.RETURN_TYPES), {}, False)
        else:
            return _original_get_output_data(obj, input_data_all, *args, **kwargs)

    # 普通节点：检查所有输入，任何一个被阻断都阻止执行
    for an_input in input_data_all.values():
        if is_execution_blocked(an_input):
            # 返回合适的阻断器
            blocker = get_execution_blocker()
            return ([[blocker]] * len(obj.RETURN_TYPES), {}, False)
    
    return _original_get_output_data(obj, input_data_all, *args, **kwargs)

# 应用execution hook来处理执行阻断
# 在新版ComfyUI中主要用于InversedSwitch的阻断逻辑
# Switch节点现在使用lazy evaluation
execution.get_output_data = _hooked_get_output_data
if is_execution_model_version_supported():
    logging.info("[WBLESS] Applied execution hook for new ComfyUI version (for InversedSwitch blocking)")
else:
    logging.info("[WBLESS] Applied execution hook for legacy ComfyUI version")


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
        """执行Inversed Switch节点的路由逻辑"""
        if isinstance(Path, list) and len(Path) == 1:
            Path = Path[0]

        value_to_route = Input
        if isinstance(Input, list) and len(Input) > 0:
            value_to_route = Input[0]

        # 使用合适的执行阻断器填充结果数组
        blocker = get_execution_blocker()
        results = [blocker] * MAX_OUTPUTS
        
        # 只有指定的路径输出真实数据
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
        # 为新版ComfyUI创建动态输入
        dyn_inputs = {"Input_1": (COZY_TYPE_ANY, {"lazy": True, "tooltip": "Any input. When connected, one more input slot is added."})}
        
        # 如果是新版ComfyUI，使用特殊的容器类来支持动态输入验证
        if is_execution_model_version_supported():
            stack = inspect.stack()
            if stack[2].function == 'get_input_info':
                # 绕过验证的容器类
                class AllContainer:
                    def __contains__(self, item):
                        return True

                    def __getitem__(self, key):
                        return COZY_TYPE_ANY, {"lazy": True}

                dyn_inputs = AllContainer()

        return {
            "required": {
                "Path": ("INT", {"default": 1, "min": 1, "max": MAX_INPUTS, "tooltip": "The input number you want to output among the inputs"}),
            },
            "optional": dyn_inputs,
            "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"}
        }

    RETURN_TYPES = (COZY_TYPE_ANY,)
    RETURN_NAMES = ("output",)

    def check_lazy_status(self, *args, **kwargs):
        """告诉ComfyUI只需要加载选中的输入"""
        if 'Path' not in kwargs:
            return []
        
        try:
            # 处理Path可能是列表的情况
            path_value = kwargs['Path']
            if isinstance(path_value, list) and len(path_value) > 0:
                selected_index = int(path_value[0])
            else:
                selected_index = int(path_value)
                
            input_name = f"Input_{selected_index}"
            
            logging.info(f"[WBLESS Switch] check_lazy_status - Path={path_value}, selected_index={selected_index}, input_name={input_name}")

            # 只返回需要加载的输入
            if input_name in kwargs:
                logging.info(f"[WBLESS Switch] Found input {input_name}, loading it")
                return [input_name]
            else:
                logging.info(f"[WBLESS Switch] Input {input_name} not found in kwargs: {list(kwargs.keys())}")
                return []
                
        except Exception as e:
            logging.error(f"[WBLESS Switch] Error in check_lazy_status: {e}, Path={kwargs.get('Path')}, type={type(kwargs.get('Path'))}")
            return []

    def run(self, Path, unique_id=None, extra_pnginfo=None, **kw):
        """Switch节点的核心逻辑"""
        if isinstance(Path, list) and len(Path) == 1:
            Path = Path[0]
            
        selected_input_name = f"Input_{Path}"
        value = kw.get(selected_input_name)

        # 处理列表格式的输入
        if isinstance(value, list) and len(value) > 0:
            value = value[0]

        logging.info(f"[WBLESS Switch] Path={Path}, selected_input={selected_input_name}, value_type={type(value)}")

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
