"""
RunningHub DeepSeek Chat 节点
通过 RunningHub OpenAI 兼容接口调用 DeepSeek V4（Pro / Flash）
"""

import json
import logging
import ssl
import urllib.error
import urllib.request

from cozy_comfyui.node import CozyBaseNode

logger = logging.getLogger(__name__)

# RunningHub LLM OpenAI 兼容 base_url 默认值
DEFAULT_BASE_URL = "https://llm.runninghub.ai/v1"

# 官方示例中的模型 ID
MODEL_CHOICES = [
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
]


class RunningHubDeepSeekChatNode(CozyBaseNode):
    """
    RunningHub DeepSeek Chat
    对接 RunningHub LLM Chat Completions API，支持 reasoning_effort 与采样参数
    """

    NAME = "RunningHub DeepSeek Chat"
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
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
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "reasoning", "raw_response")

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

    def run(
        self,
        api_key,
        base_url,
        model,
        reasoning_effort,
        system_instruction,
        user_input,
        max_tokens,
        temperature,
        top_p,
        presence_penalty,
        frequency_penalty,
    ):
        api_key = str(self._extract_param(api_key, ""))
        base_url = str(self._extract_param(base_url, DEFAULT_BASE_URL)).strip()
        model = str(self._extract_param(model, "deepseek/deepseek-v4-flash"))
        reasoning_effort = str(self._extract_param(reasoning_effort, "none"))
        system_instruction = str(self._extract_param(system_instruction, ""))
        user_input = str(self._extract_param(user_input, ""))
        max_tokens = int(self._extract_param(max_tokens, 2048))
        temperature = float(self._extract_param(temperature, 1.0))
        top_p = float(self._extract_param(top_p, 1.0))
        presence_penalty = float(self._extract_param(presence_penalty, 0.0))
        frequency_penalty = float(self._extract_param(frequency_penalty, 0.0))

        if not api_key:
            raise ValueError("请提供有效的 RunningHub API Key")

        if not base_url:
            raise ValueError("请提供有效的 base_url")

        if not user_input and not system_instruction:
            raise ValueError("请提供系统提示词或用户输入")

        endpoint = self._build_chat_completions_url(base_url)

        messages = []
        if system_instruction:
            messages.append({
                "role": "system",
                "content": system_instruction
            })
        if user_input:
            messages.append({
                "role": "user",
                "content": user_input
            })

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
                f"[RunningHub DeepSeek Chat] 开始请求 {model} "
                f"effort={reasoning_effort} (URL: {endpoint})"
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
                    f"[RunningHub DeepSeek Chat] HTTP请求失败: "
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
                logger.error(f"[RunningHub DeepSeek Chat] 解析失败: {e}")
                result_text = f"解析响应发生错误: {str(e)}\n\n{raw_text}"

            return (result_text, reasoning_text, raw_text)

        except Exception as e:
            logger.error(f"[RunningHub DeepSeek Chat] API调用发生错误: {e}")
            raise Exception(f"RunningHub DeepSeek Chat 节点执行失败: {e}") from e


NODE_CLASS_MAPPINGS = {
    "RunningHub DeepSeek Chat": RunningHubDeepSeekChatNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RunningHub DeepSeek Chat": "RunningHub DeepSeek Chat"
}
