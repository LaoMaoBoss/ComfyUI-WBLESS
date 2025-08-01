"""."""

import sys
import json
import inspect
import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

from cozy_comfyui import \
    COZY_INTERNAL, \
    InputType, \
    logger

# ==============================================================================
# === TYPE ===
# ==============================================================================

class CozyTypeAny(str):
    """AnyType input wildcard trick taken from pythongossss's:

    https://github.com/pythongosssss/ComfyUI-Custom-Scripts
    """
    def __ne__(self, __value: object) -> bool:
        return False

COZY_TYPE_ANY = CozyTypeAny("*")

COZY_TYPE_NUMBER = "BOOLEAN,FLOAT,INT"
COZY_TYPE_VECTOR = "VEC2,VEC3,VEC4"
COZY_TYPE_NUMERICAL = f"{COZY_TYPE_NUMBER},{COZY_TYPE_VECTOR}"
COZY_TYPE_IMAGE = "IMAGE,MASK"
COZY_TYPE_FULL = f"{COZY_TYPE_NUMERICAL},{COZY_TYPE_IMAGE}"

COZY_TYPE_NUMBERB = "BOOLEAN,FLOAT,INT,VEC2,VEC3,VEC4,IMAGE,MASK"
COZY_TYPE_NUMBERF = "FLOAT,BOOLEAN,INT,VEC2,VEC3,VEC4,IMAGE,MASK"
COZY_TYPE_NUMBERI = "INT,BOOLEAN,FLOAT,VEC2,VEC3,VEC4,IMAGE,MASK"
COZY_TYPE_VECTOR2 = "VEC2,VEC3,VEC4,BOOLEAN,FLOAT,INT,IMAGE,MASK"
COZY_TYPE_VECTOR3 = "VEC3,VEC2,VEC4,BOOLEAN,FLOAT,INT,IMAGE,MASK"
COZY_TYPE_VECTOR4 = "VEC4,VEC2,VEC3,BOOLEAN,FLOAT,INT,IMAGE,MASK"
COZY_TYPE_IMG     = "IMAGE,BOOLEAN,FLOAT,INT,VEC2,VEC3,VEC4,MASK"
COZY_TYPE_MASK    = "MASK,BOOLEAN,FLOAT,INT,VEC2,VEC3,VEC4,IMAGE"

# ==============================================================================
# === GLOBAL ===
# ==============================================================================

_LOADED = {}

# ==============================================================================
# === SUPPORT ===
# ==============================================================================

def load_module(root:str, name: str) -> None|ModuleType:
    root_module = root.split("/")[-1]
    try:
        route = name.split(f"{root}/")[1]
        route = route.split('.')[0].replace('/', '.')
        module = f"{root_module}.{route}"
    except Exception as e:
        logger.warning(f"module failed {name}")
        logger.warning(str(e))
        return

    if (lib := _LOADED.get(module, None)) is not None:
        return lib

    try:
        lib = importlib.import_module(module)
        _LOADED[module] = lib
        return lib
    except Exception as e:
        logger.warning(f"module failed {module}")
        logger.warning(str(e))

def loader(root_str: str, pack: str, directory: str='',
           category: str="COZY COMFYUI ☕",
           rename: bool=True) -> tuple[dict[str, object], dict[str, str]]:
    """
    rename will force the new name from the existing definition on the old node.
    Currently used to support older Jovimetrix nodes
    """

    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    NODE_LIST_MAP = {}

    # package core root
    root = Path(root_str)
    root_str = str(root).replace("\\", "/")
    core = str(root.parent)
    sys.path.append(core)
    node_root = f"{directory}/**/*.py"

    for fname in root.glob(node_root):
        if fname.stem.startswith('_'):
            continue

        fname = str(fname).replace("\\", "/")
        if (module := load_module(root_str, fname)) is None:
            continue

        # check if there is a dynamic register function....
        try:
            if hasattr(module, 'import_dynamic'):
                for class_name, class_def in module.import_dynamic():
                    setattr(module, class_name, class_def)
        except Exception as e:
            logger.exception(str(e))

        classes = inspect.getmembers(module, inspect.isclass)
        for class_name, class_object in classes:
            if class_name.endswith("Lexicon"):
                continue
            if not class_name.endswith('BaseNode') and hasattr(class_object, 'NAME'):
                name = f"{class_object.NAME} ({pack})" if rename else class_object.NAME
                NODE_DISPLAY_NAME_MAPPINGS[name] = name
                NODE_CLASS_MAPPINGS[name] = class_object
                desc = class_object.DESCRIPTION if hasattr(class_object, 'DESCRIPTION') else name
                NODE_LIST_MAP[name] = desc.split('.')[0].strip('\n')
                new_cat = category
                if hasattr(class_object, 'CATEGORY'):
                    if class_object.CATEGORY.startswith(new_cat):
                        new_cat = class_object.CATEGORY
                    else:
                        new_cat = f"{new_cat}/{class_object.CATEGORY}"

                class_object.CATEGORY = new_cat

    NODE_CLASS_MAPPINGS = {x[0] : x[1] for x in sorted(NODE_CLASS_MAPPINGS.items(),
                                                       key=lambda item: getattr(item[1], 'SORT', 0))}

    keys = NODE_CLASS_MAPPINGS.keys()
    logger.info(f"{pack} {len(keys)} nodes loaded")

    # only do the list on local runs...
    if COZY_INTERNAL:
        with open(f"{root_str}/node_list.json", "w", encoding="utf-8") as f:
            json.dump(NODE_LIST_MAP, f, sort_keys=True, indent=4 )

    return NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# ==============================================================================
# === CLASS ===
# ==============================================================================

class Singleton(type):
    """THERE CAN BE ONLY ONE"""
    _instances = {}

    def __call__(cls, *arg, **kw) -> Any:
        # If the instance does not exist, create and store it
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*arg, **kw)
        return cls._instances[cls]

class CozyBaseNode:
    INPUT_IS_LIST = True
    RETURN_TYPES = ()
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls, prompt:bool=False, extra_png:bool=False, dynprompt:bool=False) -> dict[str, str]:
        data: InputType = {
            "required": {},
            "hidden": {
                "ident": "UNIQUE_ID"
            }
        }
        if prompt:
            data["hidden"]["prompt"] = "PROMPT"
        if extra_png:
            data["hidden"]["extra_pnginfo"] = "EXTRA_PNGINFO"

        if dynprompt:
            data["hidden"]["dynprompt"] = "DYNPROMPT"
        return data

class CozyImageNode(CozyBaseNode):
    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("RGBA", "RGB", "MASK")
    OUTPUT_TOOLTIPS = (
        "Full channel [RGBA] image. If there is an alpha, the image will be masked out with it when using this output.",
        "Three channel [RGB] image. There will be no alpha.",
        "Single channel mask output."
    )
