import urllib.request
import urllib.error
import json
import logging
from cozy_comfyui.node import CozyBaseNode

logger = logging.getLogger(__name__)

class DeepSeekChatNode(CozyBaseNode):
    """
    DeepSeek Chat
    """
    NAME = "DeepSeek Chat"
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入你的 API key (可带或不带 Bearer)"
                }),
                "model": (["deepseek-chat", "deepseek-reasoner"], {
                    "default": "deepseek-chat"
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
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "reasoning", "raw_response")

    def run(self, api_key, model, system_instruction, user_input, temperature, top_p):
        # 兼容 ComfyUI 的列表传参
        if isinstance(api_key, list): api_key = api_key[0] if len(api_key) > 0 else ""
        if isinstance(model, list): model = model[0] if len(model) > 0 else "deepseek-chat"
        if isinstance(system_instruction, list): system_instruction = system_instruction[0] if len(system_instruction) > 0 else ""
        if isinstance(user_input, list): user_input = user_input[0] if len(user_input) > 0 else ""
        if isinstance(temperature, list): temperature = temperature[0] if len(temperature) > 0 else 1.0
        if isinstance(top_p, list): top_p = top_p[0] if len(top_p) > 0 else 1.0

        endpoint = "https://api.deepseek.com/chat/completions"

        try:
            logger.info(f"[DeepSeek Chat] 开始请求 {model} (URL: {endpoint})")
            
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

            payload_dict = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "stream": False
            }
            
            payload = json.dumps(payload_dict).encode("utf-8")
            
            # 处理 Authorization 头
            auth_token = api_key if "Bearer " in api_key else f"Bearer {api_key}"
            headers = {
               'Authorization': auth_token,
               'Content-Type': 'application/json',
               'Accept': 'application/json'
            }
            
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
            
            try:
                with urllib.request.urlopen(req) as response:
                    raw_text = response.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                raw_text = e.read().decode("utf-8")
                logger.error(f"[DeepSeek Chat] HTTP请求失败: {e.code} {e.reason}\n{raw_text}")
            
            # 解析结果
            result_text = ""
            reasoning_text = ""
            try:
                resp_json = json.loads(raw_text)
                if "choices" in resp_json and len(resp_json["choices"]) > 0:
                    message = resp_json["choices"][0].get("message", {})
                    result_text = message.get("content", "")
                    reasoning_text = message.get("reasoning_content", "")
                else:
                    if "error" in resp_json:
                        result_text = f"API 报错: {resp_json['error'].get('message', '未知错误')}"
                    else:
                        result_text = f"API 未返回合适的回复内容。\nRaw: {raw_text}"
            except Exception as e:
                logger.error(f"[DeepSeek Chat] 解析失败: {e}")
                result_text = f"解析响应发生错误: {str(e)}\n\n{raw_text}"

            return (result_text, reasoning_text, raw_text)
            
        except Exception as e:
            logger.error(f"[DeepSeek Chat] API调用发生错误: {e}")
            raise Exception(f"DeepSeek Chat 节点执行失败: {e}")

NODE_CLASS_MAPPINGS = {
    "DeepSeek Chat": DeepSeekChatNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DeepSeek Chat": "DeepSeek Chat"
}
