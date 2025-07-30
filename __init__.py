import sys
from pathlib import Path

WBLESS_LIB_PATH = Path(__file__).resolve().parent / "lib"
if str(WBLESS_LIB_PATH) not in sys.path:
    sys.path.insert(0, str(WBLESS_LIB_PATH))

from cozy_comfyui.node import \
    loader

PACKAGE = "WBLESS"
WEB_DIRECTORY = "./web"
ROOT = Path(__file__).resolve().parent

NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = loader(ROOT,
                                                         PACKAGE,
                                                         "core",
                                                         f"🌈{PACKAGE}",
                                                         False)
