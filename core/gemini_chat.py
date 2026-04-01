import http.client
import json
import logging
from cozy_comfyui.node import CozyBaseNode

logger = logging.getLogger(__name__)

class GeminiChatNode(CozyBaseNode):
    """
    Gemini Chat
    """
    NAME = "Gemini Chat"
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "host": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "如 millionengine.com"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入你的 token (可带或不带 Bearer)"
                }),
                "model": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "如 gemini-2.5-pro"
                }),
                "system_instruction": ("STRING", {
                    "default": "",
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
                "include_thoughts": ("BOOLEAN", {
                    "default": True
                }),
                "thinking_budget": ("INT", {
                    "default": 26240,
                    "min": 1024,
                    "max": 131072,
                    "step": 1024
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "raw_response")

    def run(self, host, api_key, model, system_instruction, user_input, temperature, top_p, include_thoughts, thinking_budget):
        # 兼容 ComfyUI 的列表传参
        if isinstance(host, list): host = host[0] if len(host) > 0 else "millionengine.com"
        if isinstance(api_key, list): api_key = api_key[0] if len(api_key) > 0 else ""
        if isinstance(model, list): model = model[0] if len(model) > 0 else "gemini-2.5-pro"
        if isinstance(system_instruction, list): system_instruction = system_instruction[0] if len(system_instruction) > 0 else ""
        if isinstance(user_input, list): user_input = user_input[0] if len(user_input) > 0 else ""
        if isinstance(temperature, list): temperature = temperature[0] if len(temperature) > 0 else 1.0
        if isinstance(top_p, list): top_p = top_p[0] if len(top_p) > 0 else 1.0
        if isinstance(include_thoughts, list): include_thoughts = include_thoughts[0] if len(include_thoughts) > 0 else True
        if isinstance(thinking_budget, list): thinking_budget = thinking_budget[0] if len(thinking_budget) > 0 else 26240

        try:
            logger.info(f"[Gemini Chat] 开始请求 {model} (Host: {host})")
            conn = http.client.HTTPSConnection(host)
            
            payload_dict = {
               "systemInstruction": {
                  "parts": [
                     {
                        "text": system_instruction
                     }
                  ]
               },
               "contents": [
                  {
                     "role": "user",
                     "parts": [
                        {
                           "text": user_input
                        }
                     ]
                  }
               ],
               "generationConfig": {
                  "temperature": temperature,
                  "topP": top_p,
               }
            }
            
            # Thinking 配置
            if include_thoughts:
                payload_dict["generationConfig"]["thinkingConfig"] = {
                   "includeThoughts": True,
                   "thinkingBudget": thinking_budget
                }

            payload = json.dumps(payload_dict)
            
            # 处理 Authorization 头
            auth_token = api_key if "Bearer " in api_key else f"Bearer {api_key}"
            headers = {
               'Authorization': auth_token,
               'Content-Type': 'application/json'
            }
            
            endpoint = f"/v1beta/models/{model}:generateContent"
            conn.request("POST", endpoint, payload, headers)
            res = conn.getresponse()
            data = res.read()
            raw_text = data.decode("utf-8")
            
            # 解析纯文本结果
            result_text = ""
            try:
                resp_json = json.loads(raw_text)
                if "candidates" in resp_json and len(resp_json["candidates"]) > 0:
                    candidate = resp_json["candidates"][0]
                    parts = candidate.get("content", {}).get("parts", [])
                    extracted_texts = []
                    for part in parts:
                        if "text" in part:
                            extracted_texts.append(part["text"])
                    result_text = "\n".join(extracted_texts)
                else:
                    result_text = f"API未返回合适的回复内容。\nRaw: {raw_text}"
            except Exception as e:
                logger.error(f"[Gemini Chat] 解析失败: {e}")
                result_text = f"解析响应发生错误: {str(e)}\n\n{raw_text}"

            return (result_text, raw_text)
            
        except Exception as e:
            logger.error(f"[Gemini Chat] API调用发生错误: {e}")
            raise Exception(f"Gemini Chat 节点执行失败: {e}")

NODE_CLASS_MAPPINGS = {
    "Gemini Chat": GeminiChatNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Gemini Chat": "Gemini Chat"
}
