import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly, TypeSlot, TypeSlotEvent } from "../util.js";

const _id = "Text Block";

/**
 * 更新字重选项的方法
 * @param {LGraphNode} node - Text Block节点
 * @param {string} selectedFamily - 选中的字体家族
 */
function updateFontWeights(node, selectedFamily) {
    try {
        const fontWeightWidget = node.widgets?.find(w => w.name === "font_weight");
        if (!fontWeightWidget) {
            return;
        }
        
        // 使用字体字重映射
        const fontWeightMap = node.fontWeightMap || {};
        const weights = fontWeightMap[selectedFamily] || ["Regular"];
        
        // 保存当前选中的字重
        const currentWeight = fontWeightWidget.value;
        
        // 更新字重选项
        fontWeightWidget.options.values = weights;
        
        // 如果当前字重在新的选项中，保持选中；否则选择第一个
        if (weights.includes(currentWeight)) {
            fontWeightWidget.value = currentWeight;
        } else {
            fontWeightWidget.value = weights[0];
        }
        
        // 强制刷新UI
        if (fontWeightWidget.callback) {
            fontWeightWidget.callback(fontWeightWidget.value);
        }
        
    } catch (error) {
        console.error("[WBLESS] Error updating font weights:", error);
        // 回退到默认值
        const fontWeightWidget = node.widgets?.find(w => w.name === "font_weight");
        if (fontWeightWidget) {
            fontWeightWidget.options.values = ["Regular"];
            fontWeightWidget.value = "Regular";
        }
    }
}

/**
 * 处理默认值设置变化
 * @param {LGraphNode} node - Text Block节点
 * @param {boolean} setAsDefault - 是否设置为默认值
 */
function handleDefaultValueChange(node, setAsDefault) {
    try {
        if (setAsDefault) {
            // 当设置为默认值时，确保其他Text Block节点的默认值开关被关闭
            ensureOnlyOneDefaultNode(node);
            // 通知其他Text Block节点应用这个节点的默认值
            broadcastDefaultValues(node);
        } else {
            // 当取消默认值设置时，通知其他节点恢复处理
            broadcastDefaultCancellation(node);
        }
    } catch (error) {
        console.error("[WBLESS] Error handling default value change:", error);
    }
}

/**
 * 确保在连接到同一个Overlay Text节点的范围内只有一个Text Block节点被设置为默认值
 * @param {LGraphNode} currentNode - 当前设置为默认值的节点
 */
function ensureOnlyOneDefaultNode(currentNode) {
    try {
        // 获取当前节点连接的Overlay Text节点
        const currentOverlayNodes = getConnectedOverlayTextNodes(currentNode);
        
        if (currentOverlayNodes.length === 0) {
            return; // 如果没有连接到任何Overlay Text节点，不需要处理
        }
        
        // 对于每个连接的Overlay Text节点，确保其连接的Text Block中只有当前节点被设为默认值
        for (const overlayNode of currentOverlayNodes) {
            const connectedTextBlocks = getTextBlocksConnectedToOverlay(overlayNode);
            
            for (const node of connectedTextBlocks) {
                if (node.id !== currentNode.id) {
                    const setAsDefaultWidget = node.widgets?.find(w => w.name === "set_as_default");
                    if (setAsDefaultWidget && setAsDefaultWidget.value === true) {
                        // 关闭其他节点的默认值开关
                        setAsDefaultWidget.value = false;
                        // 触发回调以确保UI更新
                        if (setAsDefaultWidget.callback) {
                            setAsDefaultWidget.callback(false);
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error ensuring only one default node:", error);
    }
}

/**
 * 广播默认值到连接到同一个Overlay Text节点的其他Text Block节点
 * @param {LGraphNode} defaultNode - 设置为默认值的节点
 */
function broadcastDefaultValues(defaultNode) {
    try {
        // 获取默认节点的所有参数值
        const defaultValues = extractNodeValues(defaultNode);
        
        // 获取默认节点连接的Overlay Text节点
        const defaultOverlayNodes = getConnectedOverlayTextNodes(defaultNode);
        
        if (defaultOverlayNodes.length === 0) {
            return; // 如果没有连接到任何Overlay Text节点，不需要广播
        }
        
        // 对于每个连接的Overlay Text节点，将默认值应用到其连接的其他Text Block节点
        for (const overlayNode of defaultOverlayNodes) {
            const connectedTextBlocks = getTextBlocksConnectedToOverlay(overlayNode);
            
            for (const node of connectedTextBlocks) {
                if (node.id !== defaultNode.id) {
                    const setAsDefaultWidget = node.widgets?.find(w => w.name === "set_as_default");
                    // 只对未设置为默认值的节点应用默认值
                    if (!setAsDefaultWidget || setAsDefaultWidget.value !== true) {
                        applyDefaultValuesToNode(node, defaultValues);
                    }
                }
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error broadcasting default values:", error);
    }
}

/**
 * 广播默认值取消，让其他节点恢复到原始默认值
 * @param {LGraphNode} canceledNode - 取消默认值设置的节点
 */
function broadcastDefaultCancellation(canceledNode) {
    try {
        // 获取取消默认值节点连接的Overlay Text节点
        const canceledOverlayNodes = getConnectedOverlayTextNodes(canceledNode);
        
        if (canceledOverlayNodes.length === 0) {
            return; // 如果没有连接到任何Overlay Text节点，不需要处理
        }
        
        // 对于每个连接的Overlay Text节点，检查是否还有其他默认值节点
        for (const overlayNode of canceledOverlayNodes) {
            const connectedTextBlocks = getTextBlocksConnectedToOverlay(overlayNode);
            
            // 查找是否还有其他默认值节点
            const remainingDefaultNode = connectedTextBlocks.find(n => {
                if (n.id === canceledNode.id) return false; // 排除当前取消的节点
                const setAsDefaultWidget = n.widgets?.find(w => w.name === "set_as_default");
                return setAsDefaultWidget && setAsDefaultWidget.value === true;
            });
            
            for (const node of connectedTextBlocks) {
                if (node.id !== canceledNode.id) {
                    const setAsDefaultWidget = node.widgets?.find(w => w.name === "set_as_default");
                    // 只处理未设置为默认值的节点
                    if (!setAsDefaultWidget || setAsDefaultWidget.value !== true) {
                        if (remainingDefaultNode) {
                            // 如果还有其他默认值节点，应用其默认值
                            const defaultValues = extractNodeValues(remainingDefaultNode);
                            applyDefaultValuesToNode(node, defaultValues);
                        } else {
                            // 如果没有其他默认值节点，恢复到原始默认值
                            restoreToOriginalDefaults(node);
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error broadcasting default cancellation:", error);
    }
}

/**
 * 提取节点的所有参数值
 * @param {LGraphNode} node - Text Block节点
 * @returns {Object} 参数值对象
 */
function extractNodeValues(node) {
    const values = {};
    try {
        // 排除的参数（不作为默认值）
        const excludeParams = ['text', 'set_as_default'];
        
        for (const widget of node.widgets || []) {
            if (!excludeParams.includes(widget.name)) {
                values[widget.name] = widget.value;
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error extracting node values:", error);
    }
    return values;
}

/**
 * 初始化节点的参数跟踪系统
 * @param {LGraphNode} node - Text Block节点
 */
function initializeParameterTracking(node) {
    if (!node._wbless_tracking) {
        node._wbless_tracking = {
            originalDefaults: {},      // 原始默认值
            userModified: new Set(),   // 用户修改过的参数集合
            lastAppliedDefaults: {}    // 上次应用的默认值
        };
        
        // 捕获节点的原始默认值
        captureOriginalDefaults(node);
    }
}

/**
 * 捕获节点的原始默认值
 * @param {LGraphNode} node - Text Block节点
 */
function captureOriginalDefaults(node) {
    try {
        const excludeParams = ['text', 'set_as_default'];
        
        for (const widget of node.widgets || []) {
            if (!excludeParams.includes(widget.name)) {
                node._wbless_tracking.originalDefaults[widget.name] = widget.value;
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error capturing original defaults:", error);
    }
}

/**
 * 标记参数为用户修改
 * @param {LGraphNode} node - Text Block节点
 * @param {string} paramName - 参数名
 */
function markParameterAsUserModified(node, paramName) {
    initializeParameterTracking(node);
    node._wbless_tracking.userModified.add(paramName);
}

/**
 * 检查参数是否被用户修改过
 * @param {LGraphNode} node - Text Block节点
 * @param {string} paramName - 参数名
 * @returns {boolean} 是否被用户修改过
 */
function isParameterUserModified(node, paramName) {
    initializeParameterTracking(node);
    return node._wbless_tracking.userModified.has(paramName);
}

/**
 * 智能应用默认值到指定节点（只覆盖未被用户修改的参数）
 * @param {LGraphNode} node - 目标Text Block节点
 * @param {Object} defaultValues - 默认值对象
 */
function applyDefaultValuesToNode(node, defaultValues) {
    try {
        initializeParameterTracking(node);
        
        for (const [paramName, value] of Object.entries(defaultValues)) {
            const widget = node.widgets?.find(w => w.name === paramName);
            if (widget) {
                // 只有在参数没有被用户修改过的情况下才应用默认值
                if (!isParameterUserModified(node, paramName)) {
                    if (widget.value !== value) {
                        // 临时禁用跟踪，避免将默认值应用标记为用户修改
                        const wasTracking = node._wbless_applying_defaults;
                        node._wbless_applying_defaults = true;
                        
                        widget.value = value;
                        // 触发回调以确保UI更新和相关逻辑执行
                        if (widget.callback) {
                            widget.callback(value);
                        }
                        
                        node._wbless_applying_defaults = wasTracking;
                    }
                    
                    // 记录应用的默认值
                    node._wbless_tracking.lastAppliedDefaults[paramName] = value;
                }
            }
        }
        
        // 强制重新计算节点尺寸
        nodeFitHeightRobustly(node);
        
    } catch (error) {
        console.error("[WBLESS] Error applying default values to node:", error);
    }
}

/**
 * 重置参数的用户修改状态（当用户明确想要使用默认值时）
 * @param {LGraphNode} node - Text Block节点
 * @param {string} paramName - 参数名
 */
function resetParameterModification(node, paramName) {
    initializeParameterTracking(node);
    node._wbless_tracking.userModified.delete(paramName);
}

/**
 * 将节点的未修改参数恢复到原始默认值
 * @param {LGraphNode} node - Text Block节点
 */
function restoreToOriginalDefaults(node) {
    try {
        initializeParameterTracking(node);
        
        for (const [paramName, originalValue] of Object.entries(node._wbless_tracking.originalDefaults)) {
            // 只恢复未被用户修改的参数
            if (!isParameterUserModified(node, paramName)) {
                const widget = node.widgets?.find(w => w.name === paramName);
                if (widget && widget.value !== originalValue) {
                    // 临时禁用跟踪，避免将恢复操作标记为用户修改
                    const wasTracking = node._wbless_applying_defaults;
                    node._wbless_applying_defaults = true;
                    
                    widget.value = originalValue;
                    // 触发回调以确保UI更新和相关逻辑执行
                    if (widget.callback) {
                        widget.callback(originalValue);
                    }
                    
                    node._wbless_applying_defaults = wasTracking;
                }
            }
        }
        
        // 强制重新计算节点尺寸
        nodeFitHeightRobustly(node);
        
    } catch (error) {
        console.error("[WBLESS] Error restoring to original defaults:", error);
    }
}

/**
 * 为单个控件包装跟踪功能
 * @param {LGraphNode} node - Text Block节点
 * @param {Object} widget - 控件对象
 */
function wrapWidgetWithTracking(node, widget) {
    if (widget._wbless_tracking_wrapped) {
        return; // 已经包装过了，避免重复
    }
    
    const originalCallback = widget.callback;
    
    widget.callback = function(value) {
        // 如果不是在应用默认值期间，标记为用户修改
        if (!node._wbless_applying_defaults) {
            markParameterAsUserModified(node, widget.name);
        }
        
        // 调用原始回调
        let result;
        if (originalCallback) {
            result = originalCallback.call(this, value);
        }
        
        // 通知连接的Overlay Text节点更新预览 - 立即更新，无延迟
        notifyOverlayNodesForPreviewUpdate(node);
        
        return result;
    };
    
    widget._wbless_tracking_wrapped = true;
}

/**
 * 强制重新包装所有控件的跟踪功能（用于处理已经设置了回调的控件）
 * @param {LGraphNode} node - Text Block节点
 */
function forceRewrapAllWidgets(node) {
    try {
        const excludeParams = ['text', 'set_as_default'];
        
        for (const widget of node.widgets || []) {
            if (!excludeParams.includes(widget.name)) {
                // 重置包装状态，强制重新包装
                widget._wbless_tracking_wrapped = false;
                wrapWidgetWithTracking(node, widget);
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error force rewrapping widgets:", error);
    }
}

/**
 * 为节点的所有控件添加修改监听器
 * @param {LGraphNode} node - Text Block节点
 */
function setupParameterChangeTracking(node) {
    try {
        initializeParameterTracking(node);
        
        // 排除的参数（不需要跟踪的参数）
        const excludeParams = ['text', 'set_as_default'];
        
        for (const widget of node.widgets || []) {
            if (!excludeParams.includes(widget.name)) {
                wrapWidgetWithTracking(node, widget);
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error setting up parameter change tracking:", error);
    }
}

/**
 * 管理高级选项的显示隐藏
 * @param {LGraphNode} node - Text Block节点
 * @param {boolean} showAdvanced - 是否显示高级选项
 */
function manageAdvancedOptions(node, showAdvanced) {
    // 需要隐藏的高级选项（从horizontal_spacing开始，不包括newline、auto_newline、auto_newline_width和expand_advanced）
    const advancedOptionNames = [
        "horizontal_spacing",
        "vertical_spacing", 
        "rotation_angle",
        "rotation_options",
        "italic",
        "bold", 
        "underline",
        "strikethrough",
        "text_case",
        "vertical_align",
        "opacity"
    ];
    
    try {
        if (showAdvanced) {
            // 展开：恢复所有隐藏的控件
            if (node._hiddenWidgets) {
                node._hiddenWidgets.forEach(widget => {
                    // 恢复控件到widgets数组
                    if (!node.widgets.includes(widget)) {
                        // 找到正确的插入位置（按原始顺序）
                        const insertIndex = node._originalWidgetOrder?.indexOf(widget.name) || node.widgets.length;
                        let actualIndex = 0;
                        for (let i = 0; i < insertIndex && actualIndex < node.widgets.length; i++) {
                            const originalName = node._originalWidgetOrder?.[i];
                            if (originalName && node.widgets.find(w => w.name === originalName)) {
                                actualIndex++;
                            }
                        }
                        node.widgets.splice(actualIndex, 0, widget);
                        
                        // 重新为恢复的widget绑定预览更新回调
                        wrapWidgetWithTracking(node, widget);
                    }
                });
                node._hiddenWidgets = [];
            }
        } else {
            // 收缩：隐藏高级选项控件
            if (!node._hiddenWidgets) {
                node._hiddenWidgets = [];
                // 保存原始控件顺序
                node._originalWidgetOrder = node.widgets.map(w => w.name);
            }
            
            // 移除高级选项控件
            advancedOptionNames.forEach(optionName => {
                const widgetIndex = node.widgets.findIndex(w => w.name === optionName);
                if (widgetIndex >= 0) {
                    const widget = node.widgets[widgetIndex];
                    // 从widgets数组中移除
                    node.widgets.splice(widgetIndex, 1);
                    // 添加到隐藏列表
                    if (!node._hiddenWidgets.includes(widget)) {
                        node._hiddenWidgets.push(widget);
                    }
                }
            });
        }
        
        // 立即重新计算节点尺寸
        nodeFitHeightRobustly(node);
        
    } catch (error) {
        console.error("[WBLESS] Error managing advanced options:", error);
    }
}

/**
 * 获取Text Block节点连接的所有Overlay Text节点
 * @param {LGraphNode} textBlockNode - Text Block节点
 * @returns {Array} 连接的Overlay Text节点数组
 */
function getConnectedOverlayTextNodes(textBlockNode) {
    const connectedOverlayNodes = [];
    try {
        if (!textBlockNode.outputs) return connectedOverlayNodes;
        
        // 遍历Text Block节点的所有输出
        for (const output of textBlockNode.outputs) {
            if (output.links) {
                for (const linkId of output.links) {
                    const link = app.graph.links[linkId];
                    if (link) {
                        const targetNode = app.graph.getNodeById(link.target_id);
                        if (targetNode && targetNode.type === "Overlay Text") {
                            connectedOverlayNodes.push(targetNode);
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error getting connected Overlay Text nodes:", error);
    }
    return connectedOverlayNodes;
}

/**
 * 获取连接到指定Overlay Text节点的所有Text Block节点
 * @param {LGraphNode} overlayTextNode - Overlay Text节点
 * @returns {Array} 连接的Text Block节点数组
 */
function getTextBlocksConnectedToOverlay(overlayTextNode) {
    const connectedTextBlocks = [];
    try {
        if (!overlayTextNode.inputs) return connectedTextBlocks;
        
        // 遍历Overlay Text节点的所有输入
        for (const input of overlayTextNode.inputs) {
            if (input.link !== null) {
                const link = app.graph.links[input.link];
                if (link) {
                    const sourceNode = app.graph.getNodeById(link.origin_id);
                    if (sourceNode && sourceNode.type === "Text Block") {
                        connectedTextBlocks.push(sourceNode);
                    }
                }
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error getting Text Blocks connected to Overlay:", error);
    }
    return connectedTextBlocks;
}

/**
 * 检查两个Text Block节点是否连接到同一个Overlay Text节点
 * @param {LGraphNode} node1 - 第一个Text Block节点
 * @param {LGraphNode} node2 - 第二个Text Block节点
 * @returns {boolean} 是否连接到同一个Overlay Text节点
 */
function areConnectedToSameOverlay(node1, node2) {
    try {
        const overlayNodes1 = getConnectedOverlayTextNodes(node1);
        const overlayNodes2 = getConnectedOverlayTextNodes(node2);
        
        // 检查是否有共同的Overlay Text节点
        for (const overlay1 of overlayNodes1) {
            for (const overlay2 of overlayNodes2) {
                if (overlay1.id === overlay2.id) {
                    return true;
                }
            }
        }
        return false;
    } catch (error) {
        console.error("[WBLESS] Error checking if nodes are connected to same overlay:", error);
        return false;
    }
}

/**
 * 检查是否存在默认值节点，如果存在则应用其默认值到当前节点
 * @param {LGraphNode} node - 当前Text Block节点
 */
function checkAndApplyExistingDefaults(node) {
    try {
        // 获取当前节点连接的Overlay Text节点
        const currentOverlayNodes = getConnectedOverlayTextNodes(node);
        
        if (currentOverlayNodes.length === 0) {
            return; // 如果没有连接到任何Overlay Text节点，不应用默认值
        }
        
        // 对于每个连接的Overlay Text节点，检查是否有默认值节点
        for (const overlayNode of currentOverlayNodes) {
            const connectedTextBlocks = getTextBlocksConnectedToOverlay(overlayNode);
            
            // 查找设置为默认值的节点
            const defaultNode = connectedTextBlocks.find(n => {
                const setAsDefaultWidget = n.widgets?.find(w => w.name === "set_as_default");
                return setAsDefaultWidget && setAsDefaultWidget.value === true && n.id !== node.id;
            });
            
            if (defaultNode) {
                // 获取默认节点的值并应用到当前节点
                const defaultValues = extractNodeValues(defaultNode);
                applyDefaultValuesToNode(node, defaultValues);
                break; // 只需要应用一次默认值
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error checking and applying existing defaults:", error);
    }
}

/**
 * 通知连接的Overlay Text节点更新预览
 * @param {LGraphNode} textBlockNode - Text Block节点
 * @param {boolean} immediate - 是否立即更新（不使用防抖）
 */
function notifyOverlayNodesForPreviewUpdate(textBlockNode, immediate = true) {
    try {
        const connectedOverlayNodes = getConnectedOverlayTextNodes(textBlockNode);
        
        for (const overlayNode of connectedOverlayNodes) {
            if (immediate && overlayNode.updatePreviewImmediate) {
                // 立即更新，用于用户交互参数
                overlayNode.updatePreviewImmediate();
                
                // 调试信息
                if (window.WBLESS_DEBUG) {
                    console.log('[WBLESS] Text Block parameter changed, triggering immediate preview update');
                }
            } else if (overlayNode.updatePreview) {
                // 防抖更新，用于复杂参数
                overlayNode.updatePreview();
                
                // 调试信息
                if (window.WBLESS_DEBUG) {
                    console.log('[WBLESS] Text Block parameter changed, triggering debounced preview update');
                }
            }
        }
    } catch (error) {
        console.error("[WBLESS] Error notifying overlay nodes for preview update:", error);
    }
}

/**
 * 包装widget回调以支持预览更新通知
 * @param {LGraphNode} node - Text Block节点
 * @param {Object} widget - widget对象
 * @param {Function} originalCallback - 原始回调函数
 * @returns {Function} 包装后的回调函数
 */
function wrapWidgetCallbackForPreview(node, widget, originalCallback) {
    return function(value) {
        // 先调用原始回调
        if (originalCallback) {
            const result = originalCallback.call(this, value);
            
            // 然后通知连接的Overlay Text节点更新预览 - 立即更新，无延迟
            notifyOverlayNodesForPreviewUpdate(node);
            
            return result;
        } else {
            // 如果没有原始回调，直接通知预览更新 - 立即更新，无延迟
            notifyOverlayNodesForPreviewUpdate(node);
        }
    };
}

/**
 * 获取标题后的下一个有效字体
 * @param {Array} values - 所有选项值
 * @param {string} titleValue - 标题值
 * @returns {string|null} 下一个有效的字体名称
 */
function getNextValidFontAfterTitle(values, titleValue) {
    try {
        const titleIndex = values.indexOf(titleValue);
        if (titleIndex >= 0) {
            // 查找标题后的第一个有效字体
            for (let i = titleIndex + 1; i < values.length; i++) {
                const value = values[i];
                // 跳过标题
                if (!value.startsWith("📁 ") && !value.startsWith("🖥️ ")) {
                    return value;
                }
            }
        }
        return null;
    } catch (error) {
        console.error("[WBLESS] Error getting next valid font after title:", error);
        return null;
    }
}

/**
 * 设置字体家族下拉框，为标题添加样式
 * @param {Object} widget - 字体家族widget
 */
function setupFontFamilyDropdown(widget) {
    try {
        // 保存原始的选项值
        const originalValues = widget.options.values;
        
        // 检查是否有标题
        const hasTitle = originalValues.some(value => value && (value.startsWith("📁 ") || value.startsWith("🖥️ ")));
        
        if (hasTitle) {
            // 为widget添加自定义样式标识
            widget._wbless_has_title = true;
            
            // 如果widget有DOM元素，添加CSS样式
            if (widget.element) {
                addTitleStyles(widget.element, originalValues);
            }
            
            // 监听widget的DOM创建事件（如果还没有DOM元素）
            const originalOnDOMCreated = widget.onDOMCreated;
            widget.onDOMCreated = function(element) {
                if (originalOnDOMCreated) {
                    originalOnDOMCreated.call(this, element);
                }
                addTitleStyles(element, originalValues);
            };
        }
    } catch (error) {
        console.error("[WBLESS] Error setting up font family dropdown:", error);
    }
}

/**
 * 为下拉框选项添加标题样式
 * @param {HTMLElement} element - 下拉框DOM元素
 * @param {Array} values - 选项值数组
 */
function addTitleStyles(element, values) {
    try {
        // 查找select元素
        const selectElement = element.tagName === 'SELECT' ? element : element.querySelector('select');
        if (!selectElement) return;
        
        // 为每个option添加样式
        const options = selectElement.querySelectorAll('option');
        values.forEach((value, index) => {
            if (value && (value.startsWith("📁 ") || value.startsWith("🖥️ "))) {
                const option = options[index];
                if (option) {
                    // 添加标题样式 - 可点击但样式特殊
                    option.style.cssText = `
                        background-color: #e8f4f8 !important;
                        color: #2c5aa0 !important;
                        font-weight: bold !important;
                        text-align: left !important;
                        border-top: 2px solid #4a90e2 !important;
                        border-bottom: 1px solid #4a90e2 !important;
                        cursor: pointer !important;
                        padding-left: 8px !important;
                    `;
                    // 标题是可选择的，不设置disabled
                }
            } else if (index > 0 && values[index - 1] && (values[index - 1].startsWith("📁 ") || values[index - 1].startsWith("🖥️ "))) {
                // 为标题后的第一个选项添加缩进
                const option = options[index];
                if (option) {
                    option.style.paddingLeft = '20px';
                    option.style.borderTop = '1px solid #ddd';
                }
            } else if (index > 0) {
                // 为标题分类下的其他字体添加缩进
                let isUnderTitle = false;
                for (let j = index - 1; j >= 0; j--) {
                    if (values[j].startsWith("📁 ") || values[j].startsWith("🖥️ ")) {
                        isUnderTitle = true;
                        break;
                    }
                }
                if (isUnderTitle) {
                    const option = options[index];
                    if (option) {
                        option.style.paddingLeft = '20px';
                    }
                }
            }
        });
        
        // 添加整体样式
        if (!document.getElementById('wbless-font-title-styles')) {
            const style = document.createElement('style');
            style.id = 'wbless-font-title-styles';
            style.textContent = `
                select option {
                    padding: 4px 8px !important;
                }
                select option:hover {
                    background-color: #f0f8ff !important;
                }
            `;
            document.head.appendChild(style);
        }
    } catch (error) {
        console.error("[WBLESS] Error adding title styles:", error);
    }
}

// 为WBLESS插件注册一个新的节点扩展
app.registerExtension({
    name: "wbless.node." + _id,
    
    // 在ComfyUI注册此节点类型之前，执行以下逻辑
    async beforeRegisterNodeDef(nodeType, nodeData) {
        // 确保我们只修改目标节点
        if (nodeData.name !== _id) return;
        
        // 从隐藏参数获取字重映射
        let fontWeightMap = {};
        if (nodeData.input?.hidden?.font_weight_map?.[1]?.default) {
            try {
                const mapStr = nodeData.input.hidden.font_weight_map[1].default;
                fontWeightMap = JSON.parse(mapStr);
            } catch (error) {
                console.error("[WBLESS] Failed to parse font weight map JSON:", error);
            }
        }
        
        // 如果没有获取到映射，使用默认的常见字体映射
        if (Object.keys(fontWeightMap).length === 0) {
            fontWeightMap = {
                "Arial": ["Regular", "Bold", "Black", "Bold Italic", "Italic"],
                "Times New Roman": ["Regular", "Bold", "Bold Italic", "Italic"],
                "Calibri": ["Light", "Regular", "Bold", "Bold Italic", "Italic", "Light Italic"],
                "Segoe UI": ["Light", "Regular", "Bold", "Italic", "Black", "Semibold", "Light Italic", "Bold Italic", "Black Italic", "Semibold Italic", "Semilight", "Semilight Italic"],
                "Trebuchet MS": ["Regular", "Bold", "Bold Italic", "Italic"],
                "Verdana": ["Regular", "Bold", "Italic", "Bold Italic"],
                "Georgia": ["Regular", "Bold", "Italic", "Bold Italic"],
                "阿里巴巴普惠体 3.0": ["35 Thin", "45 Light", "55 Regular", "55 Regular L3", "65 Medium", "75 SemiBold", "85 Bold", "95 ExtraBold", "105 Heavy", "115 Black"],
            };
        }
        
        // --- 劫持生命周期函数 ---
        
        // 1. onNodeCreated: 当节点第一次被创建时调用
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            
            // 将字体字重映射附加到节点实例
            this.fontWeightMap = fontWeightMap;
            
            // 立即处理高级选项的初始状态，避免闪烁
            const expandWidget = this.widgets?.find(w => w.name === "expand_advanced");
            const shouldExpand = expandWidget ? (expandWidget.value || false) : false;
            
            // 如果默认是收缩状态，立即隐藏高级选项
            if (!shouldExpand) {
                manageAdvancedOptions(this, false);
            }
            
            // 设置字体家族变化监听器和高级选项展开监听器
            setTimeout(() => {
                const fontFamilyWidget = this.widgets?.find(w => w.name === "font_family");
                if (fontFamilyWidget) {
                    // 保存原始回调
                    const originalCallback = fontFamilyWidget.callback;
                    
                    // 重写回调来监听字体家族变化
                    fontFamilyWidget.callback = (value) => {
                        // 如果选中的是标题，选择该分类的第一个字体
                        if (value && (value.startsWith("📁 ") || value.startsWith("🖥️ "))) {
                            const nextValidFont = getNextValidFontAfterTitle(fontFamilyWidget.options.values, value);
                            if (nextValidFont) {
                                fontFamilyWidget.value = nextValidFont;
                                value = nextValidFont;
                            }
                        }
                        
                        // 先调用原始回调
                        if (originalCallback) {
                            originalCallback.call(fontFamilyWidget, value);
                        }
                        
                        // 然后更新字重
                        updateFontWeights(this, value);
                    };
                    
                    // 自定义下拉框显示，为分隔符添加样式
                    if (fontFamilyWidget.options && fontFamilyWidget.options.values) {
                        setupFontFamilyDropdown(fontFamilyWidget);
                    }
                    
                    // 初始化字重选项
                    updateFontWeights(this, fontFamilyWidget.value);
                    
                    // 重新包装跟踪功能
                    wrapWidgetWithTracking(this, fontFamilyWidget);
                }
                
                // 设置高级选项展开开关监听器
                if (expandWidget) {
                    // 保存原始回调
                    const originalExpandCallback = expandWidget.callback;
                    
                    // 重写回调来监听展开状态变化
                    expandWidget.callback = (value) => {
                        // 先调用原始回调
                        if (originalExpandCallback) {
                            originalExpandCallback.call(expandWidget, value);
                        }
                        
                        // 然后管理高级选项显示
                        manageAdvancedOptions(this, value);
                    };
                }
                
                // 设置默认值开关监听器
                const setAsDefaultWidget = this.widgets?.find(w => w.name === "set_as_default");
                if (setAsDefaultWidget) {
                    // 保存原始回调
                    const originalDefaultCallback = setAsDefaultWidget.callback;
                    
                    // 重写回调来监听默认值设置变化
                    setAsDefaultWidget.callback = (value) => {
                        // 先调用原始回调
                        if (originalDefaultCallback) {
                            originalDefaultCallback.call(setAsDefaultWidget, value);
                        }
                        
                        // 处理默认值设置逻辑
                        handleDefaultValueChange(this, value);
                    };
                }
                
                nodeFitHeightRobustly(this);
                
                // 设置参数修改跟踪（先初始设置）
                setupParameterChangeTracking(this);
                
                // 强制重新包装所有控件（确保特殊回调也被跟踪）
                forceRewrapAllWidgets(this);
                
                // 检查并应用现有的默认值（仅在节点创建时）
                checkAndApplyExistingDefaults(this);
            }, 100);
        };
        
        // 添加连接变化监听器
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function(slotType, slot_idx, event, link_info, node_slot) {
            const result = onConnectionsChange?.apply(this, arguments);
            
            // 当连接变化时，检查是否需要应用默认值和更新预览
            setTimeout(() => {
                try {
                    // 如果这是一个输出连接变化（Text Block连接到Overlay Text）
                    if (slotType === TypeSlot.Output && event === TypeSlotEvent.Connect) {
                        // 检查并应用现有的默认值
                        checkAndApplyExistingDefaults(this);
                    }
                    
                    // 无论连接还是断开，都通知相关的Overlay Text节点更新预览
                    notifyOverlayNodesForPreviewUpdate(this);
                } catch (error) {
                    console.error("[WBLESS] Error handling connection change:", error);
                }
            }, 100);
            
            return result;
        };

        // 添加右键菜单选项
        const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function(_, options) {
            getExtraMenuOptions?.apply(this, arguments);
            
            // 添加重置参数修改状态的选项
            options.push({
                content: "Reset Parameter Modifications",
                callback: () => {
                    try {
                        initializeParameterTracking(this);
                        this._wbless_tracking.userModified.clear();
                        console.log("[WBLESS] All parameter modifications reset");
                        
                        // 重新应用默认值
                        checkAndApplyExistingDefaults(this);
                    } catch (error) {
                        console.error("[WBLESS] Error resetting parameter modifications:", error);
                    }
                }
            });
            
            // 添加恢复到原始默认值的选项
            options.push({
                content: "Restore to Original Defaults",
                callback: () => {
                    try {
                        restoreToOriginalDefaults(this);
                        console.log("[WBLESS] Restored to original defaults");
                    } catch (error) {
                        console.error("[WBLESS] Error restoring to original defaults:", error);
                    }
                }
            });
        };

        // 2. onConfigure: 当节点从工作流（JSON）加载时调用
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            onConfigure?.apply(this, arguments);
            
            // 将字体字重映射附加到节点实例
            this.fontWeightMap = fontWeightMap;
            
            // 立即处理高级选项的加载状态，避免闪烁
            const expandWidget = this.widgets?.find(w => w.name === "expand_advanced");
            const shouldExpand = expandWidget ? (expandWidget.value || false) : false;
            
            // 根据保存的状态立即设置显示状态
            manageAdvancedOptions(this, shouldExpand);
            
            // 使用setTimeout确保在所有连接信息都完全加载后，再执行我们的逻辑
            setTimeout(() => {
                const fontFamilyWidget = this.widgets?.find(w => w.name === "font_family");
                if (fontFamilyWidget) {
                    // 保存原始回调
                    const originalCallback = fontFamilyWidget.callback;
                    
                    // 重写回调来监听字体家族变化
                    fontFamilyWidget.callback = (value) => {
                        // 如果选中的是标题，选择该分类的第一个字体
                        if (value && (value.startsWith("📁 ") || value.startsWith("🖥️ "))) {
                            const nextValidFont = getNextValidFontAfterTitle(fontFamilyWidget.options.values, value);
                            if (nextValidFont) {
                                fontFamilyWidget.value = nextValidFont;
                                value = nextValidFont;
                            }
                        }
                        
                        // 先调用原始回调
                        if (originalCallback) {
                            originalCallback.call(fontFamilyWidget, value);
                        }
                        
                        // 然后更新字重
                        updateFontWeights(this, value);
                    };
                    
                    // 自定义下拉框显示，为分隔符添加样式
                    if (fontFamilyWidget.options && fontFamilyWidget.options.values) {
                        setupFontFamilyDropdown(fontFamilyWidget);
                    }
                    
                    // 加载时更新字重选项
                    updateFontWeights(this, fontFamilyWidget.value);
                }
                
                // 设置高级选项展开开关监听器（加载时）
                if (expandWidget) {
                    // 保存原始回调
                    const originalExpandCallback = expandWidget.callback;
                    
                    // 重写回调来监听展开状态变化
                    expandWidget.callback = (value) => {
                        // 先调用原始回调
                        if (originalExpandCallback) {
                            originalExpandCallback.call(expandWidget, value);
                        }
                        
                        // 然后管理高级选项显示
                        manageAdvancedOptions(this, value);
                    };
                }
                
                // 设置默认值开关监听器（加载时）
                const setAsDefaultWidget = this.widgets?.find(w => w.name === "set_as_default");
                if (setAsDefaultWidget) {
                    // 保存原始回调
                    const originalDefaultCallback = setAsDefaultWidget.callback;
                    
                    // 重写回调来监听默认值设置变化
                    setAsDefaultWidget.callback = (value) => {
                        // 先调用原始回调
                        if (originalDefaultCallback) {
                            originalDefaultCallback.call(setAsDefaultWidget, value);
                        }
                        
                        // 处理默认值设置逻辑
                        handleDefaultValueChange(this, value);
                    };
                }
                
                nodeFitHeightRobustly(this);
                
                // 设置参数修改跟踪（加载时）
                setupParameterChangeTracking(this);
                
                // 强制重新包装所有控件（确保特殊回调也被跟踪）
                forceRewrapAllWidgets(this);
            }, 100);
        };
    }
});