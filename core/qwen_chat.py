"""
Qwen Chat API 节点
基于阿里云百炼 DashScope OpenAI 兼容接口，支持多图对话
"""

import base64
import json
import logging
import time
import urllib.error
import urllib.request
from io import BytesIO

import numpy as np
import torch
from PIL import Image

from cozy_comfyui import InputType, deep_merge
from cozy_comfyui.lexicon import Lexicon
from cozy_comfyui.node import CozyBaseNode

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MAX_IMAGE_INPUTS = 10


class QwenChatNode(CozyBaseNode):
    """
    Qwen Chat API 节点
    支持文本与多图输入的多模态对话
    """

    NAME = "Qwen Chat"
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputType:
        dyn_inputs = {
            "image_1": ("IMAGE", {"tooltip": "Image input. When connected, one more input slot is added."})
        }

        try:
            import inspect

            stack = inspect.stack()
            if len(stack) > 2 and stack[2].function == "get_input_info":

                class ImageContainer:
                    def __contains__(self, item):
                        return item.startswith("image_")

                    def __getitem__(self, key):
                        if key.startswith("image_"):
                            return ("IMAGE", {"tooltip": "Dynamic image input"})
                        raise KeyError(key)

                dyn_inputs = ImageContainer()
        except Exception:
            pass

        d = super().INPUT_TYPES()

        if hasattr(dyn_inputs, "__getitem__") and hasattr(dyn_inputs, "__contains__"):
            optional_inputs = {}
        else:
            optional_inputs = (
                dict(dyn_inputs)
                if isinstance(dyn_inputs, dict)
                else {"image_1": ("IMAGE", {"tooltip": "Image input"})}
            )

        d = deep_merge(
            d,
            {
                "required": {
                    "api_key": (
                        "STRING",
                        {
                            "default": "",
                            "multiline": False,
                            "placeholder": "输入 DashScope API Key",
                        },
                    ),
                    "model": (
                        "STRING",
                        {
                            "default": "qwen3.7-plus",
                            "multiline": False,
                            "placeholder": "如 qwen3.7-plus",
                        },
                    ),
                    "system_instruction": (
                        "STRING",
                        {
                            "default": "",
                            "multiline": True,
                            "placeholder": "输入系统提示词（可选）",
                        },
                    ),
                    "user_input": (
                        "STRING",
                        {
                            "default": "",
                            "multiline": True,
                            "placeholder": "输入用户的提问",
                        },
                    ),
                    "temperature": (
                        "FLOAT",
                        {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1},
                    ),
                    "top_p": (
                        "FLOAT",
                        {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05},
                    ),
                },
                "optional": optional_inputs,
            },
        )
        return Lexicon._parse(d)

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "raw_response")

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time()

    @staticmethod
    def _extract_param(value, default):
        if isinstance(value, list):
            return value[0] if value else default
        return value if value is not None else default

    def _image_to_data_url(self, image_tensor):
        if isinstance(image_tensor, list) and image_tensor:
            image_tensor = image_tensor[0]

        if len(image_tensor.shape) == 4:
            image_tensor = image_tensor.squeeze(0)

        image_np = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
        image_pil = Image.fromarray(image_np)

        if image_pil.mode == "RGBA":
            background = Image.new("RGB", image_pil.size, (255, 255, 255))
            background.paste(image_pil, mask=image_pil.split()[-1])
            image_pil = background
        elif image_pil.mode != "RGB":
            image_pil = image_pil.convert("RGB")

        buffer = BytesIO()
        image_pil.save(buffer, format="JPEG", quality=95)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{image_b64}"

    def _collect_image_urls(self, kw):
        image_urls = []
        for i in range(1, MAX_IMAGE_INPUTS + 1):
            image_key = f"image_{i}"
            if image_key not in kw or kw[image_key] is None:
                continue
            try:
                image_urls.append(self._image_to_data_url(kw[image_key]))
            except Exception as e:
                logger.error(f"[Qwen Chat] 图像 {image_key} 转换失败: {e}")
        return image_urls

    def _build_messages(self, system_instruction, user_input, image_urls):
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        if image_urls:
            content = []
            for url in image_urls:
                content.append({"type": "image_url", "image_url": {"url": url}})
            if user_input:
                content.append({"type": "text", "text": user_input})
            messages.append({"role": "user", "content": content})
        elif user_input:
            messages.append({"role": "user", "content": user_input})

        return messages

    def run(self, **kw):
        api_key = str(self._extract_param(kw.get("api_key"), ""))
        model = str(self._extract_param(kw.get("model"), "qwen3.7-plus"))
        system_instruction = str(self._extract_param(kw.get("system_instruction"), ""))
        user_input = str(self._extract_param(kw.get("user_input"), ""))
        temperature = float(self._extract_param(kw.get("temperature"), 1.0))
        top_p = float(self._extract_param(kw.get("top_p"), 1.0))

        if not api_key:
            raise ValueError("请提供有效的 DashScope API Key")

        image_urls = self._collect_image_urls(kw)
        messages = self._build_messages(system_instruction, user_input, image_urls)

        if not messages:
            raise ValueError("请提供用户输入或至少一张图片")

        payload_dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        try:
            logger.info(f"[Qwen Chat] 开始请求 {model}，图片数量: {len(image_urls)}")

            payload = json.dumps(payload_dict).encode("utf-8")
            auth_token = api_key if "Bearer " in api_key else f"Bearer {api_key}"
            headers = {
                "Authorization": auth_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            req = urllib.request.Request(
                DEFAULT_ENDPOINT,
                data=payload,
                headers=headers,
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    raw_text = response.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                raw_text = e.read().decode("utf-8")
                logger.error(f"[Qwen Chat] HTTP 请求失败: {e.code} {e.reason}\n{raw_text}")

            result_text = ""
            try:
                resp_json = json.loads(raw_text)
                if "choices" in resp_json and resp_json["choices"]:
                    message = resp_json["choices"][0].get("message", {})
                    result_text = message.get("content", "") or ""
                elif "error" in resp_json:
                    error = resp_json["error"]
                    if isinstance(error, dict):
                        result_text = f"API 报错: {error.get('message', '未知错误')}"
                    else:
                        result_text = f"API 报错: {error}"
                else:
                    result_text = f"API 未返回合适的回复内容。\nRaw: {raw_text}"
            except Exception as e:
                logger.error(f"[Qwen Chat] 解析失败: {e}")
                result_text = f"解析响应发生错误: {str(e)}\n\n{raw_text}"

            return (result_text, raw_text)

        except Exception as e:
            logger.error(f"[Qwen Chat] API 调用发生错误: {e}")
            raise Exception(f"Qwen Chat 节点执行失败: {e}") from e
