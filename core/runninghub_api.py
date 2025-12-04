import http.client
import json
import logging
import time
import io
import tempfile
import os
from PIL import Image
import numpy as np
import torch
import requests
from cozy_comfyui.node import CozyBaseNode

# 配置日志
logger = logging.getLogger(__name__)

# RunningHub API 配置
API_HOST = "www.runninghub.cn"

class RunningHubApi(CozyBaseNode):
    """
    RunningHub API 节点
    用于与 RunningHub AI 应用进行交互，支持图片上传、任务提交和结果查询
    """
    NAME = "RunningHUB API"
    FUNCTION = "run"
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                # API 基础配置
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入您的 RunningHub API Key"
                }),
                "webapp_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入 WebApp ID"
                }),
                # 节点修改配置（从前端 JS 传入）
                "node_modifications": ("STRING", {
                    "default": "[]",
                    "multiline": True,
                    "placeholder": "节点修改配置（JSON 格式，由前端自动生成）"
                }),
                # 轮询超时时间（秒）
                "timeout": ("INT", {
                    "default": 600,
                    "min": 60,
                    "max": 3600,
                    "step": 60
                }),
            },
            # 不再需要 optional，因为图片输入是动态创建的
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "file_url")
    
    @classmethod
    def IS_CHANGED(s, **kwargs):
        """
        强制节点每次都重新执行，不使用缓存
        返回一个随机值，确保每次都被视为"已改变"
        """
        import random
        return random.random()

    def upload_image(self, api_key, image_tensor):
        """
        上传图片到 RunningHub 平台
        
        Args:
            api_key: API 密钥
            image_tensor: ComfyUI 的图片 tensor (B, H, W, C)
        
        Returns:
            上传成功后的文件名
        """
        logger.info("[RunningHub API] 开始上传图片")
        
        # 处理 ComfyUI 可能将参数包装成列表的情况
        if isinstance(image_tensor, list) and len(image_tensor) > 0:
            image_tensor = image_tensor[0]
        
        try:
            # 将 tensor 转换为 PIL Image
            # ComfyUI 的图片格式是 (B, H, W, C)，值范围是 0-1
            # 获取第一张图片并去除多余的维度
            image_np = image_tensor.cpu().numpy()
            
            # 如果是 4D 张量，取第一张图片
            if len(image_np.shape) == 4:
                image_np = image_np[0]
            
            # 去除可能存在的单维度
            image_np = np.squeeze(image_np)
            
            # 确保是 3D 张量 (H, W, C)
            if len(image_np.shape) != 3:
                raise ValueError(f"图片张量维度错误: {image_np.shape}，期望 (H, W, C)")
            
            # 转换为 uint8
            image_np = (image_np * 255).astype(np.uint8)
            pil_image = Image.fromarray(image_np)
            
            # 保存到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                pil_image.save(tmp_file, format='PNG')
                tmp_file_path = tmp_file.name
            
            try:
                # 上传文件
                url = f"https://{API_HOST}/task/openapi/upload"
                headers = {'Host': API_HOST}
                data = {
                    'apiKey': api_key,
                    'fileType': 'input'
                }
                
                with open(tmp_file_path, 'rb') as f:
                    files = {'file': f}
                    response = requests.post(url, headers=headers, files=files, data=data)
                
                result = response.json()
                logger.info(f"[RunningHub API] 上传结果: {result}")
                
                if result.get("code") == 0 and result.get("msg") == "success":
                    file_name = result.get("data", {}).get("fileName")
                    logger.info(f"[RunningHub API] 图片上传成功: {file_name}")
                    return file_name
                else:
                    raise Exception(f"上传失败: {result}")
                    
            finally:
                # 删除临时文件
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                    
        except Exception as e:
            logger.error(f"[RunningHub API] 图片上传失败: {e}")
            raise

    def submit_task(self, webapp_id, api_key, node_info_list):
        """
        提交任务到 RunningHub AI 应用
        
        Args:
            webapp_id: WebApp ID
            api_key: API 密钥
            node_info_list: 节点信息列表
        
        Returns:
            任务提交结果
        """
        logger.info("[RunningHub API] 开始提交任务")
        
        try:
            conn = http.client.HTTPSConnection(API_HOST)
            payload = json.dumps({
                "webappId": webapp_id,
                "apiKey": api_key,
                "nodeInfoList": node_info_list
            })
            headers = {
                'Host': API_HOST,
                'Content-Type': 'application/json'
            }
            
            # 输出详细的请求信息用于调试
            logger.debug(f"[RunningHub API] WebApp ID: {webapp_id}")
            logger.debug(f"[RunningHub API] 节点信息数量: {len(node_info_list)}")
            logger.debug(f"[RunningHub API] Payload: {payload}")
            
            conn.request("POST", "/task/openapi/ai-app/run", payload, headers)
            res = conn.getresponse()
            data = json.loads(res.read().decode("utf-8"))
            conn.close()
            
            logger.info(f"[RunningHub API] 任务提交结果: {data}")
            return data
            
        except Exception as e:
            logger.error(f"[RunningHub API] 任务提交失败: {e}")
            raise

    def query_task_outputs(self, task_id, api_key):
        """
        查询任务状态和生成结果
        
        Args:
            task_id: 任务 ID
            api_key: API 密钥
        
        Returns:
            任务查询结果
        """
        try:
            conn = http.client.HTTPSConnection(API_HOST)
            payload = json.dumps({
                "apiKey": api_key,
                "taskId": task_id
            })
            headers = {
                'Host': API_HOST,
                'Content-Type': 'application/json'
            }
            
            conn.request("POST", "/task/openapi/outputs", payload, headers)
            res = conn.getresponse()
            data = json.loads(res.read().decode("utf-8"))
            conn.close()
            
            return data
            
        except Exception as e:
            logger.error(f"[RunningHub API] 查询任务失败: {e}")
            raise

    def download_image(self, url):
        """
        从 URL 下载图片并转换为 ComfyUI tensor 格式
        
        Args:
            url: 图片 URL
        
        Returns:
            ComfyUI 格式的图片 tensor (B, H, W, C)
        """
        logger.info(f"[RunningHub API] 开始下载图片: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # 将下载的内容转换为 PIL Image
            image = Image.open(io.BytesIO(response.content))
            
            # 转换为 RGB（如果是 RGBA 或其他格式）
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 转换为 numpy 数组
            image_np = np.array(image).astype(np.float32) / 255.0
            
            # 转换为 torch tensor 并添加 batch 维度
            image_tensor = torch.from_numpy(image_np)[None,]
            
            logger.info(f"[RunningHub API] 图片下载成功，尺寸: {image_tensor.shape}")
            return image_tensor
            
        except Exception as e:
            logger.error(f"[RunningHub API] 图片下载失败: {e}")
            raise

    def run(self, api_key, webapp_id, node_modifications, timeout, **kwargs):
        """
        主执行函数
        
        Args:
            api_key: API 密钥
            webapp_id: WebApp ID
            node_modifications: 节点修改配置（JSON 字符串）
            timeout: 轮询超时时间（秒）
            **kwargs: 动态图片输入，格式为 image_{nodeId}_{fieldName}
        
        Returns:
            (生成的图片 tensor, 文件 URL)
        """
        logger.info("[RunningHub API] ========== 开始执行 ==========")
        
        # 处理 ComfyUI 可能将参数包装成列表的情况
        if isinstance(webapp_id, list) and len(webapp_id) > 0:
            webapp_id = webapp_id[0]
        if isinstance(api_key, list) and len(api_key) > 0:
            api_key = api_key[0]
        if isinstance(node_modifications, list) and len(node_modifications) > 0:
            node_modifications = node_modifications[0]
        if isinstance(timeout, list) and len(timeout) > 0:
            timeout = timeout[0]
        
        try:
            # 解析节点修改配置
            try:
                # 检查 node_modifications 是否已经是 list（ComfyUI 可能会自动解析）
                if isinstance(node_modifications, list):
                    node_info_list = node_modifications
                elif isinstance(node_modifications, str):
                    node_info_list = json.loads(node_modifications)
                else:
                    raise Exception(f"node_modifications 类型错误: {type(node_modifications)}")
                
                logger.info(f"[RunningHub API] 加载了 {len(node_info_list)} 个节点配置")
            except json.JSONDecodeError as e:
                logger.error(f"[RunningHub API] 节点配置解析失败: {e}")
                raise Exception(f"节点配置格式错误: {e}")
            
            # 处理动态图片输入
            # kwargs 中的键格式为 image_{nodeId}_{fieldName}
            for input_name, image_tensor in kwargs.items():
                if input_name.startswith("image_") and image_tensor is not None:
                    # 解析输入名称，提取 nodeId 和 fieldName
                    # 格式: image_{nodeId}_{fieldName}
                    parts = input_name.split("_", 2)  # 分割为 ["image", nodeId, fieldName]
                    if len(parts) >= 3:
                        node_id = parts[1]
                        field_name = parts[2]
                        
                        logger.info(f"[RunningHub API] 上传图片: 节点 {node_id}")
                        
                        # 上传图片
                        uploaded_file_name = self.upload_image(api_key, image_tensor)
                        
                        # 查找并更新对应的节点
                        updated = False
                        for node in node_info_list:
                            if node.get("nodeId") == node_id and node.get("fieldName") == field_name:
                                node["fieldValue"] = uploaded_file_name
                                logger.info(f"[RunningHub API] 图片已上传: {uploaded_file_name}")
                                updated = True
                                break
                        
                        if not updated:
                            logger.warning(f"[RunningHub API] 未找到匹配的节点: {node_id}/{field_name}")
            
            # 提交任务
            submit_result = self.submit_task(webapp_id, api_key, node_info_list)
            
            # 检查提交结果
            if submit_result.get("code") != 0:
                error_msg = f"任务提交失败: {submit_result}"
                logger.error(f"[RunningHub API] {error_msg}")
                raise Exception(error_msg)
            
            task_id = submit_result["data"]["taskId"]
            logger.info(f"[RunningHub API] 任务提交成功，Task ID: {task_id}")
            
            # 检查节点错误
            prompt_tips_str = submit_result["data"].get("promptTips")
            if prompt_tips_str:
                try:
                    prompt_tips = json.loads(prompt_tips_str)
                    node_errors = prompt_tips.get("node_errors", {})
                    if node_errors:
                        logger.warning(f"[RunningHub API] 节点错误信息: {node_errors}")
                        for node_id, err in node_errors.items():
                            logger.warning(f"[RunningHub API] 节点 {node_id} 错误: {err}")
                except Exception as e:
                    logger.warning(f"[RunningHub API] 无法解析 promptTips: {e}")
            
            # 轮询查询任务状态
            logger.info("[RunningHub API] 开始轮询任务状态")
            start_time = time.time()
            poll_interval = 5  # 每 5 秒查询一次
            
            while True:
                # 检查超时
                if time.time() - start_time > timeout:
                    error_msg = f"任务超时（超过 {timeout} 秒）"
                    logger.error(f"[RunningHub API] {error_msg}")
                    raise Exception(error_msg)
                
                # 查询任务状态
                outputs_result = self.query_task_outputs(task_id, api_key)
                code = outputs_result.get("code")
                msg = outputs_result.get("msg")
                data = outputs_result.get("data")
                
                if code == 0 and data:  # 任务成功完成
                    file_url = data[0].get("fileUrl")
                    logger.info(f"[RunningHub API] 🎉 任务完成！生成结果: {file_url}")
                    
                    # 下载生成的图片
                    result_image = self.download_image(file_url)
                    
                    logger.info("[RunningHub API] ========== RunningHub API 节点执行完成 ==========")
                    return (result_image, file_url)
                    
                elif code == 805:  # 任务失败
                    failed_reason = data.get("failedReason") if data else None
                    error_msg = "任务失败"
                    if failed_reason:
                        error_msg += f": 节点 {failed_reason.get('node_name')} - {failed_reason.get('exception_message')}"
                        logger.error(f"[RunningHub API] {error_msg}")
                        logger.error(f"[RunningHub API] Traceback: {failed_reason.get('traceback')}")
                    else:
                        logger.error(f"[RunningHub API] {error_msg}: {outputs_result}")
                    raise Exception(error_msg)
                    
                elif code == 804:  # 运行中
                    logger.info("[RunningHub API] ⏳ 任务运行中...")
                    
                elif code == 813:  # 排队中
                    logger.info("[RunningHub API] ⏳ 任务排队中...")
                    
                else:  # 未知状态
                    logger.warning(f"[RunningHub API] ⚠️ 未知状态: {outputs_result}")
                
                # 等待后继续查询
                time.sleep(poll_interval)
                
        except Exception as e:
            logger.error(f"[RunningHub API] 执行失败: {e}")
            raise

NODE_CLASS_MAPPINGS = {
    "RunningHUB API": RunningHubApi
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RunningHUB API": "RunningHUB API"
}
