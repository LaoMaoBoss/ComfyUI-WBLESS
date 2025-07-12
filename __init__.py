from pathlib import Path

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
