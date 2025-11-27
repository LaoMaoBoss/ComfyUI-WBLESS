from typing import Any, Dict, Optional, List
import time
import inspect
import json
import os
import uuid
from urllib.parse import urlencode, quote_plus
import socket
from io import BytesIO

import numpy as np
from PIL import Image
import torch

from cozy_comfyui.node import CozyBaseNode
from comfy.cli_args import args
import folder_paths

MAX_INPUTS = 64
TEMP_SUBDIR = os.path.join("WBLESS", "apicore")

class APICoreNode(CozyBaseNode):
    """
    API核心节点 - 支持图片分析和API调用
    
    这个节点获取输入图片的URL，然后直接发送API请求进行处理。
    """
    NAME = "API Core"
    FUNCTION = "run"
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Dict[str, Any]]:
        """
        定义节点的输入参数
        包括提示词和动态图片输入
        """
        # 动态图片输入，非lazy以便立即获取到真实tensor
        dyn_inputs = {"image_1": ("IMAGE", {"lazy": False, "tooltip": "Image input. When connected, one more input slot is added."})}

        return {
            "required": {
                "prompt": ("STRING", {"default": "画个类似图片", "multiline": True, "tooltip": "描述生成目标的提示词"}),
                "api_key": ("STRING", {"default": "sk-xxxx", "multiline": False, "tooltip": "API authorization key"}),
                "model": ("STRING", {"default": "gemini-3-pro-image-preview", "tooltip": "模型名称，将与API返回的列表同步，亦可手动输入"}),
                "server_origin": ("STRING", {"default": "", "multiline": False, "tooltip": "必填：ComfyUI地址，例如http://192.168.1.10:8188"}),
                "size": ([
                    "1:1", "2:3", "3:2", "3:4", "4:3",
                    "4:5", "5:4", "9:16", "16:9", "21:9"
                ], {"default": "1:1", "tooltip": "输出画幅比例"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成图像数量"}),
            },
            "optional": dyn_inputs,
            "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"}
        }
    
    RETURN_TYPES = ("STRING", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("response", "preview_1", "preview_2", "preview_3", "preview_4", "preview_5", "preview_6", "preview_7", "preview_8", "preview_9", "preview_10")
    
    @classmethod
    def IS_CHANGED(cls, **kwargs) -> float:
        """
        确保节点在每次运行时都会重新执行
        """
        return time.time()
    
    def _get_image_url(self, image, server_origin: Optional[str] = None) -> str:
        """
        将输入图片转换为ComfyUI /view 接口可访问的URL
        """
        direct_url = self._extract_direct_url(image)
        if direct_url:
            return direct_url

        meta = self._extract_comfy_metadata(image)
        if meta is None:
            meta = self._persist_image_to_temp(image)

        if meta is None:
            raise ValueError("无法从输入图片推导出可访问的URL")

        return self._build_view_url(meta, server_origin)

    def _extract_direct_url(self, image) -> Optional[str]:
        """
        处理字符串或自带url/path属性的输入，避免重复保存
        """
        if isinstance(image, str):
            return image.strip()

        if isinstance(image, dict):
            for key in ("url", "path", "filename"):
                value = image.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        for attr in ("url", "path", "filename"):
            if hasattr(image, attr):
                value = getattr(image, attr)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _extract_comfy_metadata(self, image) -> Optional[Dict[str, str]]:
        """
        当上游节点已经写入文件并提供filename/type/subfolder信息时直接复用
        """
        candidate: Optional[Dict[str, str]] = None
        if isinstance(image, dict):
            candidate = image
        elif hasattr(image, "metadata") and isinstance(image.metadata, dict):
            candidate = image.metadata  # type: ignore[attr-defined]

        if not candidate:
            return None

        filename = candidate.get("filename")
        img_type = candidate.get("type", "temp")
        subfolder = candidate.get("subfolder", "")
        if filename:
            return {
                "filename": filename,
                "type": img_type,
                "subfolder": subfolder,
            }
        return None

    def _persist_image_to_temp(self, image) -> Optional[Dict[str, str]]:
        """
        将tensor保存到ComfyUI临时目录，生成/view可读取的文件信息
        """
        tensor = self._extract_tensor(image)
        if tensor is None:
            return None

        pil_image = self._tensor_to_pil(tensor)
        filename = f"{int(time.time() * 1000)}_{uuid.uuid4().hex}.png"
        subfolder = TEMP_SUBDIR.replace("\\", "/")
        temp_root = folder_paths.get_temp_directory()
        full_subfolder = os.path.join(temp_root, subfolder)
        os.makedirs(full_subfolder, exist_ok=True)
        file_path = os.path.join(full_subfolder, filename)
        pil_image.save(file_path, compress_level=4)
        return {
            "filename": filename,
            "type": "temp",
            "subfolder": subfolder,
        }

    def _extract_tensor(self, image) -> Optional[torch.Tensor]:
        """
        尽可能从多种数据结构里提取IMAGE对应的Tensor
        """
        if image is None:
            return None

        if isinstance(image, torch.Tensor):
            return image

        if isinstance(image, np.ndarray):
            arr = image
            if arr.dtype != np.float32:
                arr = arr.astype(np.float32)
            if arr.max() > 1.5:
                arr = arr / 255.0
            return torch.from_numpy(arr)

        if isinstance(image, Image.Image):
            arr = np.array(image).astype(np.float32) / 255.0
            return torch.from_numpy(arr)

        if isinstance(image, dict):
            # 递归检查常见字段，兼容带metadata的结构
            for key in ("image", "images", "value", "tensor", "data"):
                if key in image:
                    tensor = self._extract_tensor(image[key])
                    if tensor is not None:
                        return tensor
            for value in image.values():
                tensor = self._extract_tensor(value)
                if tensor is not None:
                    return tensor
            return None

        if isinstance(image, (list, tuple)):
            for item in image:
                tensor = self._extract_tensor(item)
                if tensor is not None:
                    return tensor
            return None

        return None

    def _tensor_to_pil(self, tensor: torch.Tensor) -> Image.Image:
        """
        将ComfyUI格式的IMAGE tensor转换为PIL Image
        """
        tensor = tensor.detach().cpu()
        if tensor.ndim == 4:
            tensor = tensor[0]
        tensor = tensor.clamp(0.0, 1.0)
        arr = tensor.mul(255).round().byte().numpy()
        if arr.ndim == 2:
            mode = "L"
        else:
            channels = arr.shape[-1]
            if channels == 1:
                mode = "L"
                arr = arr[:, :, 0]
            elif channels == 3:
                mode = "RGB"
            elif channels == 4:
                mode = "RGBA"
            else:
                raise ValueError(f"Unsupported channel count: {channels}")
        return Image.fromarray(arr, mode=mode)

    def _extract_urls_from_payload(self, payload) -> List[str]:
        """
        从API响应中提取图片URL，优先从data数组的url字段提取
        """
        urls: List[str] = []
        
        # 优先处理标准格式：{"data": [{"url": "..."}, ...]}
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        url = item.get("url")
                        if isinstance(url, str) and url.strip().startswith("http"):
                            urls.append(url.strip())
        
        # 如果标准格式没有找到，则递归扫描所有字段
        if not urls:
            def _walk(value, depth=0):
                # 限制递归深度，避免处理过深的嵌套
                if depth > 10:
                    return
                if isinstance(value, dict):
                    for k, v in value.items():
                        # 跳过revised_prompt等文本字段，避免提取其中的URL
                        if k in ("revised_prompt", "prompt", "text", "message", "content"):
                            continue
                        _walk(v, depth + 1)
                elif isinstance(value, list):
                    for item in value:
                        _walk(item, depth + 1)
                elif isinstance(value, str):
                    candidate = value.strip()
                    if candidate.startswith("http") and candidate not in urls:
                        urls.append(candidate)
            
            _walk(payload)
        
        # 去重并保持顺序
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        return unique_urls

    def _download_image_tensor(self, url: str) -> Optional[torch.Tensor]:
        """
        下载远程图片并转换为ComfyUI期望的IMAGE tensor
        """
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read()
            image = Image.open(BytesIO(data)).convert("RGB")
            arr = np.array(image).astype(np.float32) / 255.0
            tensor = torch.from_numpy(arr)[None, ...]
            return tensor
        except Exception as exc:
            print(f"Failed to download preview image from {url}: {exc}")
            return None

    def _create_blank_image(self) -> torch.Tensor:
        """
        创建一个占位的黑色图像，避免IMAGE输出为空
        """
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

    def _build_view_url(self, meta: Dict[str, str], server_origin: Optional[str] = None) -> str:
        """
        根据ComfyUI的/view接口规范拼装图片可访问URL
        """
        base_url = self._get_server_base_url(server_origin)
        query: Dict[str, str] = {
            "filename": meta["filename"],
            "type": meta.get("type", "temp"),
        }
        subfolder = meta.get("subfolder")
        if subfolder:
            query["subfolder"] = subfolder
        return f"{base_url}/view?{urlencode(query, quote_via=quote_plus)}"

    def _get_server_base_url(self, override: Optional[str] = None) -> str:
        """
        推导ComfyUI服务端origin（含协议、host、端口）
        """
        if override is None or not str(override).strip():
            raise ValueError("请在节点中填写ComfyUI地址(server_origin)")

        custom = str(override).strip()
        if custom.endswith("/"):
            custom = custom.rstrip("/")
        if "://" not in custom:
            custom = f"http://{custom}"
        return custom

        scheme = "https" if args.tls_certfile and args.tls_keyfile else "http"
        # 以下逻辑不会被触发，保留向后兼容
        host = "127.0.0.1"
        display_host = host
        if ":" in host and not host.startswith("["):
            display_host = f"[{host}]"
        port = os.environ.get("WBLESS_PUBLIC_PORT", getattr(args, "port", 8188))
        return f"{scheme}://{display_host}:{port}"
    
    def run(self, prompt, api_key, model, server_origin, size, n, unique_id=None, extra_pnginfo=None, **kw) -> tuple:
        # 处理列表格式的输入参数
        if isinstance(prompt, list) and len(prompt) > 0:
            prompt = prompt[0]
        if isinstance(api_key, list) and len(api_key) > 0:
            api_key = api_key[0]
        if isinstance(model, list) and len(model) > 0:
            model = model[0]
        if isinstance(server_origin, list) and len(server_origin) > 0:
            server_origin = server_origin[0]
        if isinstance(size, list) and len(size) > 0:
            size = size[0]
        if isinstance(n, list) and len(n) > 0:
            n = n[0]
        """
        图片分析API调用节点的运行方法
        
        获取输入图片的URL，构建API请求，发送到服务器并返回响应
        
        Args:
            prompt: 分析提示词
            api_key: API授权密钥
            model: 使用的模型名称
            unique_id: 节点唯一ID
            extra_pnginfo: PNG额外信息
            **kw: 包含所有动态输入的参数
            
        Returns:
            tuple: 包含API响应的字符串
        """
        import http.client
        from io import BytesIO
        
        server_origin_value = (server_origin or "").strip()
        if not server_origin_value:
            error_message = "请在节点中填写ComfyUI地址(server_origin)"
            result = [error_message]
            for _ in range(10):
                result.append(self._create_blank_image())
            return tuple(result)
        # 收集所有有效的图片输入URL
        image_urls = []
        for i in range(1, MAX_INPUTS + 1):
            input_name = f"image_{i}"
            if input_name in kw:
                value = kw[input_name]
                # 处理列表格式的输入
                if isinstance(value, list) and len(value) > 0:
                    try:
                        # 获取图片URL
                        img_url = self._get_image_url(value[0], server_origin_value)
                        image_urls.append(img_url)
                    except Exception as e:
                        print(f"Error getting URL for image {i}: {str(e)}")
                elif value is not None:
                    try:
                        # 获取图片URL
                        img_url = self._get_image_url(value, server_origin_value)
                        image_urls.append(img_url)
                    except Exception as e:
                        print(f"Error getting URL for image {i}: {str(e)}")
        
        # 组合最终prompt：图片URL + 空格 + 文本
        # 如果没有图片，则直接使用文本提示
        sanitized_prompt = str(prompt or "").strip()
        prompt_parts: List[str] = []
        if image_urls:
            prompt_parts.extend(image_urls)
        if sanitized_prompt:
            prompt_parts.append(sanitized_prompt)
        final_prompt = " ".join(part.strip().strip('`') for part in prompt_parts if part)
        if not final_prompt:
            error_message = "Prompt is empty, please provide description or image."
            result = [error_message]
            for _ in range(10):
                result.append(self._create_blank_image())
            return tuple(result)

        # size转换为API格式（官方示例使用1x1等写法）
        size_str = str(size or "1:1").strip()
        size_for_api = size_str.replace("：", ":").replace(":", "x")
        try:
            n_value = max(1, int(n))
        except (TypeError, ValueError):
            n_value = 1

        # 构建图生文/文生图统一请求体
        payload_dict = {
            "prompt": final_prompt,
            "model": model,
            "size": size_for_api,
            "n": n_value
        }
        payload = json.dumps(payload_dict)
        
        # 打印调试信息，检查请求体结构
        print(f"Request payload structure:")
        print(json.dumps(payload_dict, indent=2))
        
        # 设置请求头
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        preview_tensor: Optional[torch.Tensor] = None

        try:
            # 发送API请求
            conn = http.client.HTTPSConnection("api.apicore.ai")
            conn.request("POST", "/v1/images/generations", payload, headers)
            res = conn.getresponse()
            data = res.read()
            conn.close()
            
            # 解析响应
            response_data = data.decode("utf-8")
            response_json = None
            try:
                response_json = json.loads(response_data)
            except Exception:
                pass

            if response_json is not None:
                urls = self._extract_urls_from_payload(response_json)
            else:
                urls = self._extract_urls_from_payload(response_data)

            # 打印提取到的URL数量，用于调试
            print(f"Extracted {len(urls)} image URL(s) from API response")
            if urls:
                for i, url in enumerate(urls[:n_value], 1):
                    print(f"  URL {i}: {url}")

            # 下载所有图片，最多n_value个
            preview_tensors = []
            for idx, url in enumerate(urls[:n_value], 1):
                print(f"Downloading image {idx}/{min(len(urls), n_value)}: {url}")
                tensor = self._download_image_tensor(url)
                if tensor is not None:
                    preview_tensors.append(tensor)
                    print(f"  Successfully downloaded image {idx}")
                else:
                    print(f"  Failed to download image {idx}")
            
            # 如果图片数量不足，用占位图填充
            while len(preview_tensors) < n_value:
                preview_tensors.append(self._create_blank_image())
            
            # 如果图片数量超过n_value，只保留前n_value个
            preview_tensors = preview_tensors[:n_value]
            
            # 如果没有任何图片，至少返回一个占位图
            if not preview_tensors:
                preview_tensors.append(self._create_blank_image())
            
            # 构建返回元组：response + 最多10个图片
            result = [response_data]
            for i in range(10):
                if i < len(preview_tensors):
                    result.append(preview_tensors[i])
                else:
                    result.append(self._create_blank_image())
            
            return tuple(result)
        
        except Exception as e:
            error_message = f"API request failed: {str(e)}"
            print(error_message)
            # 返回错误消息和10个占位图
            result = [error_message]
            for _ in range(10):
                result.append(self._create_blank_image())
            return tuple(result)
    
# 确保节点能被正确识别
def NODE_CLASS_MAPPINGS():
    return {
        "APICore": APICoreNode,
    }

def NODE_DISPLAY_NAME_MAPPINGS():
    return {
        "APICore": "API Core",
    }
