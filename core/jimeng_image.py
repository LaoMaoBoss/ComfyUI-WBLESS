"""
Jimeng Image 4.0 API 节点
基于即梦4.0的图像生成能力，支持文生图、图像编辑及多图组合生成
使用火山引擎官方Python SDK
"""

import json
import time
import base64
from io import BytesIO
from PIL import Image
import torch
import numpy as np

# 导入火山引擎SDK（支持本地lib目录）
import sys
from pathlib import Path

# 添加lib目录到Python路径
WBLESS_ROOT = Path(__file__).resolve().parent.parent
VOLCENGINE_LIB_PATH = WBLESS_ROOT / "lib" / "volcengine"

if VOLCENGINE_LIB_PATH.exists():
    lib_path_str = str(WBLESS_ROOT / "lib")
    if lib_path_str not in sys.path:
        sys.path.insert(0, lib_path_str)
    print(f"[Jimeng Image 4.0] 已添加本地SDK路径: {lib_path_str}")

# 尝试导入火山引擎SDK
SDK_AVAILABLE = False
VisualService = None

try:
    from volcengine.visual.VisualService import VisualService
    SDK_AVAILABLE = True
    print("[Jimeng Image 4.0] 火山引擎SDK已加载（本地版本）")
except ImportError:
    try:
        # 尝试从系统安装的包导入
        import volcengine.visual.VisualService
        from volcengine.visual.VisualService import VisualService
        SDK_AVAILABLE = True
        print("[Jimeng Image 4.0] 火山引擎SDK已加载（系统版本）")
    except ImportError:
        print("[Jimeng Image 4.0] 火山引擎SDK未找到")
        print("[Jimeng Image 4.0] 请将volcengine包放入 lib/ 目录，或运行: pip install volcengine")

# 导入 cozy_comfyui 工具
from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY
from cozy_comfyui import InputType, deep_merge
from cozy_comfyui.lexicon import Lexicon
from server import PromptServer


class JimengImageNode(CozyBaseNode):
    """
    即梦 Image 4.0 API 节点
    支持文生图、图像编辑和多图组合生成
    """
    
    NAME = "Jimeng Image 4.0"
    
    @classmethod
    def INPUT_TYPES(cls) -> InputType:
        # 创建动态图像输入
        dyn_inputs = {"image_1": ("IMAGE", {"tooltip": "Image input. When connected, one more input slot is added."})}
        
        # 检测是否为新版ComfyUI并支持动态输入验证绕过
        try:
            import inspect
            stack = inspect.stack()
            if len(stack) > 2 and stack[2].function == 'get_input_info':
                # 绕过验证的容器类
                class ImageContainer:
                    def __contains__(self, item):
                        return item.startswith("image_")
                    
                    def __getitem__(self, key):
                        if key.startswith("image_"):
                            return ("IMAGE", {"tooltip": "Dynamic image input"})
                        raise KeyError(key)
                
                dyn_inputs = ImageContainer()
        except:
            # 如果出错，使用默认的静态定义
            pass
        
        d = super().INPUT_TYPES()
        
        # 将动态控件也加入optional
        if hasattr(dyn_inputs, '__getitem__') and hasattr(dyn_inputs, '__contains__'):
            # 如果是自定义容器类，转换为字典
            optional_inputs = {}
        else:
            # 如果是普通字典
            optional_inputs = dict(dyn_inputs) if isinstance(dyn_inputs, dict) else {"image_1": ("IMAGE", {"tooltip": "Image input"})}
        
        # 添加可能被隐藏的控件到optional
        optional_inputs.update({
            # 尺寸控制（根据size_mode动态显示）
            "size": ("INT", {"default": 4194304, "min": 1048576, "max": 16777216, "step": 1024}),
            "width": ("INT", {"default": 2048, "min": 512, "max": 4096, "step": 64}),
            "height": ("INT", {"default": 2048, "min": 512, "max": 4096, "step": 64}),
            
            # 水印设置（根据add_watermark动态显示）
            "watermark_position": (["right_bottom", "left_bottom", "left_top", "right_top"], {"default": "right_bottom"}),
            "watermark_language": (["chinese", "english"], {"default": "chinese"}),
            "watermark_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.1}),
            "watermark_text": ("STRING", {"default": "", "multiline": False}),
        })
        
        d = deep_merge(d, {
            "required": {
                # API 认证信息
                "access_key": ("STRING", {"default": "", "multiline": False}),
                "secret_key": ("STRING", {"default": "", "multiline": False}),
                "picgo_api_key": ("STRING", {"default": "", "multiline": False, "tooltip": "PicGo图片托管API密钥，用于上传输入图片"}),
                
                # 基础参数
                "prompt": ("STRING", {"default": "一幅美丽的风景画", "multiline": True}),
                "force_single": ("BOOLEAN", {"default": True}),
                "scale": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                
                # 控制参数（总是显示）
                "size_mode": (["auto", "custom_size", "custom_dimensions"], {"default": "auto"}),
                "add_watermark": ("BOOLEAN", {"default": False}),
                
                # 宽高比控制
                "min_ratio": ("FLOAT", {"default": 0.33, "min": 0.0625, "max": 16.0, "step": 0.01}),
                "max_ratio": ("FLOAT", {"default": 3.0, "min": 0.0625, "max": 16.0, "step": 0.01}),
                
                # 高级设置
                "timeout": ("INT", {"default": 300, "min": 30, "max": 600, "step": 10}),
                "poll_interval": ("INT", {"default": 5, "min": 1, "max": 30, "step": 1}),
            },
            "optional": optional_inputs
        })
        return Lexicon._parse(d)
    
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "run"
    OUTPUT_IS_LIST = (True,)
    
    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        """强制禁用缓存，确保每次都重新执行API调用"""
        return time.time()
    
    @classmethod
    @PromptServer.instance.routes.post("/wbless/check_jimeng_sdk")
    def check_sdk_status(cls, *args, **kwargs):
        """
        检查火山引擎SDK状态的API端点
        """
        try:
            if SDK_AVAILABLE and VisualService is not None:
                # 尝试创建一个VisualService实例来进一步验证
                test_service = VisualService()
                return {
                    "available": True,
                    "message": "火山引擎SDK状态正常",
                    "version": getattr(test_service, '__version__', 'unknown')
                }
            else:
                return {
                    "available": False,
                    "message": "火山引擎SDK未正确加载"
                }
        except Exception as e:
            return {
                "available": False,
                "message": f"SDK检查失败: {str(e)}"
            }
    
    def _init_visual_service(self, access_key, secret_key):
        """
        初始化火山引擎视觉服务
        """
        if not SDK_AVAILABLE or VisualService is None:
            error_msg = (
                "火山引擎SDK不可用！\n"
                "请尝试以下解决方案：\n"
                "1. 重启ComfyUI（SDK可能已自动安装）\n"
                "2. 手动安装：pip install volcengine\n"
                "3. 检查网络连接和权限"
            )
            raise ImportError(error_msg)
        
        # 基本的密钥格式验证
        if not access_key or len(access_key) < 10:
            raise ValueError("Access Key格式不正确，请检查是否完整输入")
        
        if not secret_key or len(secret_key) < 10:
            raise ValueError("Secret Key格式不正确，请检查是否完整输入")
        
        print(f"[Jimeng Image 4.0] 初始化SDK，Access Key: {access_key[:8]}...")
        
        visual_service = VisualService()
        visual_service.set_ak(access_key)
        visual_service.set_sk(secret_key)
        
        return visual_service
    
    def _upload_image_to_temp_url(self, image_tensor, api_key=""):
        """
        将图像张量上传到PicGo图片托管平台并返回公开URL
        
        使用PicGo API上传图片，支持base64格式上传
        API文档: https://www.picgo.net/api/1/upload
        """
        try:
            # 将张量转换为PIL图像
            if len(image_tensor.shape) == 4:
                image_tensor = image_tensor.squeeze(0)
            
            # 转换为numpy数组并调整范围
            image_np = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
            image_pil = Image.fromarray(image_np)
            
            # 如果图像有透明通道，转换为RGB模式（JPEG不支持透明度）
            if image_pil.mode == 'RGBA':
                # 创建白色背景
                background = Image.new('RGB', image_pil.size, (255, 255, 255))
                background.paste(image_pil, mask=image_pil.split()[-1])  # 使用alpha通道作为遮罩
                image_pil = background
            elif image_pil.mode != 'RGB':
                image_pil = image_pil.convert('RGB')
            
            # 转换为base64格式
            buffer = BytesIO()
            image_pil.save(buffer, format='JPEG', quality=95)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # 如果没有提供API密钥，直接返回None，不处理图片
            if not api_key:
                print("[Jimeng Image 4.0] 错误: 未提供PicGo API密钥，无法上传图片。即梦4.0只支持公开URL，请提供PicGo API密钥。")
                return None
            
            # 准备上传到PicGo
            print("[Jimeng Image 4.0] 正在上传图片到PicGo...")
            
            # PicGo API参数
            api_url = "https://www.picgo.net/api/1/upload"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "multipart/form-data"
            }
            
            # 准备multipart/form-data
            import requests
            files = {
                'source': ('image.jpg', buffer.getvalue(), 'image/jpeg')
            }
            
            # 可选参数
            data = {
                'format': 'json',  # 返回JSON格式
                'title': f'ComfyUI_Jimeng_{int(time.time())}',  # 自动生成标题
                'description': 'Uploaded by ComfyUI Jimeng Image 4.0'
            }
            
            # 发送上传请求
            response = requests.post(
                api_url,
                headers={"X-API-Key": api_key},  # 简化headers
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status_code') == 200 and 'image' in result:
                    image_url = result['image']['url']
                    print(f"[Jimeng Image 4.0] 图片上传成功: {image_url}")
                    return image_url
                else:
                    error_msg = result.get('error', {}).get('message', '未知错误')
                    print(f"[Jimeng Image 4.0] PicGo API返回错误: {error_msg}")
                    return None
            else:
                print(f"[Jimeng Image 4.0] PicGo上传失败，HTTP状态码: {response.status_code}")
                print(f"[Jimeng Image 4.0] 响应内容: {response.text}")
                return None
                
        except Exception as e:
            print(f"[Jimeng Image 4.0] 图片上传异常: {e}")
            return None
    
    def _submit_task(self, visual_service, payload):
        """
        使用SDK提交任务到即梦API
        """
        try:
            print(f"[Jimeng Image 4.0] 正在调用SDK提交任务...")
            print(f"[Jimeng Image 4.0] SDK类型: {type(visual_service)}")
            
            # 确保payload中的所有值都是正确的类型
            # 注意：image_urls必须保持为数组格式
            cleaned_payload = {}
            for key, value in payload.items():
                if key == "image_urls":
                    # image_urls必须保持为数组格式，不要转换为单个值
                    cleaned_payload[key] = value
                elif isinstance(value, list) and len(value) == 1:
                    cleaned_payload[key] = value[0]
                else:
                    cleaned_payload[key] = value
            
            print(f"[Jimeng Image 4.0] 清理后的payload: {cleaned_payload}")
            
            response = visual_service.cv_sync2async_submit_task(cleaned_payload)
            print(f"[Jimeng Image 4.0] SDK响应: {response}")
            return response
        except Exception as e:
            import traceback
            error_str = str(e)
            print(f"[Jimeng Image 4.0] 提交任务错误: {e}")
            print(f"[Jimeng Image 4.0] 错误详情: {traceback.format_exc()}")
            
            # 尝试解析错误信息
            if "Access Denied" in error_str:
                return {
                    "code": 50400, 
                    "message": "访问被拒绝：请检查API密钥是否正确，账户是否有足够余额，以及是否已开通即梦4.0服务，参考文档https://www.volcengine.com/docs/6444/79136"
                }
            elif "50400" in error_str:
                return {
                    "code": 50400,
                    "message": "认证失败：API密钥可能无效或已过期"
                }
            else:
                return {"code": -1, "message": str(e)}
    
    def _query_result(self, visual_service, task_id, watermark_config):
        """
        使用SDK查询任务结果
        """
        try:
            payload = {
                "req_key": "jimeng_t2i_v40",
                "task_id": task_id,
                "req_json": json.dumps(watermark_config, ensure_ascii=False)
            }
            response = visual_service.cv_sync2async_get_result(payload)
            return response
        except Exception as e:
            print(f"[Jimeng Image 4.0] 查询结果错误: {e}")
            return {"code": -1, "message": str(e)}
    
    def _base64_to_tensor(self, base64_string):
        """
        将base64图像字符串转换为张量
        """
        image_data = base64.b64decode(base64_string)
        image_pil = Image.open(BytesIO(image_data))
        
        # 确保是RGB格式
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')
        
        # 转换为张量
        image_np = np.array(image_pil).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_np).unsqueeze(0)
        
        return image_tensor
    
    def run(self, **kw):
        """
        主要的图像生成函数
        """
        try:
            # 从关键字参数中提取参数，并处理可能的列表格式
            def extract_param(key, default_value):
                """提取参数，处理列表格式"""
                value = kw.get(key, default_value)
                if isinstance(value, list) and len(value) > 0:
                    return value[0]
                return value
            
            access_key = extract_param("access_key", "")
            secret_key = extract_param("secret_key", "")
            picgo_api_key = extract_param("picgo_api_key", "")
            prompt = extract_param("prompt", "一幅美丽的风景画")
            force_single = extract_param("force_single", True)
            scale = extract_param("scale", 0.5)
            size_mode = extract_param("size_mode", "auto")
            size = extract_param("size", 4194304)
            width = extract_param("width", 2048)
            height = extract_param("height", 2048)
            min_ratio = extract_param("min_ratio", 0.33)
            max_ratio = extract_param("max_ratio", 3.0)
            add_watermark = extract_param("add_watermark", False)
            watermark_position = extract_param("watermark_position", "right_bottom")
            watermark_language = extract_param("watermark_language", "chinese")
            watermark_opacity = extract_param("watermark_opacity", 1.0)
            watermark_text = extract_param("watermark_text", "")
            timeout = extract_param("timeout", 300)
            poll_interval = extract_param("poll_interval", 5)
            
            # 确保关键参数是正确的类型
            prompt = str(prompt) if prompt else "一幅美丽的风景画"
            access_key = str(access_key) if access_key else ""
            secret_key = str(secret_key) if secret_key else ""
            
            # 验证API密钥
            if not access_key or not secret_key:
                raise ValueError("请提供有效的 Access Key 和 Secret Key")
            
            # 初始化火山引擎服务
            visual_service = self._init_visual_service(access_key, secret_key)
            
            # 检查是否有图片输入
            has_images = False
            for i in range(1, 11):
                image_key = f"image_{i}"
                if image_key in kw and kw[image_key] is not None:
                    has_images = True
                    break
            
            # 如果有图片输入但没有PicGo API密钥，返回错误
            if has_images and not picgo_api_key:
                print("[Jimeng Image 4.0] 错误: 检测到图片输入但未提供PicGo API密钥")
                print("[Jimeng Image 4.0] 即梦4.0只支持公开图片URL，必须使用PicGo上传图片")
                print("[Jimeng Image 4.0] 请在节点中填入PicGo API密钥，或移除图片输入")
                raise ValueError("即梦4.0需要PicGo API密钥来上传图片，请提供API密钥或移除图片输入")
            
            # 准备输入图像URL列表
            image_urls = []
            for i in range(1, 11):
                image_key = f"image_{i}"
                if image_key in kw and kw[image_key] is not None:
                    image_data = kw[image_key]
                    # 处理可能的列表格式
                    if isinstance(image_data, list) and len(image_data) > 0:
                        image_data = image_data[0]
                    # 上传图像到PicGo并获取URL
                    temp_url = self._upload_image_to_temp_url(image_data, picgo_api_key)
                    if temp_url:  # 只添加成功上传的URL
                        image_urls.append(temp_url)
                    else:
                        print(f"[Jimeng Image 4.0] 警告: 图片 {image_key} 上传失败，跳过")
            
            # 如果有图片输入但上传全部失败，返回错误
            if has_images and not image_urls:
                print("[Jimeng Image 4.0] 错误: 所有图片上传失败")
                raise ValueError("图片上传失败，请检查PicGo API密钥或网络连接")
            
            # 构建请求payload
            payload = {
                "req_key": "jimeng_t2i_v40",
                "prompt": prompt,
                "scale": scale,
                "force_single": force_single,
                "min_ratio": min_ratio,
                "max_ratio": max_ratio
            }
            
            # 添加图像URL（如果有）
            if image_urls:
                payload["image_urls"] = image_urls
            
            # 根据尺寸模式设置尺寸参数
            if size_mode == "custom_size":
                payload["size"] = size
            elif size_mode == "custom_dimensions":
                payload["width"] = width
                payload["height"] = height
            
            print(f"[Jimeng Image 4.0] 提交任务，提示词: {prompt}")
            print(f"[Jimeng Image 4.0] 输入图像数量: {len(image_urls)}")
            print(f"[Jimeng Image 4.0] Payload类型检查:")
            for key, value in payload.items():
                print(f"  {key}: {type(value)} = {value}")
            
            # 提交任务
            submit_result = self._submit_task(visual_service, payload)
            
            if submit_result.get("code") != 10000:
                raise ValueError(f"任务提交失败: {submit_result.get('message', 'Unknown error')}")
            
            task_id = submit_result["data"]["task_id"]
            print(f"[Jimeng Image 4.0] 任务已提交，Task ID: {task_id}")
            
            # 准备水印配置
            watermark_config = {
                "return_url": False  # 返回base64而不是URL
            }
            
            if add_watermark:
                position_map = {
                    "right_bottom": 0,
                    "left_bottom": 1,
                    "left_top": 2,
                    "right_top": 3
                }
                language_map = {
                    "chinese": 0,
                    "english": 1
                }
                
                watermark_config["logo_info"] = {
                    "add_logo": True,
                    "position": position_map[watermark_position],
                    "language": language_map[watermark_language],
                    "opacity": watermark_opacity
                }
                
                if watermark_text:
                    watermark_config["logo_info"]["logo_text_content"] = watermark_text
            
            # 轮询查询结果
            start_time = time.time()
            while time.time() - start_time < timeout:
                query_result = self._query_result(visual_service, task_id, watermark_config)
                
                if query_result.get("code") != 10000:
                    raise ValueError(f"查询结果失败: {query_result.get('message', 'Unknown error')}")
                
                status = query_result["data"]["status"]
                
                if status == "done":
                    print("[Jimeng Image 4.0] 任务完成")
                    
                    # 处理返回的图像
                    binary_data_base64 = query_result["data"].get("binary_data_base64", [])
                    if not binary_data_base64:
                        raise ValueError("API返回的图像数据为空")
                    
                    # 转换base64图像为张量
                    result_images = []
                    for i, base64_data in enumerate(binary_data_base64):
                        print(f"[Jimeng Image 4.0] 处理图像 {i+1}/{len(binary_data_base64)}")
                        image_tensor = self._base64_to_tensor(base64_data)
                        result_images.append(image_tensor)
                    
                    print(f"[Jimeng Image 4.0] 成功生成 {len(result_images)} 张图像")
                    return (result_images,)
                
                elif status == "generating":
                    print(f"[Jimeng Image 4.0] 任务处理中，等待 {poll_interval} 秒后重试...")
                    time.sleep(poll_interval)
                
                elif status == "in_queue":
                    print("[Jimeng Image 4.0] 任务排队中...")
                    time.sleep(poll_interval)
                
                elif status == "not_found":
                    raise ValueError("任务未找到，可能已过期")
                
                elif status == "expired":
                    raise ValueError("任务已过期，请重新提交")
                
                else:
                    print(f"[Jimeng Image 4.0] 未知状态: {status}")
                    time.sleep(poll_interval)
            
            raise TimeoutError(f"任务超时（{timeout}秒），请检查网络连接或增加超时时间")
            
        except Exception as e:
            print(f"[Jimeng Image 4.0] 错误: {str(e)}")
            # 返回一个空白图像作为错误处理
            error_image = torch.zeros((1, 512, 512, 3), dtype=torch.float32)
            return ([error_image],)

