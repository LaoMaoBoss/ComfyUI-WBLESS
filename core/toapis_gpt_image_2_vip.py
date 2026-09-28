"""
ToAPIs GPT Image 2 VIP 图像生成节点
对接 ToAPIs 统一图像生成接口，通过 model=gpt-image-2-vip 生成图像：
- 参数与 gpt-image-2 一致，但支持全部常用宽高比（含任意 宽:高）
- 支持文生图、单图参考、多图参考
- 异步任务：提交任务 -> 轮询任务 -> 下载结果
- 参考图仅支持 URL，ComfyUI 本地图片会先上传到 ToAPIs /v1/uploads/images 换取 URL
"""

import http.client
import json
import logging
import os
import ssl
import time
import random
import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, quote

import numpy as np
from PIL import Image
import torch

from cozy_comfyui.node import CozyBaseNode
from cozy_comfyui import InputType, deep_merge
from cozy_comfyui.lexicon import Lexicon

logger = logging.getLogger(__name__)

# ==============================================================================
# === 常量 ===
# ==============================================================================

DEFAULT_MODEL = "gpt-image-2-vip"
# 默认使用国际站；中国大陆用户可在节点里改为 https://toapis.cn
DEFAULT_API_BASE = "https://toapis.com"
PATH_GENERATIONS = "/v1/images/generations"
PATH_UPLOAD_IMAGES = "/v1/uploads/images"

# 文档给出的预设比例（含 auto）
PRESET_SIZES = [
    "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "21:9", "9:21", "auto",
]
RESOLUTIONS = ["1k", "2k", "4k"]
QUALITIES = ["low", "medium", "high"]
BACKGROUNDS = ["auto", "transparent", "opaque"]

# gpt-image-2 系列官方 prompt 上限
MAX_PROMPT_LENGTH = 32000
# 参考图动态端口上限（与前端保持一致）
MAX_IMAGE_INPUTS = 10
# ToAPIs 上传接口的文件大小上限（10MB）
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# 任意比例时的宽高比上限
MAX_CUSTOM_RATIO = 3.0
# 环境变量名：便于不把密钥写进工作流
API_KEY_ENV = "TOAPIS_API_KEY"
API_BASE_ENV = "TOAPIS_API_BASE"

_SIZE_RATIO_RE = re.compile(r"^(\d+)\s*:\s*(\d+)$")
_TASK_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._~-]")

# 完成任务时可能的图片 URL 容器字段（按优先级）
_URL_CONTAINER_KEYS = ("result", "data", "output", "outputs", "images")
_URL_ITEM_KEYS = ("url", "image_url", "imageUrl")
_B64_ITEM_KEYS = ("b64_json", "base64", "image_base64", "binary_data_base64")


# ==============================================================================
# === 工具函数 ===
# ==============================================================================

def _extract_param(value: Any, default: Any = None) -> Any:
    """兼容 CozyBaseNode 的 INPUT_IS_LIST 行为：把 [x] 还原成 x。"""
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value if value is not None else default


def _as_int(value: Any, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    """把输入安全地转成 int，并做区间裁剪。"""
    try:
        result = int(float(_extract_param(value, default)))
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _as_float(value: Any, default: float, minimum: Optional[float] = None, maximum: Optional[float] = None) -> float:
    """把输入安全地转成 float，并做区间裁剪。"""
    try:
        result = float(_extract_param(value, default))
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _as_str(value: Any, default: str = "") -> str:
    """把输入安全地转成去空白的字符串。"""
    value = _extract_param(value, default)
    if value is None:
        return default
    return str(value).strip()


def _normalize_api_base(raw: str) -> str:
    """规范化 Base URL：补协议、去尾部斜杠、支持直接填完整 endpoint。"""
    base = (raw or "").strip() or os.environ.get(API_BASE_ENV, "").strip() or DEFAULT_API_BASE
    base = base.rstrip("/")
    if not base:
        base = DEFAULT_API_BASE
    if "://" not in base:
        base = f"https://{base}"
    # 允许用户把完整路径也填进来，这里统一裁掉，避免拼出 /v1/images/generations/v1/images/generations
    for suffix in (PATH_GENERATIONS, PATH_UPLOAD_IMAGES):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    # 只填到 /v1 也接受
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base.rstrip("/")


def _encode_path_segment(segment: str) -> str:
    """对 URL 路径片段做安全编码，防止 task_id 中的特殊字符破坏路径。"""
    return quote(str(segment), safe="")


def _normalize_size(raw: str) -> str:
    """
    校验并规范化 size 参数。

    - 预设比例直接放行（21:9 / 9:21 本身超过 3:1，属官方预设，不能按任意比例卡）
    - 任意 宽:高 必须为正整数，且宽高比不超过 3:1
    """
    size = _as_str(raw, "1:1") or "1:1"
    size = size.replace("：", ":")  # 中文冒号容错
    if size.lower() == "auto" or size in PRESET_SIZES:
        return size
    match = _SIZE_RATIO_RE.match(size)
    if not match:
        raise ValueError(
            f"size 参数非法: {size}。请使用预设比例（{'/'.join(PRESET_SIZES)}）"
            f"或任意 宽:高 格式（如 7:4）"
        )
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError(f"size 参数非法: {size}，宽高必须为正整数")
    ratio = max(width, height) / float(min(width, height))
    if ratio > MAX_CUSTOM_RATIO + 1e-9:
        raise ValueError(f"size 宽高比超过 {MAX_CUSTOM_RATIO:g}:1: {size}")
    return f"{width}:{height}"


def _decode_body(raw: bytes) -> str:
    """把响应体解码成文本，优先 UTF-8。"""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _preview(text: str, limit: int = 600) -> str:
    """截断长文本，避免日志/报错信息被巨量响应淹没。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _looks_like_error(payload: Any) -> Optional[str]:
    """从响应里提取 API 侧的错误描述。"""
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    error = payload.get("error")
    if isinstance(error, dict):
        inner = error.get("message")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
        return str(error)[:400]
    if isinstance(error, str) and error.strip():
        return error.strip()
    return None


def _image_input_spec(index: int) -> Tuple[str, Dict[str, Any]]:
    """单个参考图槽位的 ComfyUI 类型定义。"""
    return ("IMAGE", {
        "lazy": False,
        "tooltip": f"参考图 {index}。连上后会自动追加下一个端口，最多 {MAX_IMAGE_INPUTS} 张。",
    })


# ==============================================================================
# === 参考图端口解析 ===
# ==============================================================================

# 内部哨兵值：区分「取到 None」与「没取到」
_MISSING = object()


class OptionalImageInputs(dict):
    """
    参考图端口映射：只"显示"image_1，但对任意 image_N 都能给出类型定义。

    为什么需要这个：
    - ComfyUI 会把 optional 里声明的输入全部渲染出来，所以一次性声明
      image_1..image_10 会变成十个端口全堆在节点上，失去"连一个补一个"的体验；
    - 但如果只声明 image_1，ComfyUI（校验 / 执行期解析输入类型时）又会把
      image_2..image_N 当成未知输入丢弃，参考图连线静默失效。

    所以这里让 image_1 正常出现在迭代结果里（UI 只画一个端口），
    同时让 __contains__ / get / __getitem__ 对任意 image_N 都返回类型定义
    （校验和执行期解析都能通过）。前端负责 addInput 出真正的端口。
    """

    def __init__(self) -> None:
        super().__init__({"image_1": _image_input_spec(1)})

    @staticmethod
    def _slot_index(key: Any) -> Optional[int]:
        """把 image_N 解析成序号 N，非法返回 None。"""
        if not isinstance(key, str) or not key.startswith("image_"):
            return None
        suffix = key[len("image_"):]
        if not suffix.isdigit():
            return None
        index = int(suffix)
        return index if 1 <= index <= MAX_IMAGE_INPUTS else None

    def __contains__(self, key: Any) -> bool:
        return self._slot_index(key) is not None or super().__contains__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        # 任意 image_N 都要能取到类型定义，否则执行期该输入会被丢弃
        if self._slot_index(key) is not None and not super().__contains__(key):
            return _image_input_spec(int(str(key)[len("image_"):]))
        return super().get(key, default)

    def __getitem__(self, key: Any) -> Any:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value


# ==============================================================================
# === 节点 ===
# ==============================================================================

class ToApisGptImage2VipNode(CozyBaseNode):
    """
    ToAPIs GPT Image 2 VIP 图像生成

    通过 ToAPIs 统一的 /v1/images/generations 接口调用 gpt-image-2-vip。
    参考图只能是 http(s) URL，因此本地 IMAGE 会先经 /v1/uploads/images 换成 URL。
    """

    NAME = "ToAPIs GPT Image 2 VIP"
    FUNCTION = "run"
    DESCRIPTION = "ToAPIs GPT Image 2 VIP image generation (text-to-image / multi-reference image-to-image)."

    @classmethod
    def INPUT_TYPES(cls) -> InputType:
        d = super().INPUT_TYPES()
        optional_inputs: Dict[str, Any] = OptionalImageInputs()

        d = deep_merge(d, {
            "required": {
                # ---- 鉴权与地址 ----
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": f"ToAPIs API Key；留空则读取环境变量 {API_KEY_ENV}",
                    "tooltip": f"ToAPIs Bearer Token。留空时自动读取环境变量 {API_KEY_ENV}。",
                }),
                "api_base": ("STRING", {
                    "default": DEFAULT_API_BASE,
                    "multiline": False,
                    "placeholder": "https://toapis.com（中国大陆建议改 https://toapis.cn）",
                    "tooltip": "ToAPIs Base URL。中国大陆用户请使用 https://toapis.cn。",
                }),

                # ---- 基础参数 ----
                "prompt": ("STRING", {
                    "default": "白色背景上的红色圆形，简洁测试图",
                    "multiline": True,
                    "placeholder": "图像生成的文本描述（最长 32000 字符）",
                    "tooltip": "图像生成的文本描述，最长 32000 字符。",
                }),
                "model": (["gpt-image-2-vip"], {
                    "default": DEFAULT_MODEL,
                    "tooltip": "图像生成模型名称，本节点固定为 gpt-image-2-vip。",
                }),

                # ---- 尺寸 ----
                "size": (PRESET_SIZES, {
                    "default": "1:1",
                    "tooltip": "输出图像比例。preset 覆盖全部常用宽高比；需要 7:4 这类任意比例时改用 custom_size。",
                }),
                "custom_size": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "任意比例，如 7:4 或 1:3（留空则使用上方预设）",
                    "tooltip": "任意 宽:高 比例，非空时覆盖上方预设。宽高比最大 3:1，实际像素由 resolution 推导。",
                }),
                "resolution": (RESOLUTIONS, {
                    "default": "1k",
                    "tooltip": "输出分辨率档位：1k / 2k / 4k（4K 长边最长 3840 像素）。",
                }),

                # ---- 画质 ----
                "quality": (QUALITIES, {
                    "default": "medium",
                    "tooltip": "图片质量：low 快速省钱、medium 平衡、high 最高精度。",
                }),
                "background": (BACKGROUNDS, {
                    "default": "auto",
                    "tooltip": "背景样式。transparent 建议搭配 PNG 使用；auto 时不向上游发送该参数。",
                }),
                "n": ("INT", {
                    "default": 1, "min": 1, "max": 10, "step": 1,
                    "tooltip": "生成图像数量。",
                }),

                # ---- 轮询控制 ----
                "timeout": ("INT", {
                    "default": 600, "min": 30, "max": 3600, "step": 30,
                    "tooltip": "轮询任务结果的总超时时间（秒）。",
                }),
                "poll_interval": ("INT", {
                    "default": 5, "min": 1, "max": 60, "step": 1,
                    "tooltip": "轮询任务结果的间隔（秒）。",
                }),
            },
            "optional": optional_inputs,
        })
        return Lexicon._parse(d)

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "response")
    OUTPUT_IS_LIST = (True, False)

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        """强制禁用缓存，确保每次都真正调用 API。"""
        return time.time()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_api_key(raw_key: str) -> str:
        """API Key 优先取节点输入，其次取环境变量。"""
        api_key = (raw_key or "").strip() or os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            raise ValueError(
                f"请填写 ToAPIs API Key（节点参数 api_key），或设置环境变量 {API_KEY_ENV}"
            )
        return api_key

    @staticmethod
    def _auth_header(api_key: str) -> str:
        """允许用户填裸 Key 或已经带 Bearer 前缀。"""
        return api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        """构建 SSL 上下文，兼容企业代理/自签证书链导致的证书校验失败。"""
        context = ssl.create_default_context()
        flag = os.environ.get("WBLESS_SSL_VERIFY", "1").strip().lower()
        if flag in ("0", "false", "no", "off"):
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def _request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: int = 120,
    ) -> Tuple[int, str, Dict[str, str]]:
        """
        基于 http.client 的轻量 HTTP 请求（本插件统一风格，避免额外依赖）。

        返回 (status_code, text_body, response_headers)。
        """
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"不支持的 URL 协议: {url}")

        is_https = parts.scheme == "https"
        port = parts.port or (443 if is_https else 80)
        conn_class = http.client.HTTPSConnection if is_https else http.client.HTTPConnection

        host_label = parts.hostname or ""
        if parts.port:
            host_label = f"{host_label}:{parts.port}"

        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        request_headers = dict(headers or {})
        # Host 头显式声明，避免部分网关因缺失 Host 直接拒绝
        request_headers.setdefault("Host", host_label)
        request_headers.setdefault("Accept", "application/json")

        if is_https:
            conn = conn_class(parts.hostname, port, timeout=timeout, context=self._ssl_context())
        else:
            conn = conn_class(parts.hostname, port, timeout=timeout)

        try:
            conn.request(method, path, body=body, headers=request_headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, _decode_body(raw), {k.lower(): v for k, v in response.getheaders()}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _request_json(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: int = 120,
    ) -> Tuple[int, Any, str, Dict[str, str]]:
        """请求并尝试解析 JSON；解析失败时把原始文本一并返回。"""
        status, text, response_headers = self._request(method, url, headers, body, timeout)
        try:
            payload = json.loads(text) if text else {}
        except ValueError:
            payload = None
        return status, payload, text, response_headers

    @staticmethod
    def _raise_http_error(status: int, payload: Any, text: str, action: str) -> None:
        """把 HTTP 错误翻译成对用户有用的中文提示。"""
        detail = _looks_like_error(payload) or _preview(text)
        if status == 401:
            hint = "API Key 无效或未携带鉴权"
        elif status == 402:
            hint = "账户余额不足"
        elif status == 403:
            hint = "无权访问该模型或接口"
        elif status == 404:
            hint = "接口地址不存在，请检查 api_base 是否正确"
        elif status == 413:
            hint = "请求体过大（参考图超过 10MB）"
        elif status == 429:
            hint = "触发限流，请稍后重试"
        elif 500 <= status < 600:
            hint = "ToAPIs 服务端错误"
        else:
            hint = "请求失败"
        raise RuntimeError(f"{action}失败：HTTP {status}（{hint}）{f' - {detail}' if detail else ''}")

    # ------------------------------------------------------------------
    # 图像编解码
    # ------------------------------------------------------------------

    def _tensor_to_pil(self, image_tensor: Any) -> Image.Image:
        """把 ComfyUI 的 IMAGE tensor 转成 PIL Image（保留 alpha）。"""
        if isinstance(image_tensor, (list, tuple)):
            if not image_tensor:
                raise ValueError("图像输入为空")
            image_tensor = image_tensor[0]

        if not isinstance(image_tensor, torch.Tensor):
            image_tensor = torch.as_tensor(image_tensor)

        tensor = image_tensor.detach().cpu()
        if tensor.ndim == 4:
            tensor = tensor[0]
        if tensor.ndim == 2:
            tensor = tensor.unsqueeze(-1)
        if tensor.ndim != 3:
            raise ValueError(f"图像张量维度错误: {tuple(tensor.shape)}")

        channels = tensor.shape[-1]
        if channels == 1:
            mode = "L"
        elif channels == 2:
            # 灰度 + alpha
            mode = "LA"
        elif channels == 3:
            mode = "RGB"
        elif channels >= 4:
            mode = "RGBA"
        else:
            raise ValueError(f"不支持的通道数: {channels}")

        array = tensor.clamp(0.0, 1.0).mul(255).round().to(torch.uint8).numpy()
        if channels > 4:
            array = array[..., :4]
        # LA 需要先降成二维 + alpha 才能被 PIL 直接接受
        if mode == "LA":
            array = array[..., :2]
        return Image.fromarray(array, mode=mode)

    @staticmethod
    def _pil_to_png_bytes(image: Image.Image) -> bytes:
        """编码为 PNG（无损，保留透明通道）。"""
        buffer = BytesIO()
        image.save(buffer, format="PNG", compress_level=6)
        return buffer.getvalue()

    @staticmethod
    def _pil_to_jpeg_bytes(image: Image.Image, quality: int = 92) -> bytes:
        """编码为 JPEG（超出 10MB 时作为降级方案，压掉 alpha）。"""
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()

    def _encode_upload(self, image_tensor: Any, slot: int) -> Tuple[bytes, str, str, bool]:
        """
        把输入图像编码为待上传的字节流。

        返回 (bytes, filename, mime_type, fell_back_to_jpeg)。
        优先 PNG 以保留透明通道；超过 ToAPIs 10MB 限制时降级为 JPEG。
        """
        pil_image = self._tensor_to_pil(image_tensor)
        data = self._pil_to_png_bytes(pil_image)
        if len(data) <= MAX_UPLOAD_BYTES:
            return data, f"ref_image_{slot}.png", "image/png", False

        logger.warning(
            f"[ToAPIs GPT Image 2 VIP] 参考图 {slot} PNG 体积 {len(data) / 1048576:.2f}MB "
            f"超过 10MB 限制，降级为 JPEG 上传（透明通道会丢失）"
        )
        data = self._pil_to_jpeg_bytes(pil_image)
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(
                f"参考图 {slot} 编码后仍有 {len(data) / 1048576:.2f}MB，超过 ToAPIs 10MB 上传限制，请先缩小图片"
            )
        return data, f"ref_image_{slot}.jpg", "image/jpeg", True

    @staticmethod
    def _bytes_to_tensor(data: bytes) -> torch.Tensor:
        """把图片字节流转成 ComfyUI IMAGE tensor（有 alpha 则保留 4 通道）。"""
        image = Image.open(BytesIO(data))
        # 动图/多帧只取第一帧
        try:
            image.seek(0)
        except Exception:
            pass
        if image.mode not in ("RGB", "RGBA", "L", "LA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        array = np.array(image).astype(np.float32) / 255.0
        if array.ndim == 2:
            array = array[:, :, None]
        return torch.from_numpy(array)[None, ...]

    @staticmethod
    def _decode_base64_image(raw: str, task_id: str, index: int) -> bytes:
        """解码可能出现的 base64 结果（本节点请求 url，但对上游兼容更稳）。"""
        import base64

        value = raw.strip()
        if value.startswith("data:"):
            _, _, value = value.partition(",")
        try:
            return base64.b64decode(value, validate=False)
        except Exception as exc:  # noqa: BLE001 - 需要把原始异常暴露给用户
            raise ValueError(f"任务 {task_id} 第 {index} 张图片 base64 解码失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 结果解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_task_id(payload: Any) -> str:
        """从提交响应里取任务 ID。"""
        if isinstance(payload, dict):
            # reference_images 里的 URL 也可能带 id，这里只认顶层任务字段
            for key in ("id", "task_id", "taskId", "taskIdStr"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        raise RuntimeError(f"提交任务响应中缺少任务 id：{_preview(str(payload), 400)}")

    @staticmethod
    def _parse_status(payload: Any) -> str:
        """读取任务状态，统一小写。"""
        if isinstance(payload, dict):
            status = payload.get("status") or payload.get("state")
            if isinstance(status, str):
                return status.strip().lower()
        return ""

    def _collect_result_images(self, payload: Any) -> List[Tuple[str, str]]:
        """
        从完成任务响应里收集图片。

        返回 [(kind, value)]，kind 为 "url" 或 "base64"。
        兼容顶层 url、result.data[].url、data[].url 等多种结构。
        """
        found: List[Tuple[str, str]] = []
        seen = set()

        def _add(kind: str, value: Any) -> None:
            if not isinstance(value, str):
                return
            text = value.strip()
            if not text:
                return
            key = (kind, text)
            if key in seen:
                return
            seen.add(key)
            found.append((kind, text))

        def _walk(node: Any, depth: int = 0) -> None:
            # 限制递归深度，避免异常结构导致栈溢出
            if depth > 8:
                return
            if isinstance(node, dict):
                # items 结构：{"url": ...} / {"b64_json": ...}
                for key in _URL_ITEM_KEYS:
                    value = node.get(key)
                    if isinstance(value, str) and value.startswith(("http://", "https://")):
                        _add("url", value)
                for key in _B64_ITEM_KEYS:
                    value = node.get(key)
                    if isinstance(value, str) and len(value) > 256:
                        _add("base64", value)
                for key, value in node.items():
                    # 跳过提示词等文本字段，避免把描述里的链接当结果
                    if key in ("revised_prompt", "prompt", "text", "message", "content"):
                        continue
                    if key in _URL_CONTAINER_KEYS or key in ("result", "data", "output", "outputs", "images"):
                        _walk(value, depth + 1)
                    elif isinstance(value, (dict, list)):
                        _walk(value, depth + 1)
            elif isinstance(node, list):
                for item in node:
                    _walk(item, depth + 1)
            elif isinstance(node, str):
                # 兜底：顶层直接给了一个 URL
                if node.strip().startswith(("http://", "https://")) and len(node.strip()) < 2048:
                    _add("url", node)

        if isinstance(payload, dict):
            # 顶层 url 优先（部分上游直接回 url 字段）
            top_url = payload.get("url")
            if isinstance(top_url, str) and top_url.strip().startswith(("http://", "https://")):
                _add("url", top_url)
            for key in _URL_CONTAINER_KEYS:
                if key in payload:
                    _walk(payload[key], 1)
            if not found:
                _walk(payload, 0)
        else:
            _walk(payload, 0)

        return found

    # ------------------------------------------------------------------
    # 主要流程
    # ------------------------------------------------------------------

    @staticmethod
    def _slot_has_content(value: Any) -> bool:
        """
        判断一个参考图槽位是否真的连了图。

        未连接的槽位可能是 None、空列表或 [None]，这些都不算「有参考图」，
        必须过滤掉，否则会白白上传一张空图（也避免误报告警）。
        """
        if value is None:
            return False
        if isinstance(value, (list, tuple)):
            return any(item is not None for item in value)
        return True

    def _collect_reference_tensors(self, kw: Dict[str, Any]) -> List[Tuple[int, Any]]:
        """
        按端口顺序收集已连接的参考图（保持用户连线顺序）。
        """
        references: List[Tuple[int, Any]] = []
        for i in range(1, MAX_IMAGE_INPUTS + 1):
            value = kw.get(f"image_{i}")
            if not self._slot_has_content(value):
                continue
            if isinstance(value, (list, tuple)):
                value = next(item for item in value if item is not None)
            references.append((i, value))
        return references

    def _upload_reference_image(
        self,
        api_base: str,
        auth_header: str,
        body_bytes: bytes,
        filename: str,
        mime_type: str,
        slot: int,
        timeout: int,
    ) -> str:
        """上传单张参考图，返回 ToAPIs 提供的公开 URL。"""
        boundary = f"----WBLESSToApis{random.randint(10 ** 11, 10 ** 12 - 1)}"
        crlf = b"\r\n"
        preamble = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="purpose"\r\n\r\n'
            f"generation\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        payload = preamble + body_bytes + crlf + f"--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Authorization": auth_header,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(payload)),
        }

        logger.info(
            f"[ToAPIs GPT Image 2 VIP] 上传参考图 {slot}: {filename} "
            f"({len(body_bytes) / 1024:.1f}KB, {mime_type})"
        )
        status, parsed, text, _ = self._request_json(
            "POST", f"{api_base}{PATH_UPLOAD_IMAGES}", headers, payload, timeout=timeout
        )

        if status not in (200, 201, 202):
            self._raise_http_error(status, parsed, text, f"上传参考图 {slot}")

        if isinstance(parsed, dict) and parsed.get("success") is False:
            raise RuntimeError(
                f"上传参考图 {slot} 失败：{_looks_like_error(parsed) or _preview(text)}"
            )

        data = parsed.get("data") if isinstance(parsed, dict) else None
        url = data.get("url") if isinstance(data, dict) else None
        if not isinstance(url, str) or not url.strip():
            raise RuntimeError(f"上传参考图 {slot} 成功但未返回 url：{_preview(text, 400)}")

        logger.info(f"[ToAPIs GPT Image 2 VIP] 参考图 {slot} 上传成功")
        return url.strip()

    def _submit_task(
        self,
        api_base: str,
        auth_header: str,
        request_payload: Dict[str, Any],
        timeout: int,
    ) -> str:
        """提交图像生成任务，返回任务 ID。"""
        body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }

        status, parsed, text, _ = self._request_json(
            "POST", f"{api_base}{PATH_GENERATIONS}", headers, body, timeout=timeout
        )

        if status not in (200, 201, 202):
            self._raise_http_error(status, parsed, text, "提交生成任务")

        if parsed is None:
            raise RuntimeError(f"提交生成任务响应不是合法 JSON：{_preview(text)}")

        task_id = self._parse_task_id(parsed)
        logger.info(f"[ToAPIs GPT Image 2 VIP] 任务已提交，Task ID: {task_id}，状态: {self._parse_status(parsed) or 'unknown'}")
        return task_id

    def _poll_task(self, api_base: str, auth_header: str, task_id: str, timeout: int, interval: int) -> Any:
        """轮询任务直到完成，返回完成时的响应体。"""
        safe_task_id = _TASK_ID_SAFE_RE.sub("_", task_id)
        status_url = f"{api_base}{PATH_GENERATIONS}/{_encode_path_segment(safe_task_id)}"
        headers = {"Authorization": auth_header}

        start_time = time.time()
        attempt = 0
        last_status = ""
        # 首次等待：上游通常需要几秒钟才会进入生成阶段
        time.sleep(min(3.0, float(interval)))

        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(
                    f"任务超时（{timeout} 秒）task_id={task_id}，最后一次状态: {last_status or 'unknown'}"
                )

            attempt += 1
            status, parsed, text, response_headers = self._request_json(
                "GET", status_url, headers, None, timeout=max(30, interval * 6)
            )

            if status == 429:
                # 触发限流时按 Retry-After 退避，且逐步拉长间隔
                retry_after = response_headers.get("retry-after")
                try:
                    wait = float(retry_after) if retry_after else float(interval)
                except (TypeError, ValueError):
                    wait = float(interval)
                wait = max(wait, float(interval)) + random.uniform(0.0, 1.0)
                logger.warning(f"[ToAPIs GPT Image 2 VIP] 轮询限流，{wait:.1f} 秒后重试")
                time.sleep(min(wait, max(1.0, timeout - (time.time() - start_time))))
                continue

            if status == 401:
                raise RuntimeError("轮询鉴权失败：API Key 无效或已过期（HTTP 401）")
            if status == 404:
                raise RuntimeError(f"任务不存在（HTTP 404）task_id={task_id}，请确认 api_base 与任务归属")
            if status != 200:
                # 偶发的 5xx / 网关错误不应立即失败，记录后继续轮询
                logger.warning(
                    f"[ToAPIs GPT Image 2 VIP] 轮询异常 HTTP {status}（第 {attempt} 次），"
                    f"响应: {_preview(text, 200)}"
                )
                remaining = timeout - (time.time() - start_time)
                if remaining <= 0:
                    raise TimeoutError(f"任务超时（{timeout} 秒）task_id={task_id}")
                time.sleep(min(float(interval) + random.uniform(0.0, 1.0), remaining))
                continue

            if parsed is None:
                logger.warning(f"[ToAPIs GPT Image 2 VIP] 轮询响应不是合法 JSON（第 {attempt} 次）")
                time.sleep(min(float(interval) + random.uniform(0.0, 1.0), max(1.0, timeout - (time.time() - start_time))))
                continue

            task_status = self._parse_status(parsed)
            progress = parsed.get("progress") if isinstance(parsed, dict) else None
            if task_status != last_status or progress is not None:
                logger.info(
                    f"[ToAPIs GPT Image 2 VIP] 任务状态: {task_status or 'unknown'}"
                    f"{f' ({progress}%)' if progress is not None else ''}"
                )
            last_status = task_status

            if task_status == "completed":
                return parsed
            if task_status == "failed":
                error = parsed.get("error") if isinstance(parsed, dict) else None
                detail = ""
                if isinstance(error, dict):
                    detail = str(error.get("message") or error)
                elif error:
                    detail = str(error)
                detail = detail or str(parsed.get("fail_reason") if isinstance(parsed, dict) else "") or _preview(text, 400)
                raise RuntimeError(f"生成失败 task_id={task_id}：{detail or '上游未提供失败原因'}")

            # queued / in_progress / 未知状态：继续等待
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                raise TimeoutError(f"任务超时（{timeout} 秒）task_id={task_id}，最后一次状态: {last_status or 'unknown'}")
            time.sleep(min(float(interval) + random.uniform(0.0, 1.0), remaining))

    def _download_image(self, url: str, task_id: str, index: int, timeout: int) -> torch.Tensor:
        """下载结果图并转成 IMAGE tensor。"""
        image_bytes = self._request_raw(url, timeout)
        if not image_bytes:
            raise RuntimeError(f"下载结果图失败，响应为空: {_preview(url, 200)}")
        tensor = self._bytes_to_tensor(image_bytes)

        # 日志里打印尺寸，shape 缺失时不阻断主流程
        shape = getattr(tensor, "shape", None)
        if shape is not None and len(shape) == 4:
            logger.info(
                f"[ToAPIs GPT Image 2 VIP] 结果图 {index} 下载完成 "
                f"{shape[2]}x{shape[1]} 通道={shape[3]}"
            )
        else:
            logger.info(f"[ToAPIs GPT Image 2 VIP] 结果图 {index} 下载完成（{len(image_bytes) / 1024:.1f}KB）")
        return tensor

    def _request_raw(self, url: str, timeout: int) -> bytes:
        """单独走一次请求拿原始字节（图片不能用文本方式解码）。"""
        parts = urlsplit(url)
        is_https = parts.scheme == "https"
        port = parts.port or (443 if is_https else 80)
        conn_class = http.client.HTTPSConnection if is_https else http.client.HTTPConnection

        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        if is_https:
            conn = conn_class(parts.hostname, port, timeout=timeout, context=self._ssl_context())
        else:
            conn = conn_class(parts.hostname, port, timeout=timeout)
        try:
            conn.request("GET", path, headers={"Accept": "*/*", "User-Agent": "ComfyUI-WBLESS"})
            response = conn.getresponse()
            return response.read()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def run(self, **kw) -> Tuple[List[torch.Tensor], str]:
        """节点主入口。"""
        # ---- 读取参数 ----
        api_key = _as_str(kw.get("api_key"))
        api_base = _normalize_api_base(_as_str(kw.get("api_base")))
        prompt = _as_str(kw.get("prompt"))
        model = _as_str(kw.get("model"), DEFAULT_MODEL) or DEFAULT_MODEL
        preset_size = _as_str(kw.get("size"), "1:1") or "1:1"
        custom_size = _as_str(kw.get("custom_size"))
        resolution = _as_str(kw.get("resolution"), "1k") or "1k"
        quality = _as_str(kw.get("quality"), "medium") or "medium"
        background = _as_str(kw.get("background"), "auto") or "auto"
        n = _as_int(kw.get("n"), 1, 1, 10)
        timeout = _as_int(kw.get("timeout"), 600, 30, 3600)
        poll_interval = _as_int(kw.get("poll_interval"), 5, 1, 60)

        if not prompt:
            raise ValueError("prompt 不能为空，请填写图像生成的文本描述")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"prompt 长度 {len(prompt)} 超过上限 {MAX_PROMPT_LENGTH} 字符")

        # 任意比例优先于预设
        size = _normalize_size(custom_size or preset_size)
        if resolution not in RESOLUTIONS:
            raise ValueError(f"resolution 非法: {resolution}，可选 {RESOLUTIONS}")
        if quality not in QUALITIES:
            raise ValueError(f"quality 非法: {quality}，可选 {QUALITIES}")
        if background not in BACKGROUNDS:
            raise ValueError(f"background 非法: {background}，可选 {BACKGROUNDS}")

        auth_header = self._auth_header(self._resolve_api_key(api_key))

        # ---- 上传参考图，换取公开 URL ----
        references = self._collect_reference_tensors(kw)
        resolved_keys = {f"image_{slot}" for slot, _ in references}

        # 诊断：端口连了线、但参数没送进来，说明该输入被 ComfyUI 丢掉了。
        # 这种情况以前会静默退化成「文生图」，很难排查，这里显式告警出来。
        missing_slots = [
            key for key, value in kw.items()
            if key.startswith("image_") and self._slot_has_content(value) and key not in resolved_keys
        ]
        if missing_slots:
            logger.warning(
                f"[ToAPIs GPT Image 2 VIP] 参考图输入被上游丢弃: {sorted(missing_slots)}；"
                f"实际解析到的槽位: {sorted(resolved_keys)}"
            )

        reference_urls: List[str] = []
        for slot, tensor in references:
            body_bytes, filename, mime_type, fell_back = self._encode_upload(tensor, slot)
            url = self._upload_reference_image(
                api_base, auth_header, body_bytes, filename, mime_type, slot, timeout
            )
            reference_urls.append(url)
            if fell_back:
                logger.warning(f"[ToAPIs GPT Image 2 VIP] 参考图 {slot} 已降级为 JPEG 上传")

        # ---- 构建请求体 ----
        request_payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "resolution": resolution,
            "quality": quality,
            "response_format": "url",
        }
        # auto 时不发送，交给上游按默认行为处理
        if background != "auto":
            request_payload["background"] = background
        if reference_urls:
            request_payload["reference_images"] = reference_urls

        mode = "图生图" if reference_urls else "文生图"
        logger.info(
            f"[ToAPIs GPT Image 2 VIP] {mode} model={model} size={size} resolution={resolution} "
            f"quality={quality} background={background} n={n} 参考图={len(reference_urls)} "
            f"prompt长度={len(prompt)} base={api_base}"
        )

        # ---- 提交并轮询 ----
        task_id = self._submit_task(api_base, auth_header, request_payload, timeout=max(60, poll_interval * 6))
        completed = self._poll_task(api_base, auth_header, task_id, timeout, poll_interval)

        # ---- 收集并下载结果 ----
        items = self._collect_result_images(completed)
        if not items:
            raise RuntimeError(
                f"任务已完成但未找到图片结果 task_id={task_id}：{_preview(json.dumps(completed, ensure_ascii=False) if isinstance(completed, (dict, list)) else str(completed), 600)}"
            )

        images: List[torch.Tensor] = []
        result_urls: List[str] = []
        for index, (kind, value) in enumerate(items[:n], start=1):
            if kind == "url":
                images.append(self._download_image(value, task_id, index, timeout))
                result_urls.append(value)
            else:
                images.append(self._bytes_to_tensor(self._decode_base64_image(value, task_id, index)))
                result_urls.append("<base64>")

        if not images:
            raise RuntimeError(f"任务已完成但结果图下载失败 task_id={task_id}")
        if len(images) != n:
            # 上游偶尔会少给图，明确告知而不是静默返回少量结果
            logger.warning(
                f"[ToAPIs GPT Image 2 VIP] 请求 {n} 张但仅收到 {len(images)} 张 task_id={task_id}"
            )

        logger.info(f"[ToAPIs GPT Image 2 VIP] 成功获取 {len(images)} 张图像 task_id={task_id}")

        response = json.dumps(
            {
                "task_id": task_id,
                "model": model,
                "status": "completed",
                "size": size,
                "resolution": resolution,
                "quality": quality,
                "background": background,
                "reference_images": reference_urls,
                "urls": result_urls,
            },
            ensure_ascii=False,
            indent=2,
        )
        return (images, response)


NODE_CLASS_MAPPINGS = {
    "ToAPIs GPT Image 2 VIP": ToApisGptImage2VipNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ToAPIs GPT Image 2 VIP": "ToAPIs GPT Image 2 VIP",
}
