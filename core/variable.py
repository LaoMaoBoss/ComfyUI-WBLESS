from typing import Any
import time
from cozy_comfyui import \
    InputType, deep_merge
from cozy_comfyui.lexicon import \
    Lexicon
from cozy_comfyui.node import \
    COZY_TYPE_ANY, \
    CozyBaseNode
from server import PromptServer

COZY_TYPE_SCOPE = "COZY_SCOPE"

class SetVariableNode(CozyBaseNode):
    NAME = "Set Global Variable"
    RETURN_TYPES = (COZY_TYPE_ANY, COZY_TYPE_SCOPE)
    RETURN_NAMES = ("Output", "scope")
    
    VARIABLES = {}

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time()

    @classmethod
    def INPUT_TYPES(cls) -> InputType:
        d = super().INPUT_TYPES()
        d = deep_merge(d, {
            "required": {
                "variable_name": ("STRING", {"default": ""}),
            }
        })
        return Lexicon._parse(d)

    @classmethod
    @PromptServer.instance.routes.get("/wbless/variables")
    def get_wbless_variables(cls, *args, **kwargs):
        return {"variables": list(SetVariableNode.VARIABLES.keys())}

    def run(self, **kw) -> tuple[Any, ...]:
        variable_name = kw.get("variable_name")
        passthrough_data = kw.get('Input')
        data_to_store = kw.get('variable data')
        scope = kw.get("scope")

        if isinstance(variable_name, list) and len(variable_name) == 1:
            variable_name = variable_name[0]
        
        if isinstance(passthrough_data, list) and len(passthrough_data) == 1:
            passthrough_data = passthrough_data[0]
        
        if isinstance(data_to_store, list) and len(data_to_store) == 1:
            data_to_store = data_to_store[0]

        if variable_name and data_to_store is not None:
            SetVariableNode.VARIABLES[variable_name] = data_to_store

        return (passthrough_data, scope)

class GetVariableNode(CozyBaseNode):
    NAME = "Get Global Variable"
    RETURN_TYPES = (COZY_TYPE_ANY, COZY_TYPE_ANY, COZY_TYPE_SCOPE)
    RETURN_NAMES = ("Output", "variable data", "scope")

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time()

    @classmethod
    def INPUT_TYPES(cls) -> InputType:
        d = super().INPUT_TYPES()
        d = deep_merge(d, {
            "required": {
                "variable_name": ("STRING", {"default": "none"}),
            }
        })
        return Lexicon._parse(d)

    def run(self, **kw) -> tuple[Any, ...]:
        passthrough_data = kw.get('Input') 
        if isinstance(passthrough_data, list) and len(passthrough_data) == 1:
            passthrough_data = passthrough_data[0]

        variable_name = kw.get("variable_name")
        scope = kw.get("scope")
        
        if isinstance(variable_name, list) and len(variable_name) == 1:
            variable_name = variable_name[0]
            
        value = SetVariableNode.VARIABLES.get(variable_name, None)
            
        return (passthrough_data, value, scope)