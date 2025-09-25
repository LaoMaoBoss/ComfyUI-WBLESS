# coding: utf-8
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import platform
import re
import time
from cozy_comfyui.node import CozyBaseNode

try:
    from fontTools.ttLib import TTFont
    FONTTOOLS_AVAILABLE = True
except ImportError:
    FONTTOOLS_AVAILABLE = False
    print("[WBLESS] fonttools not available. Using filename-based font parsing.")

# WBLESS 插件根目录的绝对路径
WBLESS_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# 排版行业标准倾斜角度（度）
STANDARD_ITALIC_ANGLE = 12.0  # 标准斜体角度12°，符合主流排版软件标准
# 为动态输入端口定义一个理论上的最大数量
MAX_TEXT_BLOCKS = 64

# 颜色映射，参考 ComfyRoll 的实现
COLOR_MAPPING = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "brown": (160, 85, 15),
    "gray": (128, 128, 128),
    "lightgray": (211, 211, 211),
    "darkgray": (102, 102, 102),
    "olive": (128, 128, 0),
    "lime": (0, 128, 0),
    "teal": (0, 128, 128),
    "navy": (0, 0, 128),
    "maroon": (128, 0, 0),
    "fuchsia": (255, 0, 128),
    "aqua": (0, 255, 128),
    "silver": (192, 192, 192),
    "gold": (255, 215, 0),
    "turquoise": (64, 224, 208),
    "lavender": (230, 230, 250),
    "violet": (238, 130, 238),
    "coral": (255, 127, 80),
    "indigo": (75, 0, 130),    
}

def get_system_font_files():
    """
    获取系统字体文件列表
    参考 CR Select Font 的实现，支持 Windows、Linux 和 macOS
    """
    system_name = platform.system()
    font_files = []
    
    try:
        if system_name == "Windows":
            # Windows 系统字体目录
            system_root = os.environ.get("SystemRoot")
            if system_root:
                font_dir = os.path.join(system_root, "Fonts")
                if os.path.exists(font_dir):
                    font_files = [f for f in os.listdir(font_dir) 
                                if os.path.isfile(os.path.join(font_dir, f)) 
                                and f.lower().endswith(('.ttf', '.otf'))]
        
        elif system_name == "Linux":
            # Linux 系统字体目录
            font_dir = "/usr/share/fonts/truetype"
            if os.path.exists(font_dir):
                # 递归扫描子目录
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        if file.lower().endswith(('.ttf', '.otf')):
                            font_files.append(file)
        
        elif system_name == "Darwin":  # macOS
            # macOS 系统字体目录
            font_dir = "/System/Library/Fonts"
            if os.path.exists(font_dir):
                font_files = [f for f in os.listdir(font_dir) 
                            if os.path.isfile(os.path.join(font_dir, f)) 
                            and f.lower().endswith(('.ttf', '.otf'))]
    
    except Exception as e:
        print(f"[WBLESS] Error scanning system fonts: {e}")
    
    return font_files

def read_font_metadata(font_file_path, font_index=0):
    """
    读取字体文件的元数据，包括字体家族名称和样式
    优先读取中文名称，回退到英文名称
    返回: (family_name, style_name, full_name)
    
    Args:
        font_file_path: 字体文件路径
        font_index: 对于TTC文件，指定要读取的字体索引（默认为0）
    """
    if not FONTTOOLS_AVAILABLE:
        return None, None, None
    
    try:
        # 检查是否为TTC文件
        if font_file_path.lower().endswith('.ttc'):
            try:
                font = TTFont(font_file_path, fontNumber=font_index)
            except Exception as ttc_e:
                # 如果指定的索引无效，尝试获取TTC信息并处理所有字体
                if "specify a font number" in str(ttc_e):
                    return None, None, None  # 这个索引无效，调用者应该处理
                else:
                    raise ttc_e
        else:
            font = TTFont(font_file_path)
        
        name_table = font['name']
        
        # 存储不同语言版本的名称
        family_names = {}      # {languageID: name} - nameID = 1
        style_names = {}       # {languageID: name} - nameID = 2
        full_names = {}        # {languageID: name} - nameID = 4
        preferred_family = {}  # {languageID: name} - nameID = 16 (优先)
        preferred_style = {}   # {languageID: name} - nameID = 17 (优先)
        
        # 遍历所有名称记录
        for record in name_table.names:
            try:
                # 只处理 Windows Unicode 平台 (platformID=3, platEncID=1)
                if record.platformID == 3 and record.platEncID == 1:
                    name_text = record.toUnicode()
                    lang_id = record.langID
                    
                    # 字体家族名称 (nameID = 1) - 备用
                    if record.nameID == 1:
                        family_names[lang_id] = name_text
                    # 字体样式名称 (nameID = 2) - 备用
                    elif record.nameID == 2:
                        style_names[lang_id] = name_text
                    # 完整字体名称 (nameID = 4)
                    elif record.nameID == 4:
                        full_names[lang_id] = name_text
                    # 首选家族名称 (nameID = 16) - 优先使用
                    elif record.nameID == 16:
                        preferred_family[lang_id] = name_text
                    # 首选样式名称 (nameID = 17) - 优先使用
                    elif record.nameID == 17:
                        preferred_style[lang_id] = name_text
            except Exception as e:
                # 忽略单个记录的解析错误
                continue
        
        # 语言优先级：中文 > 英文 > 其他
        language_priority = [
            2052,  # 中文 (简体) - Chinese Simplified
            1028,  # 中文 (繁体) - Chinese Traditional  
            1033,  # 英文 - English US
            1031,  # 德文 - German
            1036,  # 法文 - French
            1041,  # 日文 - Japanese
            1042,  # 韩文 - Korean
        ]
        
        def get_best_name(names_dict):
            """根据语言优先级选择最佳名称"""
            if not names_dict:
                return None
            
            # 按优先级查找
            for lang_id in language_priority:
                if lang_id in names_dict:
                    return names_dict[lang_id]
            
            # 如果没有找到优先语言，返回任意一个
            return next(iter(names_dict.values()))
        
        # 优先使用 Preferred Family/Style，如果没有则回退到普通 Family/Style
        family_name = get_best_name(preferred_family) or get_best_name(family_names)
        style_name = get_best_name(preferred_style) or get_best_name(style_names)
        full_name = get_best_name(full_names)
        
        font.close()
        
        # 调试信息：显示找到的语言版本和最终选择
        debug_info = []
        if preferred_family:
            debug_info.append(f"Preferred Family langs: {list(preferred_family.keys())}")
        elif family_names:
            debug_info.append(f"Family langs: {list(family_names.keys())}")
        
        if preferred_style:
            debug_info.append(f"Preferred Style langs: {list(preferred_style.keys())}")
        elif style_names:
            debug_info.append(f"Style langs: {list(style_names.keys())}")
        
        if debug_info and FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Font {os.path.basename(font_file_path)}: {', '.join(debug_info)}")
            print(f"[WBLESS] Selected: '{family_name}' | '{style_name}'")
        
        return family_name, style_name, full_name
    
    except Exception as e:
        print(f"[WBLESS] Error reading font metadata from {font_file_path}: {e}")
        return None, None, None

def get_ttc_font_count(font_file_path):
    """
    获取TTC文件中包含的字体数量
    
    Args:
        font_file_path: TTC字体文件路径
        
    Returns:
        int: 字体数量，如果出错则返回0
    """
    if not FONTTOOLS_AVAILABLE:
        return 0
    
    try:
        from fontTools.ttLib import TTCollection
        ttc = TTCollection(font_file_path)
        font_count = len(ttc.fonts)
        ttc.close()
        return font_count
    except Exception as e:
        # 如果无法读取TTC文件，返回0
        return 0

def read_all_fonts_from_ttc(font_file_path):
    """
    从TTC文件中读取所有字体的元数据
    
    Args:
        font_file_path: TTC字体文件路径
        
    Returns:
        list: [(family_name, style_name, full_name), ...] 所有字体的元数据列表
    """
    fonts_metadata = []
    font_count = get_ttc_font_count(font_file_path)
    
    if font_count == 0:
        return fonts_metadata
    
    for i in range(font_count):
        try:
            metadata = read_font_metadata(font_file_path, font_index=i)
            if metadata[0] is not None:  # 如果成功读取到family_name
                fonts_metadata.append(metadata)
        except Exception as e:
            # 忽略单个字体的读取错误
            continue
    
    return fonts_metadata

def get_local_fonts():
    """
    获取WBLESS工程目录下fonts文件夹中的字体
    返回字体字典，格式与系统字体相同
    """
    local_fonts = {}
    
    try:
        # 构建fonts目录路径
        fonts_dir = os.path.join(WBLESS_PATH, "fonts")
        
        if not os.path.exists(fonts_dir):
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] Local fonts directory not found: {fonts_dir}")
            return local_fonts
        
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Scanning local fonts directory: {fonts_dir}")
        
        # 支持的字体格式
        font_extensions = ('.ttf', '.otf', '.ttc', '.woff', '.woff2')
        local_font_count = 0
        
        # 扫描fonts目录中的所有字体文件
        for file in os.listdir(fonts_dir):
            if file.lower().endswith(font_extensions):
                font_path = os.path.join(fonts_dir, file)
                
                # 检查文件是否可读
                if not os.access(font_path, os.R_OK):
                    continue
                
                try:
                    # 解析字体信息
                    if FONTTOOLS_AVAILABLE:
                        # 检查是否为TTC文件
                        if font_path.lower().endswith('.ttc'):
                            # 处理TTC文件中的所有字体
                            fonts_metadata = read_all_fonts_from_ttc(font_path)
                            for family_name, style_name, full_name in fonts_metadata:
                                if family_name:
                                    if family_name not in local_fonts:
                                        local_fonts[family_name] = {}
                                    
                                    # 如果没有字重信息，使用"Regular"作为默认
                                    final_style = style_name if style_name else "Regular"
                                    
                                    # 存储字体文件路径
                                    if final_style not in local_fonts[family_name]:
                                        local_fonts[family_name][final_style] = font_path
                                        local_font_count += 1
                        else:
                            # 处理普通字体文件
                            family_name, style_name, full_name = read_font_metadata(font_path)
                            if family_name:
                                if family_name not in local_fonts:
                                    local_fonts[family_name] = {}
                                
                                # 如果没有字重信息，使用"Regular"作为默认
                                final_style = style_name if style_name else "Regular"
                                
                                # 存储字体文件路径
                                if final_style not in local_fonts[family_name]:
                                    local_fonts[family_name][final_style] = font_path
                                    local_font_count += 1
                    else:
                        # 如果fonttools不可用，使用智能文件名解析
                        family_name, style_name = parse_font_name_intelligently(file)
                        if family_name:
                            if family_name not in local_fonts:
                                local_fonts[family_name] = {}
                            
                            # 如果没有字重信息，使用"Regular"作为默认
                            final_style = style_name if style_name else "Regular"
                            
                            # 存储字体文件路径
                            if final_style not in local_fonts[family_name]:
                                local_fonts[family_name][final_style] = font_path
                                local_font_count += 1
                
                except Exception as e:
                    # 记录详细的解析错误，但继续处理其他字体
                    if FONT_SCAN_CONFIG.get('enable_debug', False):
                        print(f"[WBLESS] Failed to parse local font {font_path}: {e}")
                    continue
        
        if local_font_count > 0:
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] Found {local_font_count} local fonts in {len(local_fonts)} families")
        else:
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] No local fonts found in {fonts_dir}")
        
    except Exception as e:
        print(f"[WBLESS] Error scanning local fonts: {e}")
    
    return local_fonts

def get_system_fonts():
    """
    获取系统字体列表，增强版本
    支持更多字体目录、格式和递归扫描，修复CR Select Font的局限性
    """
    system_fonts = {}
    system_name = platform.system()
    
    try:
        # 根据操作系统确定所有可能的字体目录
        font_dirs = []
        
        if system_name == "Windows":
            # Windows 系统字体目录
            system_root = os.environ.get("SystemRoot", "C:\\Windows")
            font_dirs = [
                os.path.join(system_root, "Fonts"),
                # 用户安装的字体目录
                os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\Fonts"),
                # Windows 10+ 的新字体目录
                os.path.join(system_root, "SystemApps"),
            ]
        elif system_name == "Linux":
            # Linux 字体目录 - 扩展更多位置
            font_dirs = [
                "/usr/share/fonts",              # 系统字体
                "/usr/local/share/fonts",        # 本地安装字体
                "/usr/share/fonts/truetype",     # TrueType字体
                "/usr/share/fonts/opentype",     # OpenType字体
                "/usr/share/fonts/X11",          # X11字体
                os.path.expanduser("~/.fonts"),  # 用户字体
                os.path.expanduser("~/.local/share/fonts"),  # 用户本地字体
                "/var/lib/defoma/fontconfig.d/",  # Debian字体配置
            ]
        elif system_name == "Darwin":  # macOS
            # macOS 字体目录
            font_dirs = [
                "/System/Library/Fonts",         # 系统字体
                "/Library/Fonts",                # 系统安装字体
                os.path.expanduser("~/Library/Fonts"),  # 用户字体
                "/System/Library/Assets/com_apple_MobileAsset_Font6",  # iOS字体
            ]
        else:
            print(f"[WBLESS] Unsupported operating system: {system_name}")
            return {}
        
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Scanning system fonts on {system_name}...")
        
        # 支持更多字体格式
        font_extensions = ('.ttf', '.otf', '.ttc', '.woff', '.woff2', '.eot')
        total_fonts_found = 0
        
        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue
                
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] Scanning directory: {font_dir}")
            dir_font_count = 0
            
            # 递归扫描所有字体目录
            for root, dirs, files in os.walk(font_dir):
                # 跳过一些不必要的目录以提高性能
                dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ['cache', 'backup', 'temp']]
                
                for file in files:
                    if file.lower().endswith(font_extensions):
                        font_path = os.path.join(root, file)
                        
                        # 检查文件是否可读
                        if not os.access(font_path, os.R_OK):
                            continue
                            
                        try:
                            # 解析字体信息
                            if FONTTOOLS_AVAILABLE:
                                # 检查是否为TTC文件
                                if font_path.lower().endswith('.ttc'):
                                    # 处理TTC文件中的所有字体
                                    fonts_metadata = read_all_fonts_from_ttc(font_path)
                                    for family_name, style_name, full_name in fonts_metadata:
                                        if family_name:
                                            if family_name not in system_fonts:
                                                system_fonts[family_name] = {}
                                            
                                            # 如果没有字重信息，使用"Regular"作为默认
                                            final_style = style_name if style_name else "Regular"
                                            
                                            # 避免重复字体（优先级：系统 > 用户）
                                            if final_style not in system_fonts[family_name]:
                                                system_fonts[family_name][final_style] = font_path
                                                dir_font_count += 1
                                            elif "/System/" in font_path or "/Windows/" in font_path:
                                                # 优先使用系统字体
                                                system_fonts[family_name][final_style] = font_path
                                else:
                                    # 处理普通字体文件
                                    family_name, style_name, full_name = read_font_metadata(font_path)
                                    if family_name:
                                        if family_name not in system_fonts:
                                            system_fonts[family_name] = {}
                                        
                                        # 如果没有字重信息，使用"Regular"作为默认
                                        final_style = style_name if style_name else "Regular"
                                        
                                        # 避免重复字体（优先级：系统 > 用户）
                                        if final_style not in system_fonts[family_name]:
                                            system_fonts[family_name][final_style] = font_path
                                            dir_font_count += 1
                            else:
                                family_name, style_name = parse_font_name_intelligently(file)
                                if family_name:
                                    if family_name not in system_fonts:
                                        system_fonts[family_name] = {}
                                    
                                    # 如果没有字重信息，使用"Regular"作为默认
                                    final_style = style_name if style_name else "Regular"
                                    
                                    # 避免重复字体（优先级：系统 > 用户）
                                    if final_style not in system_fonts[family_name]:
                                        system_fonts[family_name][final_style] = font_path
                                        dir_font_count += 1
                                    elif "/System/" in font_path or "/Windows/" in font_path:
                                        # 系统字体优先级更高，覆盖用户字体
                                        system_fonts[family_name][final_style] = font_path
                                    
                        except Exception as e:
                            # 记录详细的解析错误，但继续处理其他字体
                            if FONT_SCAN_CONFIG.get('enable_debug', False):
                                print(f"[WBLESS] Failed to parse font {font_path}: {e}")
                            continue
            
            if dir_font_count > 0:
                if FONT_SCAN_CONFIG.get('enable_debug', False):
                    print(f"[WBLESS] Found {dir_font_count} fonts in {font_dir}")
                total_fonts_found += dir_font_count
        
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Total: {len(system_fonts)} font families, {total_fonts_found} font files")
        
        # 如果没有找到任何字体，尝试基本的回退方案
        if not system_fonts:
            print(f"[WBLESS] No fonts found, trying fallback detection...")
            return get_fallback_fonts(system_name)
        
        return system_fonts
        
    except Exception as e:
        print(f"[WBLESS] Error scanning system fonts: {e}")
        # 尝试回退方案
        return get_fallback_fonts(system_name)

def get_fallback_fonts(system_name):
    """
    回退字体检测方案，当主要扫描失败时使用
    提供基本的字体支持
    """
    fallback_fonts = {}
    
    try:
        # 尝试一些常见的字体路径和名称
        common_fonts = []
        
        if system_name == "Windows":
            common_fonts = [
                ("Arial", "C:\\Windows\\Fonts\\arial.ttf"),
                ("Times New Roman", "C:\\Windows\\Fonts\\times.ttf"),
                ("Calibri", "C:\\Windows\\Fonts\\calibri.ttf"),
                ("Segoe UI", "C:\\Windows\\Fonts\\segoeui.ttf"),
                ("Tahoma", "C:\\Windows\\Fonts\\tahoma.ttf"),
                ("Verdana", "C:\\Windows\\Fonts\\verdana.ttf"),
            ]
        elif system_name == "Darwin":  # macOS
            common_fonts = [
                ("Helvetica", "/System/Library/Fonts/Helvetica.ttc"),
                ("Times", "/System/Library/Fonts/Times.ttc"),
                ("Arial", "/System/Library/Fonts/Arial.ttf"),
                ("Courier", "/System/Library/Fonts/Courier.ttc"),
                ("Monaco", "/System/Library/Fonts/Monaco.ttf"),
            ]
        elif system_name == "Linux":
            common_fonts = [
                ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                ("Liberation Sans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
                ("Ubuntu", "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
                ("Noto Sans", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
            ]
        
        for family_name, font_path in common_fonts:
            if os.path.exists(font_path) and os.access(font_path, os.R_OK):
                if family_name not in fallback_fonts:
                    fallback_fonts[family_name] = {}
                fallback_fonts[family_name]["Regular"] = font_path
                print(f"[WBLESS] Fallback font found: {family_name} at {font_path}")
        
        if fallback_fonts:
            print(f"[WBLESS] Fallback detection found {len(fallback_fonts)} font families")
        else:
            print(f"[WBLESS] No fallback fonts found")
        
        return fallback_fonts
        
    except Exception as e:
        print(f"[WBLESS] Error in fallback font detection: {e}")
        return {}

def parse_font_name_intelligently(font_filename):
    """
    智能解析字体文件名，区分字体名称、字重和版本号
    增强版本，支持更多命名模式和特殊情况
    """
    # 移除扩展名
    base_name = os.path.splitext(font_filename)[0]
    
    # 预处理：处理一些特殊的命名模式
    base_name = preprocess_font_name(base_name)
    
    # 扩展的字重关键词（支持更多语言和变体）
    weight_keywords = [
        # 英文字重
        'Thin', 'ExtraLight', 'UltraLight', 'Light', 'Regular', 'Normal', 'Medium',
        'SemiBold', 'DemiBold', 'Bold', 'ExtraBold', 'UltraBold', 'Black', 'Heavy',
        'Italic', 'Oblique', 'Condensed', 'Extended', 'Narrow', 'Wide',
        # 样式变体
        'Roman', 'Upright', 'Slanted', 'Inclined', 'Compressed', 'Expanded',
        # 缩写形式
        'Reg', 'Med', 'Bd', 'Bk', 'Lt', 'It', 'Obl', 'Cond', 'Ext',
        # 中文字重 (如果有的话)
        'Regular', 'Bold', 'Light', 'Heavy', 'Thin'
    ]
    
    # 数字字重模式 (严格模式，只匹配有效的字重值)
    numeric_weight_patterns = [
        r'\b(?:[1-9]00)\b',      # 100, 200, 300, 400, 500, 600, 700, 800, 900
        r'\b(?:w[1-9]00)\b',     # w100, w200, ..., w900
        r'\b(?:W[1-9]00)\b',     # W100, W200, ..., W900
    ]
    
    # 有效的数字字重值 (用于验证)
    valid_numeric_weights = {
        '100', '200', '300', '400', '500', '600', '700', '800', '900',
        'w100', 'w200', 'w300', 'w400', 'w500', 'w600', 'w700', 'w800', 'w900',
        'W100', 'W200', 'W300', 'W400', 'W500', 'W600', 'W700', 'W800', 'W900'
    }
    
    # 版本号模式 (如 v1.0, V2.1, 1.0, 2021)
    version_patterns = [
        r'[vV]\d+\.\d+',     # v1.0, V2.1
        r'[vV]\d+',          # v1, V2
        r'\b\d{4}\b',        # 2021, 2022 (年份)
        r'\b\d+\.\d+\b',     # 1.0, 2.1
        r'Version\d+',       # Version1, Version2
    ]
    
    # 分割字符 (连字符、下划线、空格、点)
    separators = r'[-_\s.]+'
    
    # 将字体名分割成部分
    parts = re.split(separators, base_name)
    parts = [part.strip() for part in parts if part.strip()]
    
    family_parts = []
    weight_parts = []
    
    for i, part in enumerate(parts):
        is_weight = False
        is_version = False
        
        # 检查是否为版本号
        for version_pattern in version_patterns:
            if re.search(version_pattern, part, re.IGNORECASE):
                is_version = True
                break
        
        # 如果是版本号，归入字体名称
        if is_version:
            family_parts.append(part)
            continue
        
        # 检查是否为字重关键词（严格匹配，避免误判）
        part_lower = part.lower()
        for keyword in weight_keywords:
            keyword_lower = keyword.lower()
            # 优先精确匹配
            if keyword_lower == part_lower:
                is_weight = True
                break
            # 只允许作为独立单词出现在复合词中
            elif len(keyword_lower) >= 3 and keyword_lower in part_lower:
                # 确保不是部分匹配，避免像 "thin" 匹配到 "197thin" 这样的情况
                if (part_lower.startswith(keyword_lower) or 
                    part_lower.endswith(keyword_lower) or
                    f"_{keyword_lower}_" in f"_{part_lower}_"):
                    is_weight = True
                    break
        
        # 检查是否为数字字重（严格验证）
        if not is_weight:
            for pattern in numeric_weight_patterns:
                match = re.search(pattern, part, re.IGNORECASE)
                if match:
                    # 验证匹配的数字是否为有效的字重值
                    matched_weight = match.group().lower()
                    if matched_weight in valid_numeric_weights:
                        is_weight = True
                        break
        
        # 特殊处理：复合字重标识（严格模式）
        if not is_weight:
            # 检查复合样式（如 BoldItalic, LightCondensed）
            # 只有当包含两个明确的字重关键词时才认为是字重
            found_keywords = []
            for keyword in weight_keywords[:15]:  # 只检查主要字重关键词
                keyword_lower = keyword.lower()
                if len(keyword_lower) >= 3 and keyword_lower in part_lower:
                    # 确保是完整的关键词匹配
                    if (part_lower.startswith(keyword_lower) or 
                        part_lower.endswith(keyword_lower)):
                        found_keywords.append(keyword_lower)
            
            # 如果找到了明确的字重关键词，才认为是字重
            if len(found_keywords) >= 1 and len(part) >= 4:  # 至少4个字符长度
                is_weight = True
        
        if is_weight:
            weight_parts.append(part)
        else:
            family_parts.append(part)
    
    # 构建最终的家族名称和字重名称
    family_name = ' '.join(family_parts) if family_parts else 'Unknown'
    weight_name = ' '.join(weight_parts) if weight_parts else ''
    
    # 后处理：清理和标准化
    family_name, weight_name = postprocess_font_names(family_name, weight_name)
    
    # 最终验证：如果字重不是标准字重，则设为空
    weight_name = validate_font_weight(weight_name)
    
    return family_name, weight_name

def validate_font_weight(weight_name):
    """
    验证字重名称是否为有效的标准字重
    采用更宽松的验证策略，但仍过滤明显无效的字重
    """
    if not weight_name or not weight_name.strip():
        return ""
    
    weight_lower = weight_name.lower().strip()
    
    # 明确无效的模式 - 只过滤明显错误的情况
    invalid_patterns = [
        r'^\d{3,}$',  # 只是三位或更多数字且没有其他内容 (如197, 1000)
        r'^\d+[a-z]*\d+[a-z]*$',  # 数字-字母-数字模式且没有有效关键词
    ]
    
    # 检查是否匹配无效模式（但先检查是否包含有效关键词）
    for pattern in invalid_patterns:
        if re.search(pattern, weight_lower):
            # 即使匹配无效模式，如果包含有效关键词也允许
            valid_keywords = {
                'thin', 'extralight', 'ultralight', 'light', 'regular', 'normal', 'medium',
                'semibold', 'demibold', 'bold', 'extrabold', 'ultrabold', 'black', 'heavy',
                'italic', 'oblique', 'roman', 'condensed', 'compressed', 'narrow', 
                'extended', 'expanded', 'wide'
            }
            
            has_valid_keyword = False
            for keyword in valid_keywords:
                if keyword in weight_lower:
                    has_valid_keyword = True
                    break
            
            if not has_valid_keyword:
                return ""
    
    # 明确无效的字重（精确匹配）
    invalid_weights = {
        '197', '555', '666', '777', '999', '1000', '197thin', 'thin197', '555bold', 'bold197'
    }
    
    if weight_lower in invalid_weights:
        return ""
    
    # 如果包含有效的字重关键词，则认为是有效的
    valid_keywords = {
        'thin', 'extralight', 'ultralight', 'light', 'regular', 'normal', 'medium',
        'semibold', 'demibold', 'bold', 'extrabold', 'ultrabold', 'black', 'heavy',
        'italic', 'oblique', 'roman', 'condensed', 'compressed', 'narrow', 
        'extended', 'expanded', 'wide', '100', '200', '300', '400', '500', 
        '600', '700', '800', '900'
    }
    
    # 特殊处理：数字+有效关键词的组合（如 "105 Heavy", "35 Thin"）
    number_weight_pattern = r'^(\d{1,3})\s+(\w+)$'
    match = re.match(number_weight_pattern, weight_name)
    if match:
        number, keyword = match.groups()
        if keyword.lower() in valid_keywords:
            return weight_name  # 数字+有效关键词组合是有效的
    
    # 如果整个字重名称就是一个有效关键词
    if weight_lower in valid_keywords:
        return weight_name
    
    # 检查复合字重
    weight_parts = weight_lower.split()
    if len(weight_parts) > 1:
        # 如果有任何部分是有效关键词，则认为整个字重有效
        for part in weight_parts:
            if part in valid_keywords:
                return weight_name
    
    # 检查是否包含有效关键词作为子字符串（但要避免误判）
    for keyword in valid_keywords:
        if len(keyword) >= 4 and keyword in weight_lower:
            # 确保不是部分匹配导致的误判
            if (weight_lower.startswith(keyword) or 
                weight_lower.endswith(keyword) or
                f" {keyword} " in f" {weight_lower} "):
                return weight_name
    
    # 对于不包含明显有害模式的字重，采用更宽松的策略
    # 如果字重不包含明显的无效数字序列，就允许它
    if not re.search(r'^\d{3,}$', weight_lower):  # 不是纯粹的三位以上数字
        return weight_name
    
    # 如果都不匹配，返回空字符串
    return ""

def preprocess_font_name(name):
    """
    预处理字体名称，处理特殊的命名模式
    """
    # 处理Windows系统字体的特殊命名
    # 如 arialbd.ttf -> arial-bold, calibrib.ttf -> calibri-bold
    special_patterns = [
        (r'arial(bd|i|bi)$', r'arial-\1'),
        (r'times(bd|i|bi)$', r'times-\1'),
        (r'calibri(b|i|bi|l)$', r'calibri-\1'),
        (r'georgia(b|i|bi)$', r'georgia-\1'),
        (r'trebuc(bd|bi|it)$', r'trebuc-\1'),
        (r'verdana(b|i|bi)$', r'verdana-\1'),
        (r'tahoma(bd)$', r'tahoma-\1'),
    ]
    
    name_lower = name.lower()
    for pattern, replacement in special_patterns:
        if re.search(pattern, name_lower):
            name = re.sub(pattern, replacement, name_lower, flags=re.IGNORECASE)
            break
    
    return name

def postprocess_font_names(family_name, weight_name):
    """
    后处理字体名称，标准化和清理
    """
    # 如果字重为空，不进行处理
    if not weight_name or not weight_name.strip():
        family_name = family_name.strip()
        return family_name, ""
    
    # 标准化字重名称
    weight_standardization = {
        'bd': 'Bold',
        'b': 'Bold', 
        'i': 'Italic',
        'bi': 'Bold Italic',
        'l': 'Light',
        'it': 'Italic',
        'reg': 'Regular',
        'med': 'Medium',
        'bk': 'Black',
        'lt': 'Light',
        'obl': 'Oblique',
        'cond': 'Condensed',
        'ext': 'Extended',
    }
    
    # 应用标准化
    weight_lower = weight_name.lower().strip()
    if weight_lower in weight_standardization:
        weight_name = weight_standardization[weight_lower]
    
    # 清理家族名称
    family_name = family_name.strip()
    if family_name.lower() == 'unknown' and weight_name:
        # 如果家族名称未知，尝试从权重中提取
        family_name = extract_family_from_weight(weight_name)
    
    return family_name, weight_name

def extract_family_from_weight(weight_name):
    """
    从字重信息中尝试提取家族名称
    """
    # 这是一个回退策略，用于处理解析失败的情况
    common_families = ['Arial', 'Times', 'Calibri', 'Georgia', 'Verdana', 'Tahoma']
    weight_lower = weight_name.lower()
    
    for family in common_families:
        if family.lower() in weight_lower:
            return family
    
    return 'System Font'

# 全局缓存变量
_font_families_cache = None
_font_families_cache_time = 0

# 字体扫描配置
FONT_SCAN_CONFIG = {
    'enable_deep_scan': True,     # 启用深度扫描（递归子目录）
    'max_scan_depth': 3,          # 最大扫描深度
    'enable_debug': False,        # 禁用调试输出，避免大量日志影响阅读
    'cache_duration': 30,         # 缓存持续时间（秒）
    'scan_timeout': 10,           # 扫描超时时间（秒）
}

def parse_font_families():
    """
    解析字体文件，按字体家族分组
    整合本地字体和系统字体，本地字体优先显示
    优先使用字体元数据，回退到智能文件名解析
    使用缓存机制避免重复解析
    返回: (font_families_dict, family_names_list)
    """
    global _font_families_cache, _font_families_cache_time
    
    # 检查缓存是否有效（使用配置的缓存时间）
    current_time = time.time()
    cache_duration = FONT_SCAN_CONFIG.get('cache_duration', 30)
    if (_font_families_cache is not None and 
        current_time - _font_families_cache_time < cache_duration):
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Using cached font families ({len(_font_families_cache[0])} families)")
            # 调试：显示缓存的前几个字体名称
            cached_names = _font_families_cache[1]
            print(f"[WBLESS] 缓存的字体列表前10项: {cached_names[:10]}")
        return _font_families_cache
    
    if FONT_SCAN_CONFIG.get('enable_debug', False):
        print(f"[WBLESS] Starting enhanced font family parsing (local + system fonts)...")
    
    # 首先获取本地字体（WBLESS工程目录下的fonts文件夹）
    local_fonts = get_local_fonts()
    
    # 然后获取系统字体
    system_fonts = get_system_fonts()
    
    # 整合字体：本地字体优先，系统字体补充
    font_families = {}
    
    # 先添加本地字体
    for family_name, weights in local_fonts.items():
        font_families[family_name] = weights.copy()
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Local font family: {family_name} ({list(weights.keys())})")
    
    # 再添加系统字体（避免覆盖本地字体）
    for family_name, weights in system_fonts.items():
        if family_name in font_families:
            # 如果家族已存在（本地字体），只添加不重复的字重
            for weight_name, font_path in weights.items():
                if weight_name not in font_families[family_name]:
                    font_families[family_name][weight_name] = font_path
        else:
            # 如果家族不存在，直接添加
            font_families[family_name] = weights.copy()
    
    # 如果没有找到任何字体，确保有基本的回退
    if not font_families:
        print(f"[WBLESS] Warning: No fonts found, using minimal fallback")
        font_families = {"System Default": {"Regular": None}}
    
    # 获取排序后的家族名称列表（智能排序：本地字体 > 中文字体 > 英文字体）
    family_names = smart_sort_font_families_with_local(list(font_families.keys()), local_fonts)
    
    # 为本地字体和系统字体添加分类标题
    if FONT_SCAN_CONFIG.get('enable_debug', False):
        print(f"[WBLESS] 开始字体分类处理...")
        print(f"[WBLESS] 本地字体数: {len(local_fonts)}, 系统字体数: {len(system_fonts)}")
        print(f"[WBLESS] 排序前的family_names: {family_names[:10]}...")  # 只显示前10个
    
    if local_fonts or system_fonts:
        # 分离本地字体和系统字体，保持各自的排序
        local_font_names = []
        system_font_names = []
        
        # 分离本地字体和系统字体
        for name in family_names:
            if name in local_fonts:
                local_font_names.append(name)
                if FONT_SCAN_CONFIG.get('enable_debug', False) and len(local_font_names) <= 5:
                    print(f"[WBLESS] 本地字体: {name}")
            else:
                system_font_names.append(name)
                if FONT_SCAN_CONFIG.get('enable_debug', False) and len(system_font_names) <= 5:
                    print(f"[WBLESS] 系统字体: {name}")
        
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] 分离结果 - 本地: {len(local_font_names)}, 系统: {len(system_font_names)}")
        
        # 重建列表：先本地字体，后系统字体
        new_family_names = []
        
        if local_font_names:
            new_family_names.append("📁 本地字体")
            new_family_names.extend(local_font_names)
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] 添加本地字体标题和 {len(local_font_names)} 个本地字体")
        
        if system_font_names:
            new_family_names.append("🖥️ 系统字体")
            new_family_names.extend(system_font_names)
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] 添加系统字体标题和 {len(system_font_names)} 个系统字体")
        
        family_names = new_family_names
        
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] 最终分类结果前10项: {family_names[:10]}")
    else:
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] 没有找到本地字体或系统字体，跳过分类")
    
    # 打印解析结果用于调试
    if FONT_SCAN_CONFIG.get('enable_debug', False):
        print(f"[WBLESS] Total font families: {len(font_families)} ({len(local_fonts)} local, {len(system_fonts)} system)")
        if local_fonts:
            print(f"[WBLESS] Local font families:")
            for family in local_fonts.keys():
                print(f"  📁 {family}")
    
    # 更新缓存
    _font_families_cache = (font_families, family_names)
    _font_families_cache_time = current_time
    
    return font_families, family_names

def enable_font_debug():
    """
    启用字体扫描调试模式
    这将输出详细的字体扫描信息，用于诊断字体识别问题
    """
    global FONT_SCAN_CONFIG
    FONT_SCAN_CONFIG['enable_debug'] = True  # 修复：启用调试时应该设置为True
    FONT_SCAN_CONFIG['cache_duration'] = 300  # 恢复5分钟缓存
    print("[WBLESS] Font debugging enabled. Next font scan will show detailed information.")

def disable_font_debug():
    """
    禁用字体扫描调试模式
    """
    global FONT_SCAN_CONFIG
    FONT_SCAN_CONFIG['enable_debug'] = False
    FONT_SCAN_CONFIG['cache_duration'] = 30  # 恢复正常缓存
    print("[WBLESS] Font debugging disabled.")

def clear_font_cache():
    """
    清除字体缓存，强制重新扫描字体
    """
    global _font_families_cache, _font_families_cache_time
    _font_families_cache = None
    _font_families_cache_time = 0
    print("[WBLESS] Font cache cleared. Next font scan will be fresh.")

def get_font_scan_stats():
    """
    获取字体扫描统计信息
    """
    if _font_families_cache:
        font_families, family_names = _font_families_cache
        total_weights = sum(len(weights) for weights in font_families.values())
        return {
            'families': len(family_names),
            'total_fonts': total_weights,
            'cache_age': time.time() - _font_families_cache_time,
            'family_names': family_names[:10]  # 前10个作为示例
        }
    return None

def is_chinese_text(text):
    """
    检测文本是否包含中文字符
    返回: (is_chinese, is_traditional)
    """
    import re
    # 中文字符范围
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
    
    if not chinese_pattern.search(text):
        return False, False
    
    # 常见的繁体中文字符（扩展列表，包含更多繁体字）
    traditional_chars = set('傳統體繁體華發變註專觀點為過與關於從來對時間問題設計開發製作動畫標準網頁應用程式系統資料庫檔案處理計畫項目團隊組織學習課程訓練測試檢查覆蓋範圍儷細標楷')
    
    # 常见的繁体中文字体名称关键词
    traditional_font_keywords = {'華', '標楷', '細明', '儷', '繁', '傳統'}
    
    # 检测是否为繁体中文
    chinese_chars = chinese_pattern.findall(text)
    traditional_count = sum(1 for char in chinese_chars if char in traditional_chars)
    
    # 检查是否包含明确的繁体字体关键词
    has_traditional_keywords = any(keyword in text for keyword in traditional_font_keywords)
    
    # 如果包含繁体字体关键词，或者繁体字符超过10%，认为是繁体中文
    is_traditional = has_traditional_keywords or (len(chinese_chars) > 0 and (traditional_count / len(chinese_chars)) > 0.1)
    
    return True, is_traditional

def smart_sort_font_families(family_names):
    """
    智能排序字体家族名称
    优先级：简体中文 > 繁体中文 > 英文和其他语言
    """
    def family_sort_key(name):
        is_chinese, is_traditional = is_chinese_text(name)
        
        if is_chinese:
            if is_traditional:
                # 繁体中文：优先级2
                return (2, name)
            else:
                # 简体中文：优先级1（最高）
                return (1, name)
        else:
            # 英文和其他语言：优先级3（最低）
            return (3, name)
    
    return sorted(family_names, key=family_sort_key)

def smart_sort_font_families_with_local(family_names, local_fonts):
    """
    智能排序字体家族名称，优先显示本地字体
    优先级：本地字体 > 简体中文 > 繁体中文 > 英文和其他语言
    """
    def family_sort_key(name):
        # 检查是否为本地字体
        is_local = name in local_fonts
        
        # 检查语言类型
        is_chinese, is_traditional = is_chinese_text(name)
        
        if is_local:
            # 本地字体：优先级0（最高），再按语言分类
            if is_chinese:
                if is_traditional:
                    return (0, 2, name)  # 本地繁体中文
                else:
                    return (0, 1, name)  # 本地简体中文
            else:
                return (0, 3, name)  # 本地英文/其他语言
        else:
            # 系统字体：优先级1-3
            if is_chinese:
                if is_traditional:
                    return (2, name)  # 系统繁体中文
                else:
                    return (1, name)  # 系统简体中文
            else:
                return (3, name)  # 系统英文/其他语言
    
    return sorted(family_names, key=family_sort_key)

def smart_sort_font_weights(weights):
    """
    智能排序字重，数字字重按数值排序，文本字重按字母排序
    """
    def weight_sort_key(weight):
        # 提取字重中的数字部分
        import re
        numbers = re.findall(r'\d+', weight)
        if numbers:
            # 如果包含数字，使用数字作为主要排序键
            primary_number = int(numbers[0])
            return (0, primary_number, weight)  # 数字字重排在前面，按数值大小排序
        else:
            # 如果是文本字重，按预定义顺序排序
            text_order = {
                'thin': 1, 'extralight': 2, 'ultra light': 2, 'light': 3,
                'normal': 4, 'regular': 4, 'book': 5, 'medium': 6,
                'semibold': 7, 'demibold': 7, 'bold': 8, 'extrabold': 9,
                'ultra bold': 9, 'black': 10, 'heavy': 11, 'extra black': 12
            }
            weight_lower = weight.lower()
            text_priority = text_order.get(weight_lower, 999)
            return (1, text_priority, weight)  # 文本字重排在数字字重后面
    
    return sorted(weights, key=weight_sort_key)

def get_font_weights_for_family(font_families, family_name):
    """
    获取指定字体家族的所有字重选项
    过滤掉空字重，确保只返回有效的字重
    """
    if family_name in font_families:
        # 过滤掉空字重
        weights = [w for w in font_families[family_name].keys() if w and w.strip()]
        if weights:
            return smart_sort_font_weights(weights)
    return ["Regular"]

def get_font_file_from_family_and_weight(font_families, family_name, weight_name):
    """
    根据字体家族和字重获取实际的字体文件路径
    支持本地字体和系统字体的绝对路径
    """
    if family_name in font_families and weight_name in font_families[family_name]:
        font_path = font_families[family_name][weight_name]
        
        # 验证字体文件是否存在
        if font_path and os.path.exists(font_path) and os.access(font_path, os.R_OK):
            return font_path
        else:
            if FONT_SCAN_CONFIG.get('enable_debug', False):
                print(f"[WBLESS] Font file not accessible: {font_path}")
    
    # 回退到第一个可用的字体文件
    if family_name in font_families:
        for weight, font_path in font_families[family_name].items():
            if font_path and os.path.exists(font_path) and os.access(font_path, os.R_OK):
                if FONT_SCAN_CONFIG.get('enable_debug', False):
                    print(f"[WBLESS] Using fallback font: {family_name} {weight}")
                return font_path
    
    if FONT_SCAN_CONFIG.get('enable_debug', False):
        print(f"[WBLESS] No accessible font found for {family_name} {weight_name}")
    
    return None  # 如果找不到字体，返回None让系统使用默认字体

def hex_to_rgb(hex_color):
    """将十六进制颜色转换为RGB元组"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_color_values(font_color, font_color_hex):
    """获取颜色的RGB值，支持预设颜色和自定义十六进制颜色"""
    # 处理可能的列表类型输入
    if isinstance(font_color, list):
        font_color = font_color[0] if font_color else "white"
    if isinstance(font_color_hex, list):
        font_color_hex = font_color_hex[0] if font_color_hex else "#FFFFFF"
    
    if font_color == "custom":
        return hex_to_rgb(font_color_hex)
    else:
        return COLOR_MAPPING.get(font_color, (255, 255, 255))  # 默认为白色

def get_text_size(draw, text, font):
    """获取文本的宽度和高度"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    return text_width, text_height

def align_text(align, img_height, text_height, text_pos_y, margins):
    """计算文本垂直对齐位置"""
    if align == "center":
        text_plot_y = img_height / 2 - text_height / 2 + text_pos_y
        # 对于居中对齐，margins作为额外的垂直偏移
        text_plot_y += margins
    elif align == "top":
        text_plot_y = text_pos_y + margins                       
    elif align == "bottom":
        text_plot_y = img_height - text_height + text_pos_y - margins 
    return text_plot_y        

def justify_text(justify, img_width, line_width, margins):
    """计算文本水平对齐位置"""
    if justify == "left":
        text_plot_x = 0 + margins
    elif justify == "right":
        text_plot_x = img_width - line_width - margins
    elif justify == "center":
        text_plot_x = img_width/2 - line_width/2
        # 对于居中对齐，margins作为额外的水平偏移
        text_plot_x += margins
    return text_plot_x


def wrap_text_to_width(text, font, max_width, letter_spacing=0):
    """
    将文本按指定宽度自动换行（在最大宽度处直接换行，不考虑单词边界）
    
    Args:
        text (str): 要换行的文本
        font: PIL字体对象
        max_width (int): 最大宽度（像素）
        letter_spacing (int): 字间距
    
    Returns:
        str: 换行后的文本（用\n分隔）
    """
    if not text or max_width <= 0:
        return text
    
    # 创建一个临时绘图上下文来测量文本
    temp_img = Image.new('RGB', (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # 将文本按现有的换行符分割
    paragraphs = text.split('\n')
    wrapped_paragraphs = []
    
    for paragraph in paragraphs:
        if not paragraph.strip():
            wrapped_paragraphs.append("")
            continue
            
        wrapped_lines = []
        current_line = ""
        
        # 逐字符处理，不考虑单词边界
        for char in paragraph:
            # 计算添加这个字符后的行宽
            test_line = current_line + char
            
            # 计算测试行的实际宽度（考虑字间距）
            if letter_spacing == 0:
                line_width, _ = get_text_size(temp_draw, test_line, font)
            else:
                line_width = 0
                for i, c in enumerate(test_line):
                    char_width, _ = get_text_size(temp_draw, c, font)
                    line_width += char_width
                    if i < len(test_line) - 1:  # 最后一个字符后不加间距
                        line_width += letter_spacing
            
            # 如果测试行宽度超过限制且当前行不为空，开始新行
            if line_width > max_width and current_line:
                wrapped_lines.append(current_line)
                current_line = char
            else:
                current_line = test_line
        
        # 添加最后一行
        if current_line:
            wrapped_lines.append(current_line)
        
        wrapped_paragraphs.extend(wrapped_lines)
    
    return '\n'.join(wrapped_paragraphs)



def draw_masked_text(text_mask, text, font_name, font_size, letter_spacing, line_spacing,
                     position_x, position_y, align, justify, rotation_angle, rotation_options, 
                     italic=False, bold=False, underline=False, strikethrough=False, 
                     text_case="normal", vertical_align="normal"):
    """
    在文本遮罩上绘制文本，支持多行文本、对齐、间距、旋转和字形样式
    参考 ComfyRoll 的 draw_masked_text 函数实现
    """
    # debug: draw_masked_text called
    # 安全地处理可能的列表类型参数
    def safe_param(value, default, param_type=str):
        if isinstance(value, list):
            value = value[0] if value else default
        if param_type == int:
            return int(value) if value is not None else default
        elif param_type == float:
            return float(value) if value is not None else default
        elif param_type == bool:
            return bool(value) if value is not None else default
        else:
            return str(value) if value is not None else default
    
    # 确保所有数值参数都是正确的类型
    font_size = safe_param(font_size, 50, int)
    letter_spacing = safe_param(letter_spacing, 0, int)
    line_spacing = safe_param(line_spacing, 0, int)
    position_x = safe_param(position_x, 0, int)
    position_y = safe_param(position_y, 0, int)
    rotation_angle = safe_param(rotation_angle, 0.0, float)
    italic_enabled = safe_param(italic, False, bool)
    bold_enabled = safe_param(bold, False, bool)
    underline_enabled = safe_param(underline, False, bool)
    strikethrough_enabled = safe_param(strikethrough, False, bool)
    text_case_mode = safe_param(text_case, "normal", str)
    vertical_align_mode = safe_param(vertical_align, "normal", str)
    align = safe_param(align, "center", str)
    justify = safe_param(justify, "center", str)
    rotation_options = safe_param(rotation_options, "text center", str)
    
    # debug: letter_spacing and alignment params

    # 创建绘图上下文
    draw = ImageDraw.Draw(text_mask)

    # 设置字体路径
    # font_name现在可能是本地字体或系统字体的绝对路径，或None
    if font_name is None:
        font_path = None
    elif os.path.isabs(font_name) and os.path.exists(font_name) and os.access(font_name, os.R_OK):
        # 如果是有效且可读的绝对路径（本地字体或系统字体），直接使用
        font_path = font_name
        if FONT_SCAN_CONFIG.get('enable_debug', False) and WBLESS_PATH in font_name:
            print(f"[WBLESS] Using local font: {os.path.basename(font_name)}")
    else:
        # 如果路径无效或不可读，使用None让系统选择默认字体
        font_path = None
        if FONT_SCAN_CONFIG.get('enable_debug', False) and font_name:
            print(f"[WBLESS] Invalid font path, using default: {font_name}")
    
    try:
        # 尝试加载指定字体
        if font_path:
            font = ImageFont.truetype(font_path, size=font_size)
            # Successfully loaded font
        else:
            # 如果没有指定字体路径，使用默认字体
            font = ImageFont.load_default()
            # Using default font
    except (IOError, OSError) as e:
        print(f"[WBLESS] Error loading font '{font_path}': {e}. Using default font.")
        font = ImageFont.load_default()

    # 分割文本为行
    text_lines = text.split('\n')
    
    # 应用文本大小写转换
    if text_case_mode != "normal":
        transformed_lines = []
        for line in text_lines:
            if text_case_mode == "uppercase":
                transformed_lines.append(line.upper())
            elif text_case_mode == "lowercase":
                transformed_lines.append(line.lower())
            elif text_case_mode == "capitalize":
                transformed_lines.append(line.capitalize())
            elif text_case_mode == "title":
                transformed_lines.append(line.title())
            else:
                transformed_lines.append(line)
        text_lines = transformed_lines
        # Applied text case transformation

    # 计算文本尺寸
    max_text_width = 0
    max_text_height = 0

    for line in text_lines:
        if letter_spacing == 0:
            # 没有字间距时使用原始方法
            line_width, line_height = get_text_size(draw, line, font)
        else:
            # 有字间距时计算总宽度
            line_width = 0
            for i, char in enumerate(line):
                char_width, char_height = get_text_size(draw, char, font)
                line_width += char_width
                if i < len(line) - 1:  # 最后一个字符后不加间距
                    line_width += letter_spacing
            _, line_height = get_text_size(draw, line, font)
        
        line_height = line_height + line_spacing
        max_text_width = max(max_text_width, line_width)
        max_text_height = max(max_text_height, line_height)
    
    # 获取图像尺寸
    image_width, image_height = text_mask.size
    image_center_x = image_width / 2
    image_center_y = image_height / 2

    text_pos_y = position_y
    sum_text_plot_y = 0
    text_height = max_text_height * len(text_lines)
    
    # 创建高级文本绘制函数，支持各种样式效果
    def draw_styled_text(draw_obj, pos, text_content, font_obj, fill_color=255, 
                        enable_underline=None, enable_strikethrough=None):
        """绘制带样式的文本"""
        x, y = pos
        
        # 处理上标/下标的垂直偏移和字体大小调整
        if vertical_align_mode == "superscript":
            # 上标：字体缩小70%，位置上移30%
            adjusted_font_size = int(font_size * 0.7)
            y_offset = -int(font_size * 0.3)
            try:
                if font_path:
                    adjusted_font = ImageFont.truetype(font_path, size=adjusted_font_size)
                else:
                    adjusted_font = ImageFont.load_default()
            except:
                adjusted_font = font_obj
            y += y_offset
        elif vertical_align_mode == "subscript":
            # 下标：字体缩小70%，位置下移20%
            adjusted_font_size = int(font_size * 0.7)
            y_offset = int(font_size * 0.2)
            try:
                if font_path:
                    adjusted_font = ImageFont.truetype(font_path, size=adjusted_font_size)
                else:
                    adjusted_font = ImageFont.load_default()
            except:
                adjusted_font = font_obj
            y += y_offset
        else:
            adjusted_font = font_obj
        
        # 获取当前使用的字体大小（考虑上下标调整）
        current_font_size = font_size
        if vertical_align_mode == "superscript" or vertical_align_mode == "subscript":
            current_font_size = int(font_size * 0.7)
        
        # 绘制主文本（如果启用加粗，使用多次绘制模拟）
        if bold_enabled:
            # 加粗效果偏移量根据字体大小自动调整
            bold_offset = max(1, current_font_size // 30)  # 字体越大，偏移越大
            # Bold offset applied
            
            # 在周围位置绘制文本来模拟加粗
            for dx in range(-bold_offset, bold_offset + 1):
                for dy in range(-bold_offset, bold_offset + 1):
                    if dx != 0 or dy != 0:  # 不在原位置重复绘制
                        draw_obj.text((x + dx, y + dy), text_content, font=adjusted_font, fill=fill_color)
        
        # 绘制主文本
        draw_obj.text((x, y), text_content, font=adjusted_font, fill=fill_color)
        
        # 获取文本的精确边界框
        try:
            # 使用textbbox获取文本的精确边界
            bbox = draw_obj.textbbox((x, y), text_content, font=adjusted_font)
            text_left, text_top, text_right, text_bottom = bbox
            text_width = text_right - text_left
            text_actual_bottom = text_bottom
            text_actual_top = text_top
            # Text bbox calculated
        except:
            # 如果textbbox不可用，使用备用方法
            text_width, text_height = get_text_size(draw_obj, text_content, adjusted_font)
            text_actual_bottom = y + text_height
            text_actual_top = y
            # Fallback text size calculated
        
        # 决定是否绘制下划线和删除线
        should_draw_underline = underline_enabled if enable_underline is None else enable_underline
        should_draw_strikethrough = strikethrough_enabled if enable_strikethrough is None else enable_strikethrough
        
        # 绘制下划线（紧贴文字底部）
        if should_draw_underline:
            # 下划线应该紧贴在文字的实际底部
            underline_y = text_actual_bottom + 1  # 在文字底部下方1像素
            underline_thickness = max(1, current_font_size // 20)  # 根据当前字体大小调整粗细
            # Underline drawn
            for i in range(underline_thickness):
                draw_obj.line([(x, underline_y + i), (x + text_width, underline_y + i)], fill=fill_color)
        
        # 绘制删除线（基于文字实际高度）
        if should_draw_strikethrough:
            # 基于文字的实际边界计算删除线位置
            text_height_actual = text_actual_bottom - text_actual_top
            # 删除线位置在文字实际高度的中心（约50%位置）
            strikethrough_y = text_actual_top + int(text_height_actual * 0.5)
            strikethrough_thickness = max(1, current_font_size // 25)  # 根据当前字体大小调整粗细
            
            # Strikethrough drawn
            for i in range(strikethrough_thickness):
                draw_obj.line([(x, strikethrough_y + i), (x + text_width, strikethrough_y + i)], fill=fill_color)

    for line in text_lines:
        # 如果没有字间距，使用原始方法绘制
        if letter_spacing == 0:
            # 计算当前行的宽度
            line_width, _ = get_text_size(draw, line, font)
                                
            # 获取每行的x和y位置 (margins设为0，因为现在不再使用margins)
            text_plot_x = position_x + justify_text(justify, image_width, line_width, 0)
            text_plot_y = align_text(align, image_height, text_height, text_pos_y, 0)
            
            # 在文本遮罩上绘制当前行（使用高级样式）
            # Drawing styled text
            draw_styled_text(draw, (text_plot_x, text_plot_y), line, font)
        else:
            # 有字间距时，逐个字符绘制，但下划线和删除线在整行绘制完成后统一处理
            # 计算带字间距的总行宽
            total_line_width = 0
            for i, char in enumerate(line):
                char_width, _ = get_text_size(draw, char, font)
                total_line_width += char_width
                if i < len(line) - 1:  # 最后一个字符后不加间距
                    total_line_width += letter_spacing
            
            # 获取起始位置
            text_plot_x = position_x + justify_text(justify, image_width, total_line_width, 0)
            text_plot_y = align_text(align, image_height, text_height, text_pos_y, 0)
            
            # 逐个字符绘制（不包含下划线和删除线）
            current_x = text_plot_x
            for i, char in enumerate(line):
                char_width, _ = get_text_size(draw, char, font)
                # Drawing styled char without underline/strikethrough
                draw_styled_text(draw, (current_x, text_plot_y), char, font, 
                               enable_underline=False, enable_strikethrough=False)
                current_x += char_width
                if i < len(line) - 1:  # 最后一个字符后不加间距
                    current_x += letter_spacing
            
            # 在整行绘制完成后，统一绘制下划线和删除线
            if underline_enabled or strikethrough_enabled:
                # 获取整行文本的边界信息
                line_bbox = draw.textbbox((text_plot_x, text_plot_y), line, font=font)
                line_text_top = line_bbox[1]
                line_text_bottom = line_bbox[3]
                line_text_height = line_text_bottom - line_text_top
                
                # 获取当前使用的字体大小（考虑上下标调整）
                current_font_size = font_size
                if vertical_align_mode == "superscript" or vertical_align_mode == "subscript":
                    current_font_size = int(font_size * 0.7)
                
                # 绘制整行下划线
                if underline_enabled:
                    underline_y = line_text_bottom + 1  # 在文字底部下方1像素
                    underline_thickness = max(1, current_font_size // 20)
                    for i in range(underline_thickness):
                        draw.line([(text_plot_x, underline_y + i), 
                                 (text_plot_x + total_line_width, underline_y + i)], 
                                fill=255)  # 使用白色填充（遮罩模式）
                
                # 绘制整行删除线
                if strikethrough_enabled:
                    strikethrough_y = line_text_top + int(line_text_height * 0.5)
                    strikethrough_thickness = max(1, current_font_size // 25)
                    for i in range(strikethrough_thickness):
                        draw.line([(text_plot_x, strikethrough_y + i), 
                                 (text_plot_x + total_line_width, strikethrough_y + i)], 
                                fill=255)  # 使用白色填充（遮罩模式）
        
        text_pos_y += max_text_height  # 移动到下一行
        sum_text_plot_y += text_plot_y  # 累加y位置

    # 计算旋转中心
    text_center_x = text_plot_x + max_text_width / 2
    text_center_y = sum_text_plot_y / len(text_lines)

    # 应用倾斜变换（如果启用）
    if italic_enabled:
        # 使用行业标准倾斜角度
        italic_angle = STANDARD_ITALIC_ANGLE
        # Applying italic transformation
        # 将角度转换为弧度并计算倾斜系数
        import math
        skew_radians = math.radians(italic_angle)
        skew_factor = math.tan(skew_radians)
        
        # 获取图像尺寸
        width, height = text_mask.size
        
        # 找到文本的实际边界
        bbox = text_mask.getbbox()
        if bbox:
            text_left, text_top, text_right, text_bottom = bbox
            actual_text_width = text_right - text_left
            actual_text_height = text_bottom - text_top
            
            # 重新设计倾斜变换：以底部基线为锚点
            # 这样倾斜后文字底部保持在原位，顶部向右移动，不会向左伸出
            text_baseline_y = text_bottom  # 使用文本底部作为基线
            
            # Using baseline anchor
            
            # 以底部基线为锚点进行倾斜变换
            # 倾斜变换：x' = x + (y - baseline_y) * skew_factor
            # 这样底部基线(baseline_y)的点保持不动，其他点根据与基线的距离进行倾斜
            
            # 根据justify值，我们可能需要在基线锚点的基础上进行一些调整
            if justify == "left":
                # 左对齐：以左下角为最终锚点
                # 计算左下角位置，并以此为基准
                baseline_anchor_x = text_left
                anchor_description = "left baseline"
            elif justify == "right":
                # 右对齐：以右下角为最终锚点
                baseline_anchor_x = text_right  
                anchor_description = "right baseline"
            else:  # center
                # 居中：以底部中心为锚点
                baseline_anchor_x = text_left + actual_text_width / 2
                anchor_description = "center baseline"
            
            # 计算以底部基线为锚点的倾斜变换
            # 标准倾斜变换: x' = x + y * skew_factor (以原点为锚点)
            # 以任意点(anchor_x, anchor_y)为锚点的倾斜变换:
            # x' = x + (y - anchor_y) * skew_factor
            # 展开: x' = x + y * skew_factor - anchor_y * skew_factor
            # 变换矩阵: (1, skew_factor, -anchor_y * skew_factor, 0, 1, 0)
            
            anchor_y = text_baseline_y  # 使用底部基线作为y锚点
            compensation_x = -anchor_y * skew_factor
            
            # Baseline anchor set
            # Baseline compensation calculated
            
            # 构建以底部基线为锚点的倾斜变换矩阵
            transform_matrix = (1, skew_factor, compensation_x, 0, 1, 0)
            
            # Transform matrix applied
            
            # 应用倾斜变换
            text_mask = text_mask.transform(
                (width, height),
                Image.AFFINE,
                transform_matrix,
                resample=Image.Resampling.BICUBIC,
                fillcolor=0  # 透明填充
            )
        else:
            # No text content for italic transformation
            pass

    # 应用旋转（修复旋转方向，使其与预览窗口一致）
    if rotation_angle != 0.0:
        import math
        
        # 创建更大的临时画布以防止旋转时文本被裁剪
        width, height = text_mask.size
        # 计算旋转后可能需要的最大尺寸
        diagonal = math.sqrt(width**2 + height**2)
        expanded_size = int(diagonal * 1.2)  # 减少安全边距，避免过度裁剪
        
        # 创建更大的临时画布
        expanded_mask = Image.new('L', (expanded_size, expanded_size), 0)
        
        # 将原始文本遮罩居中粘贴到扩展画布上
        paste_x = (expanded_size - width) // 2
        paste_y = (expanded_size - height) // 2
        expanded_mask.paste(text_mask, (paste_x, paste_y))
        
        # 调整旋转中心到扩展画布的坐标系
        if rotation_options == "text center":
            adjusted_center_x = text_center_x + paste_x
            adjusted_center_y = text_center_y + paste_y
        elif rotation_options == "image center":
            # 图像中心应该是原始图像的中心位置在扩展画布中的坐标
            adjusted_center_x = image_center_x + paste_x
            adjusted_center_y = image_center_y + paste_y
        else:
            # 默认使用文本中心
            adjusted_center_x = text_center_x + paste_x
            adjusted_center_y = text_center_y + paste_y
        
        # 调试信息
        # print(f"[WBLESS] Text rotation: angle={rotation_angle}, center=({adjusted_center_x:.1f}, {adjusted_center_y:.1f}), option={rotation_options}, expanded_size={expanded_size}")
        
        # 在扩展画布上进行旋转，使用兼容的方法
        try:
            # 先尝试使用center参数
            rotated_expanded_mask = expanded_mask.rotate(
                -rotation_angle,  # 使用负角度，PIL和Canvas坐标系相反
                center=(adjusted_center_x, adjusted_center_y),
                resample=Image.Resampling.BICUBIC,  # 兼容的高质量重采样
                fillcolor=0  # 透明填充（灰度图像使用0）
            )
            # print(f"[WBLESS] Text block rotate with center parameter")
        except TypeError:
            # 如果center参数不支持，使用传统方法
            rotated_expanded_mask = expanded_mask.rotate(
                -rotation_angle,
                resample=Image.Resampling.BICUBIC,
                fillcolor=0
            )
            # print(f"[WBLESS] Text block rotate without center parameter (fallback)")
        
        # 将旋转后的结果裁剪回原始尺寸
        rotated_text_mask = rotated_expanded_mask.crop((paste_x, paste_y, paste_x + width, paste_y + height))
    else:
        rotated_text_mask = text_mask
        
    return rotated_text_mask

class TextBlock(CozyBaseNode):
    NAME = "Text Block"
    RETURN_TYPES = ("TEXT_BLOCK",)
    RETURN_NAMES = ("text_block",)
    
    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        """
        强制禁用缓存，确保前端参数更改能实时生效
        """
        return time.time()

    @classmethod
    def INPUT_TYPES(cls):
        try:
            # 解析字体家族
            font_families, family_names = parse_font_families()
            
            # 确保至少有一个字体家族
            if not family_names:
                family_names = ["Arial"]
                font_families = {"Arial": {"Regular": "arial.ttf"}}
            # 注意：不要在这里重新排序family_names，因为parse_font_families()已经完成了正确的分类和排序
        except Exception as e:
            print(f"[WBLESS] Error parsing font families: {e}")
            # 使用默认字体作为回退
            family_names = ["Arial"]
            font_families = {"Arial": {"Regular": "arial.ttf"}}
        
        try:
            # 获取第一个家族的字重选项作为默认
            default_family = family_names[0]
            default_weights = get_font_weights_for_family(font_families, default_family)
            
            # 创建所有可能的字重选项（用于前端动态更新）
            all_weights = set()
            for family_weights in font_families.values():
                all_weights.update(family_weights.keys())
            all_weights_list = smart_sort_font_weights(list(all_weights))
        except Exception as e:
            print(f"[WBLESS] Error processing font weights: {e}")
            all_weights_list = ["Regular"]
        
        # 定义颜色选项
        COLORS = ["custom", "white", "black", "red", "green", "blue", "yellow",
                  "cyan", "magenta", "orange", "purple", "pink", "brown", "gray",
                  "lightgray", "darkgray", "olive", "lime", "teal", "navy", "maroon",
                  "fuchsia", "aqua", "silver", "gold", "turquoise", "lavender",
                  "violet", "coral", "indigo"]
        

        
        # 定义旋转选项
        ROTATE_OPTIONS = ["text center", "image center"]
        
        # 先创建字体字重映射
        font_weight_map = {}
        for family, weights in font_families.items():
            weight_list = [w for w in weights.keys() if w and w.strip()]
            if weight_list:
                font_weight_map[family] = smart_sort_font_weights(weight_list)
            else:
                font_weight_map[family] = ["Regular"]
        
        # 创建字体家族选项，包含字重信息的自定义属性
        font_family_options = (family_names, {"font_weight_map": font_weight_map})
        
        input_spec = {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "Hello, WBLESS!"}),
                "font_family": font_family_options,  # 字体家族选择，带字重映射信息
                "font_weight": (all_weights_list,),  # 使用所有可能的字重选项
                "font_size": ("INT", {"default": 50, "min": 1, "max": 1024}),
                "font_color": (COLORS,),
                "font_color_hex": ("STRING", {"multiline": False, "default": "#FFFFFF"}),  # 移动到font_color下面
                "letter_spacing": ("INT", {"default": 0, "min": -50, "max": 100}),
                "newline": ("BOOLEAN", {"default": False}),  # 换行控制（原auto_newline功能）
                "auto_newline": ("BOOLEAN", {"default": False}),  # 启用自动换行
                "auto_newline_width": ("INT", {"default": 300, "min": 50, "max": 2048}),  # 自动换行的宽度限制
                "expand_advanced": ("BOOLEAN", {"default": False}),  # 展开高级选项开关
            },
            "optional": {
                "horizontal_spacing": ("INT", {"default": 0, "min": -200, "max": 200}),  # 与后一文本的水平间距
                "vertical_spacing": ("INT", {"default": 0, "min": -200, "max": 200}),    # 与下一文本的垂直间距
                "rotation_angle": ("FLOAT", {"default": 0.0, "min": -360.0, "max": 360.0, "step": 0.1}),  # 单独旋转角度
                "rotation_options": (ROTATE_OPTIONS, {"default": "text center"}),  # 单独旋转选项
                "italic": ("BOOLEAN", {"default": False}),  # 文本倾斜效果（行业标准12°）
                "bold": ("BOOLEAN", {"default": False}),  # 文本加粗效果
                "underline": ("BOOLEAN", {"default": False}),  # 下划线
                "strikethrough": ("BOOLEAN", {"default": False}),  # 删除线（中划线）
                "text_case": (["normal", "uppercase", "lowercase", "capitalize", "title"], {"default": "normal"}),  # 文本大小写转换
                "vertical_align": (["normal", "superscript", "subscript"], {"default": "normal"}),  # 上标/下标
                "opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "set_as_default": ("BOOLEAN", {"default": False}),  # 是否设置为默认值
            }
        }
        
        # 调试输出 - 暂时强制启用来诊断问题
        # Font system initialized
        if FONT_SCAN_CONFIG.get('enable_debug', False):
            print(f"[WBLESS] Font system ready: {len(font_weight_map)} families, {len(all_weights_list)} total weights")
        
        # 将字体字重映射作为隐藏参数传递给前端（转为JSON格式）
        import json
        input_spec["hidden"] = input_spec.get("hidden", {})
        input_spec["hidden"]["font_weight_map"] = ("STRING", {"default": json.dumps(font_weight_map, ensure_ascii=False)})
        
        return input_spec

    def run(self, **kw):
        try:
            # 解析字体家族以获取实际的字体文件名
            font_families, _ = parse_font_families()
        except Exception as e:
            print(f"[WBLESS] Error parsing font families in run: {e}")
            font_families = {"Arial": {"Regular": "arial.ttf"}}
        
        # 安全地获取参数，处理可能的列表类型
        font_family = kw.get("font_family", "Arial")
        font_weight = kw.get("font_weight", "Regular")
        
        # 如果参数是列表，取第一个元素
        if isinstance(font_family, list):
            font_family = font_family[0] if font_family else "Arial"
        if isinstance(font_weight, list):
            font_weight = font_weight[0] if font_weight else "Regular"
        
        try:
            # 获取实际的字体文件路径（现在是绝对路径）
            actual_font_path = get_font_file_from_family_and_weight(font_families, font_family, font_weight)
        except Exception as e:
            print(f"[WBLESS] Error getting font file: {e}")
            actual_font_path = None
        
        # 安全地获取其他参数，处理可能的列表类型
        def safe_get(key, default):
            value = kw.get(key, default)
            return value[0] if isinstance(value, list) and value else (value if value is not None else default)
        
        # 检查是否设置为默认值
        set_as_default = safe_get("set_as_default", False)
        
        text_block = {
            "text": safe_get("text", ""),
            "font_name": actual_font_path,  # 使用实际的字体文件路径（绝对路径）
            "font_family": font_family,  # 保留家族信息
            "font_weight": font_weight,  # 保留字重信息
            "font_size": safe_get("font_size", 50),
            "font_color": safe_get("font_color", "white"),
            "font_color_hex": safe_get("font_color_hex", "#FFFFFF"),
            "letter_spacing": safe_get("letter_spacing", 0),  # 添加字间距参数
            "expand_advanced": safe_get("expand_advanced", False),  # 添加展开高级选项参数
            "newline": safe_get("newline", False),  # 换行参数（原auto_newline功能）
            "auto_newline": safe_get("auto_newline", False),  # 启用自动换行
            "auto_newline_width": safe_get("auto_newline_width", 300),  # 自动换行的宽度限制
            "horizontal_spacing": safe_get("horizontal_spacing", 0),  # 添加水平间距参数
            "vertical_spacing": safe_get("vertical_spacing", 0),      # 添加垂直间距参数
            "rotation_angle": safe_get("rotation_angle", 0.0),       # 添加旋转角度参数
            "rotation_options": safe_get("rotation_options", "text center"),  # 添加旋转选项参数
            "italic": safe_get("italic", False),        # 添加倾斜效果参数
            "bold": safe_get("bold", False),         # 添加加粗效果参数
            "underline": safe_get("underline", False),  # 添加下划线参数
            "strikethrough": safe_get("strikethrough", False),  # 添加删除线参数
            "text_case": safe_get("text_case", "normal"),  # 添加大小写转换参数
            "vertical_align": safe_get("vertical_align", "normal"),  # 添加上标下标参数
            "opacity": safe_get("opacity", 1.0),
            "set_as_default": set_as_default,  # 添加设置为默认值参数
        }
        
        # 默认值逻辑现在完全由前端处理，后端只负责传递set_as_default标志
        # 这样可以确保默认值只在连接到同一个Overlay Text节点的范围内生效
        if set_as_default:
            print(f"[WBLESS] Text Block node marked as default value source")
        
        return (text_block,)

class OverlayText(CozyBaseNode):
    NAME = "Overlay Text"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "text_mask")

    @classmethod
    def INPUT_TYPES(cls):
        # 定义选项常量
        ALIGN_OPTIONS = ["center", "top", "bottom"]
        JUSTIFY_OPTIONS = ["center", "left", "right"]
        ROTATE_OPTIONS = ["text center", "image center"]
        
        # 动态输入：只定义一个可选输入作为前端动态添加的"模板"
        optional_inputs = {
            "text_block_1": ("TEXT_BLOCK",)
        }
        
        return {
            "required": {
                "image": ("IMAGE",),
                "align": (ALIGN_OPTIONS,),
                "justify": (JUSTIFY_OPTIONS,),
                "line_spacing": ("INT", {"default": 0, "min": -1024, "max": 1024}),
                "position_x": ("INT", {"default": 0, "min": -4096, "max": 4096}),
                "position_y": ("INT", {"default": 0, "min": -4096, "max": 4096}),
                "rotation_angle": ("FLOAT", {"default": 0.0, "min": -360.0, "max": 360.0, "step": 0.1}),
                "rotation_options": (ROTATE_OPTIONS,),
            },
            "optional": optional_inputs
        }

    def _tensor_to_pil(self, tensor):
        # 处理不同类型的输入
        if isinstance(tensor, list):
            # 如果已经是列表，递归处理每个元素
            result = []
            for item in tensor:
                result.extend(self._tensor_to_pil(item))
            return result
        
        # 确保是张量类型
        if not hasattr(tensor, 'cpu'):
            # 如果不是张量，尝试转换为numpy数组
            if hasattr(tensor, 'numpy'):
                tensor_np = tensor.numpy()
            else:
                tensor_np = np.array(tensor)
        else:
            # 处理不同的张量形状
            tensor_np = tensor.cpu().numpy()
        
        # 压缩所有大小为1的维度，除了最后的通道维度
        while len(tensor_np.shape) > 3 and tensor_np.shape[0] == 1:
            tensor_np = tensor_np.squeeze(0)
        
        if len(tensor_np.shape) == 4:
            # 批次张量 [batch, height, width, channels]
            return [Image.fromarray(np.clip(255. * img, 0, 255).astype(np.uint8)) for img in tensor_np]
        elif len(tensor_np.shape) == 3:
            # 单张图像 [height, width, channels]
            return [Image.fromarray(np.clip(255. * tensor_np, 0, 255).astype(np.uint8))]
        else:
            raise ValueError(f"Cannot handle tensor shape: {tensor.shape} -> {tensor_np.shape}")

    def _pil_to_tensor(self, pil_images):
        return torch.stack([torch.from_numpy(np.array(img).astype(np.float32) / 255.0) for img in pil_images])
    
    def _masks_to_tensor(self, pil_masks):
        """将PIL遮罩图像转换为ComfyUI遮罩张量"""
        # ComfyUI的遮罩格式：(batch, height, width)，值范围0-1
        return torch.stack([torch.from_numpy(np.array(mask).astype(np.float32) / 255.0) 
                           for mask in pil_masks])

    def run(self, image, align="center", justify="center", line_spacing=0,
            position_x=0, position_y=0, rotation_angle=0.0, rotation_options="text center", **kwargs):
        
        # 调试参数接收
        # OverlayText.run parameters received
        # Parameters: align, justify, line_spacing, position_x, position_y, rotation_angle, rotation_options
        
        # 安全地处理可能的列表类型参数
        def safe_param(value, default, param_type=str):
            if isinstance(value, list):
                value = value[0] if value else default
            if param_type == int:
                try:
                    return int(value) if value is not None else default
                except (ValueError, TypeError):
                    # Error converting to int, using default
                    return default
            elif param_type == float:
                try:
                    return float(value) if value is not None else default
                except (ValueError, TypeError):
                    # Error converting to float, using default
                    return default
            else:
                return str(value) if value is not None else default
        
        # 确保所有数值参数都是正确的类型
        line_spacing = safe_param(line_spacing, 0, int)
        position_x = safe_param(position_x, 0, int)
        position_y = safe_param(position_y, 0, int)
        rotation_angle = safe_param(rotation_angle, 0.0, float)
        align = safe_param(align, "center", str)
        justify = safe_param(justify, "center", str)
        rotation_options = safe_param(rotation_options, "text center", str)
        # Parameters processed
        
        pil_images = self._tensor_to_pil(image)
        output_images = []
        output_masks = []  # 存储输出遮罩

        # 收集所有有效的文本块
        text_blocks = []
        # kwargs keys processed
        
        for i in range(1, MAX_TEXT_BLOCKS + 1):
            key = f"text_block_{i}"
            if key in kwargs and kwargs[key] is not None:
                block_value = kwargs[key]
                # Found text block
                
                # 如果是元组或列表，尝试解包
                if isinstance(block_value, (tuple, list)) and len(block_value) > 0:
                    # 取第一个元素
                    block_value = block_value[0]
                    # Unpacked text block
                
                text_blocks.append(block_value)

        # Text blocks collected
        
        if not text_blocks:
            # No text blocks found, returning original image and empty masks
            pil_images = self._tensor_to_pil(image)
            empty_masks = [Image.new('L', img.size, 0) for img in pil_images]
            return (image, self._masks_to_tensor(empty_masks))

        for img in pil_images:
            # 转换为RGBA以支持透明度
            back_image = img.convert("RGBA")
            
            # 创建当前图像的遮罩画布（用于收集所有文本遮罩）
            final_text_mask = Image.new('L', back_image.size, 0)
            
            # 预计算所有文本块的尺寸，用于智能排列
            text_dimensions = []
            for block in text_blocks:
                if not block or not isinstance(block, dict):
                    text_dimensions.append({"width": 0, "height": 0})
                    continue
                
                # 创建临时绘图上下文来测量文本尺寸
                temp_mask = Image.new('L', back_image.size)
                temp_draw = ImageDraw.Draw(temp_mask)
                
                # 获取字体
                font_name = block.get("font_name", None)  # 现在可能是本地字体或系统字体的绝对路径，或None
                font_size = block.get("font_size", 50)
                letter_spacing_value = block.get("letter_spacing", 0)
                
                # 验证字体路径
                if font_name and os.path.isabs(font_name) and os.path.exists(font_name) and os.access(font_name, os.R_OK):
                    font_path = font_name
                else:
                    font_path = None  # 使用默认字体
                
                try:
                    if font_path:
                        font = ImageFont.truetype(font_path, size=font_size)
                    else:
                        font = ImageFont.load_default()
                except (IOError, OSError):
                    font = ImageFont.load_default()
                
                # 计算文本尺寸
                text = block.get("text", "")
                
                # 检查是否启用自动换行
                auto_newline = block.get("auto_newline", False)
                auto_newline_width = block.get("auto_newline_width", 300)
                
                # 如果启用自动换行，对文本进行换行处理
                if auto_newline and auto_newline_width > 0:
                    text = wrap_text_to_width(text, font, auto_newline_width, letter_spacing_value)
                
                text_lines = text.split('\n')
                max_line_height = 0
                max_line_width = 0
                
                for line in text_lines:
                    if letter_spacing_value == 0:
                        # 没有字间距时使用原始方法
                        line_width, line_height = get_text_size(temp_draw, line, font)
                    else:
                        # 有字间距时计算总宽度
                        line_width = 0
                        for i, char in enumerate(line):
                            char_width, _ = get_text_size(temp_draw, char, font)
                            line_width += char_width
                            if i < len(line) - 1:  # 最后一个字符后不加间距
                                line_width += letter_spacing_value
                        _, line_height = get_text_size(temp_draw, line, font)
                    
                    line_height = line_height + line_spacing
                    max_line_width = max(max_line_width, line_width)
                    max_line_height = max(max_line_height, line_height)
                
                total_text_height = max_line_height * len(text_lines)
                
                # 考虑倾斜效果对文本边界的影响
                italic_enabled = block.get("italic", False)
                adjusted_width = max_line_width
                adjusted_height = total_text_height
                
                if italic_enabled:
                    import math
                    # 使用行业标准倾斜角度
                    italic_angle = STANDARD_ITALIC_ANGLE
                    skew_radians = math.radians(italic_angle)
                    skew_factor = math.tan(skew_radians)
                    
                    # 重新计算基于底部基线锚点的倾斜边界
                    # 以底部基线为锚点时：
                    # - 底部基线保持不动
                    # - 顶部向右移动 height * skew_factor 距离
                    # - 不会向左伸出，解决了重叠问题
                    
                    # 计算倾斜后的实际边界（以底部基线为参考）
                    # 底部基线偏移：0（锚点不动）
                    bottom_x_offset = 0  
                    # 顶部相对于底部基线向右的偏移
                    top_x_offset = total_text_height * skew_factor
                    
                    # 倾斜后的宽度增加（只向右扩展）
                    width_increase = abs(top_x_offset - bottom_x_offset)
                    adjusted_width = max_line_width + width_increase
                    
                    # 对于垂直高度，由于底部基线锚点，文本不会向上伸出
                    # 倾斜只是改变了形状，但垂直占用空间保持不变
                    # 不需要额外的垂直安全边距
                    adjusted_height = total_text_height
                    
                    # Block italic adjustment with baseline anchor calculated
                
                text_dimensions.append({"width": adjusted_width, "height": adjusted_height})
                # Block final dimensions calculated
            
            # 按行分组文本块
            text_lines = []  # 每个元素是一行的文本块列表
            current_line = []
            
            for i, block in enumerate(text_blocks):
                if not block or not isinstance(block, dict):
                    continue
                    
                newline = block.get("newline", False)
                
                # 如果当前文本块设置了换行且不是第一个文本块，开始新行
                if newline and i > 0 and current_line:
                    text_lines.append(current_line)
                    current_line = []
                
                current_line.append({
                    "block": block,
                    "index": i,
                    "dimensions": text_dimensions[i]
                })
            
            # 添加最后一行
            if current_line:
                text_lines.append(current_line)
            
            # Text organized into lines
            # Lines organized with text blocks
            
            # 计算累积垂直偏移
            cumulative_y_offset = 0
            
            # 首先计算所有文本块的原始位置（不考虑旋转）
            text_positions = []  # 存储每个文本块的最终渲染位置
            
            # 预计算所有位置
            for line_idx, line in enumerate(text_lines):
                # Calculating positions for line
                
                # 计算当前行的总宽度
                total_line_width = 0
                for j, item in enumerate(line):
                    total_line_width += item["dimensions"]["width"]
                    if j < len(line) - 1:  # 不是最后一个文本块
                        # 使用当前文本块的水平间距设置
                        horizontal_spacing = item["block"].get("horizontal_spacing", 0)
                        total_line_width += horizontal_spacing
                
                # 计算当前行的起始Y位置
                current_line_y = position_y + cumulative_y_offset
                
                # 基于整行宽度计算起始X位置（整体对齐）
                image_width = back_image.size[0]
                if justify == "left":
                    line_start_x = position_x
                elif justify == "right":
                    line_start_x = position_x + image_width - total_line_width
                elif justify == "center":
                    line_start_x = position_x + (image_width - total_line_width) / 2
                else:
                    line_start_x = position_x
                
                # 计算行内每个文本块的位置
                current_x_in_line = line_start_x
                max_line_height = 0
                max_font_size = 0  # 记录当前行的最大字体大小，用于基线对齐
                
                # 第一遍：找到当前行的最大字体大小
                for j, item in enumerate(line):
                    block = item["block"]
                    font_size = block.get("font_size", 50)
                    max_font_size = max(max_font_size, font_size)
                    max_line_height = max(max_line_height, item["dimensions"]["height"])
                
                # 第二遍：计算基线对齐的位置
                for j, item in enumerate(line):
                    block = item["block"]
                    i = item["index"]
                    dimensions = item["dimensions"]
                    font_size = block.get("font_size", 50)
                    
                    # 计算基线对齐的Y偏移
                    # 使用最大字体大小作为基线参考，确保同一行中所有文本共享相同的基线
                    baseline_offset = (max_font_size - font_size) * 0.8  # 0.8是基线比例因子
                    adjusted_y = current_line_y + baseline_offset
                    
                    # 存储原始位置（包含基线调整）
                    text_positions.append({
                        "block": block,
                        "index": i,
                        "dimensions": dimensions,
                        "original_x": current_x_in_line,
                        "original_y": adjusted_y,
                        "line_idx": line_idx,
                        "baseline_offset": baseline_offset  # 记录基线偏移，用于调试
                    })
                    
                    # 更新行内X位置
                    current_x_in_line += dimensions["width"]
                    if j < len(line) - 1:  # 不是最后一个文本块
                        horizontal_spacing = block.get("horizontal_spacing", 0)
                        current_x_in_line += horizontal_spacing
                
                # 更新垂直偏移
                cumulative_y_offset += max_line_height
                if line_idx < len(text_lines) - 1:
                    last_block_in_line = line[-1]["block"]
                    vertical_spacing = last_block_in_line.get("vertical_spacing", 0)
                    cumulative_y_offset += vertical_spacing
            
            # 如果需要整体旋转，使用简化的旋转方法
            if rotation_angle != 0.0:
                # Using simplified rotation method 
                
                # 直接在原始画布尺寸上创建文本图像，然后旋转
                import math
                orig_width, orig_height = back_image.size
                
                # 创建与原图同尺寸的透明图像
                temp_text_image = Image.new('RGBA', (orig_width, orig_height), (0, 0, 0, 0))
                
                # 不需要偏移，直接使用原始坐标
                offset_x = 0
                offset_y = 0
                
                # 在临时图像上绘制所有文本（不考虑整体旋转）
                for pos in text_positions:
                    block = pos["block"]
                    i = pos["index"]
                    # 直接使用原始坐标，不需要偏移
                    original_x = pos["original_x"]
                    original_y = pos["original_y"]
                    
                    # Drawing block on temp image
                    
                    # 获取文本块的颜色RGB值
                    font_color = block.get("font_color", "white")
                    font_color_hex = block.get("font_color_hex", "#FFFFFF")
                    text_color = get_color_values(font_color, font_color_hex)
                    
                    # 创建文本图层和遮罩
                    text_image = Image.new('RGB', temp_text_image.size, text_color)
                    text_mask = Image.new('L', temp_text_image.size)
                    
                    # 获取当前文本块的字间距、旋转、倾斜和样式参数
                    block_letter_spacing = block.get("letter_spacing", 0)
                    block_rotation_angle = block.get("rotation_angle", 0.0)
                    block_rotation_options = block.get("rotation_options", "text center")
                    block_italic_enabled = block.get("italic", False)
                    
                    # 获取文本内容并应用自动换行（在旋转渲染阶段）
                    text_content = block.get("text", "")
                    auto_newline = block.get("auto_newline", False)
                    auto_newline_width = block.get("auto_newline_width", 300)
                    
                    # 如果启用自动换行，处理文本
                    if auto_newline and auto_newline_width > 0:
                        # 需要获取字体来进行换行计算
                        font_name = block.get("font_name", None)
                        font_size = block.get("font_size", 50)
                        
                        # 验证字体路径
                        if font_name and os.path.isabs(font_name) and os.path.exists(font_name) and os.access(font_name, os.R_OK):
                            font_path = font_name
                        else:
                            font_path = None
                        
                        try:
                            if font_path:
                                font = ImageFont.truetype(font_path, size=font_size)
                            else:
                                font = ImageFont.load_default()
                        except (IOError, OSError):
                            font = ImageFont.load_default()
                        
                        text_content = wrap_text_to_width(text_content, font, auto_newline_width, block_letter_spacing)
                    
                    # 使用draw_masked_text函数绘制文本
                    rotated_text_mask = draw_masked_text(
                        text_mask, 
                        text_content,
                        block.get("font_name", "arial.ttf"),
                        block.get("font_size", 50),
                        block_letter_spacing,  # 使用Text Block的字间距参数
                        line_spacing,  # 使用Overlay Text节点的参数
                        original_x,  # 使用原始位置
                        original_y,  # 使用原始位置
                        align,  # 使用Overlay Text节点的参数
                        "left",  # 强制使用左对齐，因为我们已经在布局级别处理了对齐
                        block_rotation_angle,  # 使用Text Block的旋转角度
                        block_rotation_options,  # 使用Text Block的旋转选项
                        block_italic_enabled,  # 使用Text Block的倾斜效果
                        block.get("bold", False),  # 使用Text Block的加粗效果
                        block.get("underline", False),  # 使用Text Block的下划线效果
                        block.get("strikethrough", False),  # 使用Text Block的删除线效果
                        block.get("text_case", "normal"),  # 使用Text Block的大小写转换
                        block.get("vertical_align", "normal")  # 使用Text Block的上下标效果
                    )
                    
                    # 应用透明度
                    opacity = block.get("opacity", 1.0)
                    if opacity != 1.0:
                        rotated_text_mask = rotated_text_mask.point(lambda x: int(x * opacity))
                    
                    # 将文本合成到临时图像上（确保正确的透明度处理）
                    text_layer = Image.new('RGBA', temp_text_image.size, (0, 0, 0, 0))
                    text_layer.paste(text_color, mask=rotated_text_mask)
                    temp_text_image = Image.alpha_composite(temp_text_image, text_layer)
                    
                    # 将当前文本块的遮罩合并到最终遮罩中
                    final_text_mask = Image.composite(Image.new('L', final_text_mask.size, 255), 
                                                     final_text_mask, rotated_text_mask)
                
                # 现在旋转整个文本图像
                # Rotating entire text image
                
                # 计算旋转中心（现在在原始画布坐标系中）
                if rotation_options == "image center":
                    # 图像中心
                    rotation_center = (orig_width / 2, orig_height / 2)
                    # print(f"[WBLESS] Using image center rotation")
                else:  # "text center"
                    # 计算所有文本块的加权重心作为文本中心
                    # 重要：需要将文本位置转换到最终的图像坐标系（应用align等参数）
                    try:
                        if text_positions and len(text_positions) > 0:
                            # 首先计算文本的整体高度和边界
                            min_y = min(pos["original_y"] for pos in text_positions)
                            max_y = max(pos["original_y"] + pos["dimensions"]["height"] for pos in text_positions)
                            total_text_height = max_y - min_y
                            
                            # 应用与实际渲染相同的对齐逻辑
                            image_height = orig_height
                            image_center_y = image_height / 2
                            
                            # 计算align参数导致的Y偏移
                            if align == "center":
                                # 文本整体居中
                                align_offset_y = image_center_y - total_text_height / 2 - min_y
                            elif align == "top":
                                # 文本顶部对齐（考虑position_y）
                                align_offset_y = position_y - min_y
                            elif align == "bottom":
                                # 文本底部对齐
                                align_offset_y = (image_height - total_text_height + position_y) - min_y
                            else:
                                align_offset_y = 0
                            
                            print(f"[WBLESS] Align calculation: align={align}, total_height={total_text_height:.1f}, min_y={min_y:.1f}, align_offset_y={align_offset_y:.1f}")
                            
                            total_weighted_x = 0
                            total_weighted_y = 0
                            total_area = 0
                            
                            # 计算每个文本块的中心和面积，进行加权平均
                            for i, pos in enumerate(text_positions):
                                # 文本块的中心点（应用align偏移到最终图像坐标）
                                block_center_x = pos["original_x"] + pos["dimensions"]["width"] / 2
                                block_center_y = pos["original_y"] + pos["dimensions"]["height"] / 2 + align_offset_y
                                
                                # 文本块的面积作为权重
                                block_area = pos["dimensions"]["width"] * pos["dimensions"]["height"]
                                
                                # 调试信息：显示每个文本块的信息
                                print(f"[WBLESS] Block {i+1}: original_pos=({pos['original_x']:.1f}, {pos['original_y']:.1f}), final_center=({block_center_x:.1f}, {block_center_y:.1f}), area={block_area:.1f}")
                                
                                # 累积加权值
                                total_weighted_x += block_center_x * block_area
                                total_weighted_y += block_center_y * block_area
                                total_area += block_area
                            
                            if total_area > 0:
                                # 计算加权重心
                                text_center_x = total_weighted_x / total_area
                                text_center_y = total_weighted_y / total_area
                                rotation_center = (text_center_x, text_center_y)
                                # 启用调试信息来验证计算
                                print(f"[WBLESS] Text center calculated: ({text_center_x:.1f}, {text_center_y:.1f}) from {len(text_positions)} text blocks")
                            else:
                                # 如果总面积为0，回退到图像中心
                                rotation_center = (orig_width / 2, orig_height / 2)
                                print(f"[WBLESS] Text area is zero, using image center as fallback")
                        else:
                            # 如果没有文本位置信息，回退到图像中心
                            rotation_center = (orig_width / 2, orig_height / 2)
                            print(f"[WBLESS] No text positions found, using image center as fallback")
                    except Exception as e:
                        # 计算失败时，使用图像中心作为安全回退
                        rotation_center = (orig_width / 2, orig_height / 2)
                        print(f"[WBLESS] Error calculating text center: {e}, using image center")
                
                # 调试信息
                print(f"[WBLESS] Final rotation: angle={rotation_angle}, center=({rotation_center[0]:.1f}, {rotation_center[1]:.1f}), option={rotation_options}")
                print(f"[WBLESS] Original image size: {orig_width}x{orig_height}")
                print(f"[WBLESS] Using simplified rotation (no expansion)")
                
                # 旋转文本图像和遮罩，使用兼容的方法
                # 有些PIL版本的center参数可能有问题，使用手动平移+旋转+平移的方法
                try:
                    # 先尝试使用center参数旋转文本图像
                    rotated_text_image = temp_text_image.rotate(
                        -rotation_angle,  # 使用负角度，PIL和Canvas坐标系相反
                        center=rotation_center, 
                        expand=False,  # 不扩展，因为我们已经创建了足够大的画布
                        resample=Image.Resampling.BICUBIC,  # 使用兼容的高质量重采样算法
                        fillcolor=(0, 0, 0, 0)  # 透明填充
                    )
                    
                    # 同时旋转最终遮罩
                    final_text_mask = final_text_mask.rotate(
                        -rotation_angle,  # 使用相同的角度
                        center=rotation_center,
                        expand=False,
                        resample=Image.Resampling.BICUBIC,
                        fillcolor=0  # 黑色填充（遮罩用0表示透明）
                    )
                    # print(f"[WBLESS] Using PIL rotate with center parameter")
                except TypeError:
                    # 如果center参数不支持，使用传统方法（围绕图像中心旋转）
                    rotated_text_image = temp_text_image.rotate(
                        -rotation_angle,
                        resample=Image.Resampling.BICUBIC,
                        fillcolor=(0, 0, 0, 0)
                    )
                    
                    # 同时旋转最终遮罩
                    final_text_mask = final_text_mask.rotate(
                        -rotation_angle,
                        resample=Image.Resampling.BICUBIC,
                        fillcolor=0
                    )
                    # print(f"[WBLESS] Using PIL rotate without center parameter (fallback)")
                
                # 不需要裁剪，因为我们使用的是原始尺寸
                # print(f"[WBLESS] Rotated image size: {rotated_text_image.size}")
                # print(f"[WBLESS] Target size: {orig_width}x{orig_height}")
                
                # 直接将旋转后的文本图像合成到背景图像上
                back_image = Image.alpha_composite(back_image.convert('RGBA'), rotated_text_image)
            else:
                # 不旋转时，直接渲染所有文本块
                for pos in text_positions:
                    block = pos["block"]
                    i = pos["index"]
                    original_x = pos["original_x"]
                    original_y = pos["original_y"]
                    
                    # Rendering block directly
                    
                    # 获取文本块的颜色RGB值
                    font_color = block.get("font_color", "white")
                    font_color_hex = block.get("font_color_hex", "#FFFFFF")
                    text_color = get_color_values(font_color, font_color_hex)
                    
                    # 创建文本图层和遮罩
                    text_image = Image.new('RGB', back_image.size, text_color)
                    text_mask = Image.new('L', back_image.size)
                    
                    # 获取当前文本块的字间距、旋转、倾斜和样式参数
                    block_letter_spacing = block.get("letter_spacing", 0)
                    block_rotation_angle = block.get("rotation_angle", 0.0)
                    block_rotation_options = block.get("rotation_options", "text center")
                    block_italic_enabled = block.get("italic", False)
                    
                    # 获取文本内容并应用自动换行（在直接渲染阶段）
                    text_content = block.get("text", "")
                    auto_newline = block.get("auto_newline", False)
                    auto_newline_width = block.get("auto_newline_width", 300)
                    
                    # 如果启用自动换行，处理文本
                    if auto_newline and auto_newline_width > 0:
                        # 需要获取字体来进行换行计算
                        font_name = block.get("font_name", None)
                        font_size = block.get("font_size", 50)
                        
                        # 验证字体路径
                        if font_name and os.path.isabs(font_name) and os.path.exists(font_name) and os.access(font_name, os.R_OK):
                            font_path = font_name
                        else:
                            font_path = None
                        
                        try:
                            if font_path:
                                font = ImageFont.truetype(font_path, size=font_size)
                            else:
                                font = ImageFont.load_default()
                        except (IOError, OSError):
                            font = ImageFont.load_default()
                        
                        text_content = wrap_text_to_width(text_content, font, auto_newline_width, block_letter_spacing)
                    
                    # 使用draw_masked_text函数绘制文本
                    rotated_text_mask = draw_masked_text(
                        text_mask, 
                        text_content,
                        block.get("font_name", "arial.ttf"),
                        block.get("font_size", 50),
                        block_letter_spacing,  # 使用Text Block的字间距参数
                        line_spacing,  # 使用Overlay Text节点的参数
                        original_x,  # 使用原始位置
                        original_y,  # 使用原始位置
                        align,  # 使用Overlay Text节点的参数
                        "left",  # 强制使用左对齐，因为我们已经在布局级别处理了对齐
                        block_rotation_angle,  # 使用Text Block的旋转角度
                        block_rotation_options,  # 使用Text Block的旋转选项
                        block_italic_enabled,  # 使用Text Block的倾斜效果
                        block.get("bold", False),  # 使用Text Block的加粗效果
                        block.get("underline", False),  # 使用Text Block的下划线效果
                        block.get("strikethrough", False),  # 使用Text Block的删除线效果
                        block.get("text_case", "normal"),  # 使用Text Block的大小写转换
                        block.get("vertical_align", "normal")  # 使用Text Block的上下标效果
                    )
                    
                    # 应用透明度
                    opacity = block.get("opacity", 1.0)
                    if opacity != 1.0:
                        rotated_text_mask = rotated_text_mask.point(lambda x: int(x * opacity))
                    
                    # 将文本合成到背景图像上
                    back_image = Image.composite(text_image, back_image, rotated_text_mask)
                    
                    # 将当前文本块的遮罩合并到最终遮罩中
                    final_text_mask = Image.composite(Image.new('L', final_text_mask.size, 255), 
                                                     final_text_mask, rotated_text_mask)
            

            
            # 转换回RGB并添加到输出列表
            output_images.append(back_image.convert("RGB"))
            
            # 添加最终文本遮罩到输出列表
            output_masks.append(final_text_mask)

        return (self._pil_to_tensor(output_images), self._masks_to_tensor(output_masks))
