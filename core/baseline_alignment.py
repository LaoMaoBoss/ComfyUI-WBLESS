from cozy_comfyui.node import CozyBaseNode, COZY_TYPE_ANY

class BaselineAlignmentOffset(CozyBaseNode):
    """
    基线对齐位置计算节点
    
    功能：计算高度A的中心点应该位于高度B的哪个百分比位置，
    才能使高度A的底部对齐到高度B的指定基线位置。
    
    计算逻辑：
    1. 目标：高度A的底部要对齐到高度B的基线百分比位置
    2. 高度A的中心到底部的距离 = height_a / 2
    3. 这个距离在高度B中的百分比 = (height_a / 2) / height_b * 100
    4. 高度A中心的目标位置百分比 = 基线百分比 - 中心到底部的百分比
    5. 输出：高度A中心在高度B上的目标百分比位置
    """
    NAME = "Baseline Alignment (Y)"
    
    @classmethod
    def INPUT_TYPES(s):
        """
        定义节点的输入类型
        - height_a: 高度A（需要对齐的对象的高度）
        - height_b: 高度B（参考高度，基线百分比基于此高度计算）
        - baseline_percent: 基线百分比（0-100），表示基线在高度B中的位置
        """
        return {
            "required": {
                "height_a": (COZY_TYPE_ANY,),
                "height_b": (COZY_TYPE_ANY,),
                "baseline_percent": ("FLOAT", {"default": 80.0}),
            },
        }

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("y_percent",)
    FUNCTION = "calculate_position"
    
    def calculate_position(self, height_a, height_b, baseline_percent: float):
        """
        计算高度A中心点在高度B上的目标百分比位置
        
        参数:
        - height_a: 需要对齐的对象的高度
        - height_b: 参考高度（基线百分比基于此高度）
        - baseline_percent: 基线在高度B中的位置百分比（0-100）
        
        返回:
        - y_percent: 高度A的中心点在高度B上的目标Y轴百分比位置
        """
        
        # 处理可能的列表类型输入
        if isinstance(height_a, list) and height_a:
            height_a = height_a[0]
        if isinstance(height_b, list) and height_b:
            height_b = height_b[0]
        if isinstance(baseline_percent, list) and baseline_percent:
            baseline_percent = baseline_percent[0]
        
        # 转换为浮点数以确保精确计算
        height_a_float = float(height_a)
        height_b_float = float(height_b)
        baseline_percent_float = float(baseline_percent)
        
        # 边界条件检查
        if height_b_float <= 0:
            # 如果参考高度无效，返回50%（中心位置）
            return (50.0,)
        
        if height_a_float <= 0:
            # 如果对象高度无效，返回基线位置（因为没有高度就直接在基线上）
            return (baseline_percent_float,)
        
        # 不限制基线百分比范围，允许任意数值
        
        # --- 核心计算逻辑 ---
        
        # 1. 计算高度A的中心到底部的距离在高度B中的百分比
        #    高度A的一半 / 高度B * 100 = 中心到底部的百分比距离
        center_to_bottom_percent = (height_a_float / 2.0) / height_b_float * 100.0
        
        # 2. 要让高度A的底部对齐到基线位置，
        #    高度A的中心应该位于：基线位置 - 中心到底部的距离
        center_position_percent = baseline_percent_float - center_to_bottom_percent
        
        # 3. 结果可能超出0-100范围，这是正常的
        #    比如如果高度A很大，中心可能需要在负位置才能让底部对齐基线
        #    或者如果基线位置很高，中心位置也可能超过100%
        
        return (center_position_percent,)


class BaselineAlignmentX(CozyBaseNode):
    """
    基线对齐位置计算节点（X轴版本）
    
    功能：计算宽度A的中心点应该位于宽度B的哪个百分比位置，
    才能使宽度A的右边缘对齐到宽度B的指定基线位置。
    
    计算逻辑：
    1. 目标：宽度A的右边缘要对齐到宽度B的基线百分比位置
    2. 宽度A的中心到右边缘的距离 = width_a / 2
    3. 这个距离在宽度B中的百分比 = (width_a / 2) / width_b * 100
    4. 宽度A中心的目标位置百分比 = 基线百分比 - 中心到右边缘的百分比
    5. 输出：宽度A中心在宽度B上的目标百分比位置
    """
    NAME = "Baseline Alignment (X)"
    
    @classmethod
    def INPUT_TYPES(s):
        """
        定义节点的输入类型
        - width_a: 宽度A（需要对齐的对象的宽度）
        - width_b: 宽度B（参考宽度，基线百分比基于此宽度计算）
        - baseline_percent: 基线百分比，表示基线在宽度B中的位置
        """
        return {
            "required": {
                "width_a": (COZY_TYPE_ANY,),
                "width_b": (COZY_TYPE_ANY,),
                "baseline_percent": ("FLOAT", {"default": 80.0}),
            },
        }

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("x_percent",)
    FUNCTION = "calculate_position"
    
    def calculate_position(self, width_a, width_b, baseline_percent: float):
        """
        计算宽度A中心点在宽度B上的目标百分比位置
        
        参数:
        - width_a: 需要对齐的对象的宽度
        - width_b: 参考宽度（基线百分比基于此宽度）
        - baseline_percent: 基线在宽度B中的位置百分比
        
        返回:
        - x_percent: 宽度A的中心点在宽度B上的目标X轴百分比位置
        """
        
        # 处理可能的列表类型输入
        if isinstance(width_a, list) and width_a:
            width_a = width_a[0]
        if isinstance(width_b, list) and width_b:
            width_b = width_b[0]
        if isinstance(baseline_percent, list) and baseline_percent:
            baseline_percent = baseline_percent[0]
        
        # 转换为浮点数以确保精确计算
        width_a_float = float(width_a)
        width_b_float = float(width_b)
        baseline_percent_float = float(baseline_percent)
        
        # 边界条件检查
        if width_b_float <= 0:
            # 如果参考宽度无效，返回50%（中心位置）
            return (50.0,)
        
        if width_a_float <= 0:
            # 如果对象宽度无效，返回基线位置（因为没有宽度就直接在基线上）
            return (baseline_percent_float,)
        
        # 不限制基线百分比范围，允许任意数值
        
        # --- 核心计算逻辑 ---
        
        # 1. 计算宽度A的中心到右边缘的距离在宽度B中的百分比
        #    宽度A的一半 / 宽度B * 100 = 中心到右边缘的百分比距离
        center_to_right_percent = (width_a_float / 2.0) / width_b_float * 100.0
        
        # 2. 要让宽度A的右边缘对齐到基线位置，
        #    宽度A的中心应该位于：基线位置 - 中心到右边缘的距离
        center_position_percent = baseline_percent_float - center_to_right_percent
        
        # 3. 结果可能超出0-100范围，这是正常的
        #    比如如果宽度A很大，中心可能需要在负位置才能让右边缘对齐基线
        #    或者如果基线位置很高，中心位置也可能超过100%
        
        return (center_position_percent,)
