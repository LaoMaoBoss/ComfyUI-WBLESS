"""
RunningHUB LLM 节点
通过 RunningHub OpenAI 兼容接口调用多厂商模型（DeepSeek / Gemini / Doubao 等）
支持动态多图输入（OpenAI Vision 兼容的 Base64 data URL）
"""

import base64
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from io import BytesIO

import numpy as np
from PIL import Image

from cozy_comfyui import InputType, deep_merge
from cozy_comfyui.lexicon import Lexicon
from cozy_comfyui.node import CozyBaseNode

logger = logging.getLogger(__name__)

# RunningHub LLM OpenAI 兼容 base_url 默认值
DEFAULT_BASE_URL = "https://llm.runninghub.ai/v1"
MAX_IMAGE_INPUTS = 10

# 各厂商模型共用同一 Chat Completions 协议，仅 model 字段不同（按厂商归类）
MODEL_CHOICES = [
    # OpenAI
    "openai/gpt-5.6-sol-saver",
    "openai/gpt-5.6-terra-saver",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.5-saver",
    "openai/gpt-5.5-pro",
    "openai/gpt-5.4-pro",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "openai/gpt-5.4-nano",
    "openai/gpt-5.3-codex",
    # Anthropic
    "anthropic/claude-fable-5",
    "anthropic/claude-opus-5",
    "anthropic/claude-opus-4.8-saver",
    "anthropic/claude-opus-4.7-saver",
    "anthropic/claude-opus-4.6-saver",
    "anthropic/claude-opus-4.5",
    "anthropic/claude-sonnet-5",
    "anthropic/claude-sonnet-4.6-saver",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5-saver",
    # Google
    "google/gemini-3.7-flash",
    "google/gemini-3.6-flash",
    "google/gemini-3.5-flash",
    "google/gemini-3.5-flash-lite",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3.1-flash-lite-preview",
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    # DeepSeek
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    # ByteDance Doubao
    "bytedance/doubao-seed-evolving",
    "bytedance/doubao-seed-2.1-pro",
    "bytedance/doubao-seed-2.1-turbo",
    "bytedance/doubao-seed-2.0-pro",
    "bytedance/doubao-seed-2.0-code",
    "bytedance/doubao-seed-2.0-lite",
    "bytedance/doubao-seed-2.0-mini",
    # Qwen
    "qwen/qwen3.8-max",
    "qwen/qwen3.7-max",
    "qwen/qwen3.7-plus",
    "qwen/qwen3.6-max-preview",
    "qwen/qwen3.6-plus",
    "qwen/qwen3.6-flash",
    # GLM
    "glm-5.2",
    "glm-5.1",
    "glm-5-turbo",
    "glm-5v-turbo",
    "glm-5",
    # xAI
    "xai/grok-4.6",
    "xai/grok-4.5",
    "xai/grok-4.3",
    # MiniMax
    "minimax/minimax-m2.7",
]


class RunningHubLlmNode(CozyBaseNode):
    """
    RunningHUB LLM
    对接 RunningHub LLM Chat Completions API，支持多模型、reasoning_effort 与动态多图视觉输入
    """

    NAME = "RunningHUB LLM"
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputType:
        # 动态图像输入：连上 image_1 后由前端追加 image_2 ...
        dyn_inputs = {
            "image_1": ("IMAGE", {
                "tooltip": "Image input. When connected, one more input slot is added."
            })
        }

        # 新版 ComfyUI 校验动态端口时，用容器绕过静态 optional 定义限制
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
                    "api_key": ("STRING", {
                        "default": "",
                        "multiline": False,
                        "placeholder": "输入 RunningHub API Key (可带或不带 Bearer)"
                    }),
                    "base_url": ("STRING", {
                        "default": DEFAULT_BASE_URL,
                        "multiline": False,
                        "placeholder": "如 https://llm.runninghub.ai/v1"
                    }),
                    "model": (MODEL_CHOICES, {
                        "default": "deepseek/deepseek-v4-flash"
                    }),
                    # 非空时优先生效，便于接入下拉列表未收录的模型
                    "custom_model": ("STRING", {
                        "default": "",
                        "multiline": False,
                        "placeholder": "自定义模型 ID（有值则覆盖上方下拉）"
                    }),
                    # extra_body.reasoning_effort；官方示例默认 none（非思考）
                    "reasoning_effort": (["none", "low", "high", "max"], {
                        "default": "none"
                    }),
                    "system_instruction": ("STRING", {
                        "default": "You are a helpful assistant",
                        "multiline": True,
                        "placeholder": "输入系统提示词"
                    }),
                    "user_input": ("STRING", {
                        "default": "",
                        "multiline": True,
                        "placeholder": "输入用户的提问"
                    }),
                    "max_tokens": ("INT", {
                        "default": 2048,
                        "min": 1,
                        "max": 131072,
                        "step": 1
                    }),
                    "temperature": ("FLOAT", {
                        "default": 1.0,
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.1
                    }),
                    "top_p": ("FLOAT", {
                        "default": 1.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.05
                    }),
                    "presence_penalty": ("FLOAT", {
                        "default": 0.0,
                        "min": -2.0,
                        "max": 2.0,
                        "step": 0.1
                    }),
                    "frequency_penalty": ("FLOAT", {
                        "default": 0.0,
                        "min": -2.0,
                        "max": 2.0,
                        "step": 0.1
                    }),
                },
                "optional": optional_inputs,
            },
        )
        return Lexicon._parse(d)

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "reasoning", "raw_response")

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time()

    @staticmethod
    def _extract_param(value, default):
        # 兼容 ComfyUI 的列表传参
        if isinstance(value, list):
            return value[0] if value else default
        return value if value is not None else default

    @staticmethod
    def _build_chat_completions_url(base_url):
        # 允许用户填 base_url 或已带 /chat/completions 的完整路径
        url = base_url.rstrip("/")
        if url.endswith("/chat/completions"):
            return url
        return f"{url}/chat/completions"

    def _image_to_data_url(self, image_tensor):
        # ComfyUI IMAGE → JPEG Base64 data URL，供 Vision 模型直接内联读取
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
                logger.error(f"[RunningHUB LLM] 图像 {image_key} 转换失败: {e}")
        return image_urls

    def _build_messages(self, system_instruction, user_input, image_urls):
        messages = []
        if system_instruction:
            messages.append({
                "role": "system",
                "content": system_instruction
            })

        if image_urls:
            content = []
            if user_input:
                content.append({"type": "text", "text": user_input})
            for url in image_urls:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            messages.append({"role": "user", "content": content})
        elif user_input:
            messages.append({
                "role": "user",
                "content": user_input
            })

        return messages

    def run(self, **kw):
        api_key = str(self._extract_param(kw.get("api_key"), ""))
        base_url = str(self._extract_param(kw.get("base_url"), DEFAULT_BASE_URL)).strip()
        model = str(self._extract_param(kw.get("model"), "deepseek/deepseek-v4-flash"))
        custom_model = str(self._extract_param(kw.get("custom_model"), "")).strip()
        # 自定义模型非空时覆盖下拉选项
        if custom_model:
            model = custom_model
        reasoning_effort = str(self._extract_param(kw.get("reasoning_effort"), "none"))
        system_instruction = str(self._extract_param(kw.get("system_instruction"), ""))
        user_input = str(self._extract_param(kw.get("user_input"), ""))
        max_tokens = int(self._extract_param(kw.get("max_tokens"), 2048))
        temperature = float(self._extract_param(kw.get("temperature"), 1.0))
        top_p = float(self._extract_param(kw.get("top_p"), 1.0))
        presence_penalty = float(self._extract_param(kw.get("presence_penalty"), 0.0))
        frequency_penalty = float(self._extract_param(kw.get("frequency_penalty"), 0.0))

        if not api_key:
            raise ValueError("请提供有效的 RunningHub API Key")

        if not base_url:
            raise ValueError("请提供有效的 base_url")

        image_urls = self._collect_image_urls(kw)
        if not user_input and not system_instruction and not image_urls:
            raise ValueError("请提供系统提示词、用户输入或图片")

        endpoint = self._build_chat_completions_url(base_url)
        messages = self._build_messages(system_instruction, user_input, image_urls)

        # 与官方 OpenAI SDK 示例对齐；reasoning_effort 对应 extra_body
        payload_dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "stream": False,
            "reasoning_effort": reasoning_effort,
        }

        try:
            logger.info(
                f"[RunningHUB LLM] 开始请求 {model} "
                f"effort={reasoning_effort} images={len(image_urls)} (URL: {endpoint})"
            )

            payload = json.dumps(payload_dict).encode("utf-8")
            auth_token = api_key if "Bearer " in api_key else f"Bearer {api_key}"
            headers = {
                "Authorization": auth_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            req = urllib.request.Request(
                endpoint,
                data=payload,
                headers=headers,
                method="POST",
            )

            # 兼容公司代理 / 自签证书链导致的 CERTIFICATE_VERIFY_FAILED
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            try:
                with urllib.request.urlopen(req, timeout=300, context=ssl_context) as response:
                    raw_text = response.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                raw_text = e.read().decode("utf-8")
                logger.error(
                    f"[RunningHUB LLM] HTTP请求失败: "
                    f"{e.code} {e.reason}\n{raw_text}"
                )

            result_text = ""
            reasoning_text = ""
            try:
                resp_json = json.loads(raw_text)
                if "choices" in resp_json and resp_json["choices"]:
                    message = resp_json["choices"][0].get("message", {})
                    result_text = message.get("content", "") or ""
                    # 部分网关把思考过程放在 reasoning_content
                    reasoning_text = message.get("reasoning_content", "") or ""
                elif "error" in resp_json:
                    error = resp_json["error"]
                    if isinstance(error, dict):
                        result_text = f"API 报错: {error.get('message', '未知错误')}"
                    else:
                        result_text = f"API 报错: {error}"
                else:
                    result_text = f"API 未返回合适的回复内容。\nRaw: {raw_text}"
            except Exception as e:
                logger.error(f"[RunningHUB LLM] 解析失败: {e}")
                result_text = f"解析响应发生错误: {str(e)}\n\n{raw_text}"

            return (result_text, reasoning_text, raw_text)

        except Exception as e:
            logger.error(f"[RunningHUB LLM] API调用发生错误: {e}")
            raise Exception(f"RunningHUB LLM 节点执行失败: {e}") from e


NODE_CLASS_MAPPINGS = {
    "RunningHUB LLM": RunningHubLlmNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RunningHUB LLM": "RunningHUB LLM"
}
