from typing import Any, Dict, Optional, List
import time
import json
from io import BytesIO

import numpy as np
from PIL import Image
import torch

from cozy_comfyui.node import CozyBaseNode

MAX_INPUTS = 64

class APICoreRustFSNode(CozyBaseNode):
    """
    API核心节点 - 支持图片分析和API调用
    
    这个节点获取输入图片的URL，然后直接发送API请求进行处理。
    """
    NAME = "API Core-RustFS"
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
                "endpoint_url": ("STRING", {"default": "", "multiline": False, "tooltip": "必填：自定义API Endpoint URL"}),
                "aws_access_key_id": ("STRING", {"default": "", "multiline": False, "tooltip": "必填：AWS Access Key ID"}),
                "aws_secret_access_key": ("STRING", {"default": "", "multiline": False, "tooltip": "必填：AWS Secret Access Key"}),
                "bucket_name": ("STRING", {"default": "", "multiline": False, "tooltip": "必填：RustFS Bucket 名称"}),
                "model": ("STRING", {"default": "gemini-3-pro-image-preview", "tooltip": "模型名称，将与API返回的列表同步，亦可手动输入"}),
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

    def _create_rustfs_client(self, endpoint_url: str, access_key: str, secret_key: str):
        """
        创建 RustFS (S3 兼容) 客户端连接
        """
        if not endpoint_url or not access_key or not secret_key:
            raise ValueError("RustFS连接需要 endpoint_url / aws_access_key_id / aws_secret_access_key 均为非空")

        try:
            import boto3
            from botocore.client import Config
        except ImportError as exc:
            raise ImportError("未安装 boto3 或 botocore，无法连接 RustFS，请先安装依赖：pip install boto3 botocore") from exc

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

        return client

    def _upload_tensor_to_rustfs(self, client, bucket_name: str, endpoint_url: str, key: str, tensor: torch.Tensor) -> str:
        """
        通过 RustFS 预签名URL上传图片并返回可访问的URL
        """
        if not bucket_name:
            raise ValueError("bucket_name 不能为空")

        pil_image = self._tensor_to_pil(tensor)
        buffer = BytesIO()
        pil_image.save(buffer, format="PNG")
        payload = buffer.getvalue()

        presigned_url = client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": bucket_name, "Key": key},
            ExpiresIn=600
        )

        import urllib.request

        request = urllib.request.Request(
            presigned_url,
            data=payload,
            method="PUT",
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(payload)),
            }
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status not in (200, 201, 204):
                raise ValueError(f"RustFS上传失败，状态码: {status}")

        # 上传成功后生成 GET 预签名链接，默认10分钟有效
        presigned_get_url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket_name, "Key": key},
            ExpiresIn=600
        )

        return presigned_get_url

    def run(self, prompt, api_key, endpoint_url, aws_access_key_id, aws_secret_access_key, bucket_name,
            model, size, n, unique_id=None, extra_pnginfo=None, **kw) -> tuple:
        # 处理列表格式的输入参数
        if isinstance(prompt, list) and len(prompt) > 0:
            prompt = prompt[0]
        if isinstance(api_key, list) and len(api_key) > 0:
            api_key = api_key[0]
        if isinstance(endpoint_url, list) and len(endpoint_url) > 0:
            endpoint_url = endpoint_url[0]
        if isinstance(aws_access_key_id, list) and len(aws_access_key_id) > 0:
            aws_access_key_id = aws_access_key_id[0]
        if isinstance(aws_secret_access_key, list) and len(aws_secret_access_key) > 0:
            aws_secret_access_key = aws_secret_access_key[0]
        if isinstance(bucket_name, list) and len(bucket_name) > 0:
            bucket_name = bucket_name[0]
        if isinstance(model, list) and len(model) > 0:
            model = model[0]
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
        
        endpoint_url_value = (endpoint_url or "").strip()
        aws_access_key_id_value = (aws_access_key_id or "").strip()
        aws_secret_access_key_value = (aws_secret_access_key or "").strip()
        bucket_name_value = (bucket_name or "").strip()

        try:
            rustfs_client = self._create_rustfs_client(
                endpoint_url_value,
                aws_access_key_id_value,
                aws_secret_access_key_value,
            )
            if not bucket_name_value:
                raise ValueError("请填写 RustFS Bucket 名称 (bucket_name)")
            print("[API Core-RustFS] RustFS客户端初始化成功")
        except Exception as exc:
            error_message = f"RustFS连接失败: {exc}"
            print(error_message)
            result = [error_message]
            for _ in range(10):
                result.append(self._create_blank_image())
            return tuple(result)
        # 收集所有有效的图片输入URL
        image_urls = []
        upload_index = 1
        timestamp_prefix = int(time.time() * 1000)

        def process_image_source(source_value, idx_label: str):
            nonlocal upload_index
            tensor = None
            try:
                tensor = self._extract_tensor(source_value)
            except Exception as exc:
                print(f"[API Core-RustFS] 无法提取tensor ({idx_label}): {exc}")

            if tensor is not None:
                key = f"apicore/{timestamp_prefix}_{upload_index}.png"
                try:
                    remote_url = self._upload_tensor_to_rustfs(
                        rustfs_client,
                        bucket_name_value,
                        endpoint_url_value,
                        key,
                        tensor
                    )
                    image_urls.append(remote_url)
                    upload_index += 1
                    print(f"[API Core-RustFS] 已上传参考图 {idx_label} -> {remote_url}")
                    return
                except Exception as exc:
                    print(f"[API Core-RustFS] 上传参考图失败 ({idx_label}): {exc}")
            else:
                print(f"[API Core-RustFS] 无法从输入中提取图片数据 ({idx_label})")

        for i in range(1, MAX_INPUTS + 1):
            input_name = f"image_{i}"
            if input_name in kw:
                value = kw[input_name]
                if isinstance(value, list) and len(value) > 0:
                    process_image_source(value[0], f"{input_name}[0]")
                elif value is not None:
                    process_image_source(value, input_name)
        
        sanitized_prompt = str(prompt or "").strip()
        prompt_parts: List[str] = []
        if image_urls:
            prompt_parts.extend(image_urls)
        if sanitized_prompt:
            prompt_parts.append(sanitized_prompt)
        final_prompt = " ".join(part.strip().strip('`') for part in prompt_parts if part)
        if not final_prompt:
            error_message = "Prompt is empty, please provide description or remote image."
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
        "APICoreRustFS": APICoreRustFSNode,
    }

def NODE_DISPLAY_NAME_MAPPINGS():
    return {
        "APICoreRustFS": "API Core-RustFS",
    }
