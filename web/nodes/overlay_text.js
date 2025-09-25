// WBLESS Overlay Text Node
// Author: WBLESS
// This script implements dynamic input management for the Overlay Text node,
// strictly following the robust add/remove pattern from the Switch node.

import { app } from "/scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";
import { createPreviewCanvas, drawTextPreview, debounceRAF } from "../preview.js";

const NODE_NAME = "Overlay Text";
const DYNAMIC_INPUT_TYPE = "TEXT_BLOCK";
const DYNAMIC_INPUT_PREFIX = "text_block_";

/**
 * A helper function to get all dynamically generated input ports.
 * @param {LGraphNode} node - The current OverlayText node.
 * @returns {Array} - An array containing all dynamic input port objects.
 */
function getDynamicInputs(node) {
    return node.inputs?.filter(i => i.name.startsWith(DYNAMIC_INPUT_PREFIX)) || [];
}

/**
 * Manages the dynamic input ports for the OverlayText node.
 * It ensures there is always one empty, unconnected input slot available.
 * @param {LGraphNode} node The instance of the OverlayText node.
 */
function manageInputs(node) {
    const dynamicInputs = getDynamicInputs(node);
    const connectedCount = dynamicInputs.reduce((acc, input) => acc + (input.link !== null ? 1 : 0), 0);
    const desiredCount = connectedCount + 1;
    let currentCount = dynamicInputs.length;

    // Add inputs if the current count is less than desired.
    while (currentCount < desiredCount) {
        node.addInput(`${DYNAMIC_INPUT_PREFIX}${currentCount + 1}`, DYNAMIC_INPUT_TYPE);
        currentCount++;
    }

    // Remove surplus, unconnected inputs from the end.
    while (currentCount > desiredCount) {
        const lastInput = node.inputs[node.inputs.length - 1];
        if (lastInput && lastInput.name.startsWith(DYNAMIC_INPUT_PREFIX) && lastInput.link === null) {
            node.removeInput(node.inputs.length - 1);
            currentCount--;
        } else {
            break; // Stop if the last port is connected or not a dynamic one.
        }
    }

    // Safeguard: Ensure at least one dynamic input always exists.
    if (getDynamicInputs(node).length === 0) {
        node.addInput(`${DYNAMIC_INPUT_PREFIX}1`, DYNAMIC_INPUT_TYPE);
    }
    
    // Force a sequential rename of all dynamic inputs to maintain order.
    let dynamicInputIndex = 1;
    node.inputs.forEach(input => {
        if (input.name.startsWith(DYNAMIC_INPUT_PREFIX)) {
            const newName = `${DYNAMIC_INPUT_PREFIX}${dynamicInputIndex}`;
            input.name = newName;
            input.label = newName;
            dynamicInputIndex++;
        }
    });

    // Adjust the node's height to fit the new number of inputs.
    nodeFitHeightRobustly(node);
    
    // 更新预览（如果存在）
    if (node.updatePreview) {
        node.updatePreview();
    }
}



/**
 * 显示嵌入式预览
 * @param {LGraphNode} node - Overlay Text节点实例
 */
function showEmbeddedPreview(node) {
    if (!node._previewWidget) {
        
        // 创建自定义widget
        const previewWidget = {
            name: "text_preview",
            type: "custom",
            value: "",
            options: {},
            y: 0,
            
            draw: function(ctx, node, widget_width, y, H) {
                // 计算预览画布尺寸 - 根据节点实际宽度，1:1比例
                const nodeWidth = node.size[0];
                const previewMargin = 20; // 左右各10px边距
                const previewWidth = Math.max(260, nodeWidth - previewMargin); // 最小260px宽度（与最小节点宽度280px对应）
                const previewHeight = previewWidth; // 1:1比例（正方形）
                
                // 优化：如果画布尺寸变化，重新创建画布
                if (!node._previewCanvas || 
                    node._previewCanvas.width !== previewWidth || 
                    node._previewCanvas.height !== previewHeight) {
                    node._previewCanvas = createPreviewCanvas(previewWidth, previewHeight);
                    
                    // 标记需要重绘，但不立即绘制，避免在draw过程中频繁操作
                    node._previewNeedsRedraw = true;
                    
                    // 立即更新预览，避免出现框框
                    if (node.updatePreviewImmediate) {
                        try {
                            node.updatePreviewImmediate();
                            
                            // 调试信息
                            if (window.WBLESS_DEBUG) {
                                console.log(`[WBLESS] Preview canvas resized to ${previewWidth}x${previewHeight}, immediately updated`);
                            }
                        } catch (error) {
                            console.error('[WBLESS] Error updating preview during resize:', error);
                        }
                    }
                }
                
                const canvas = node._previewCanvas;
                let currentY = y + 10;
                
                // 绘制画布边框
                ctx.strokeStyle = "#555";
                ctx.lineWidth = 1;
                ctx.strokeRect(10, currentY, canvas.width, canvas.height);
                
                // 将画布内容绘制到节点上
                if (canvas) {
                    try {
                        // 优化：只在调试模式下才检查画布内容，减少getImageData调用
                        if (window.WBLESS_DEBUG) {
                            const canvasContext = canvas.getContext('2d');
                            const imageData = canvasContext.getImageData(0, 0, 1, 1);
                            const isEmpty = imageData.data.every(channel => channel === 0);
                            
                            if (isEmpty) {
                                console.warn('[WBLESS] Canvas appears to be empty, forcing preview update');
                                // 如果画布为空，尝试重新绘制
                                const textBlocks = collectTextBlocks(node);
                                const overlaySettings = collectOverlaySettings(node);
                                drawTextPreview(canvas, textBlocks, overlaySettings);
                            }
                        }
                        
                        ctx.drawImage(canvas, 10, currentY);
                    } catch (e) {
                        // 如果绘制失败，显示错误信息
                        console.error('[WBLESS] Canvas draw error:', e);
                        ctx.fillStyle = "#ff6666";
                        ctx.font = "12px Arial";
                        ctx.textAlign = "center";
                        ctx.fillText("Preview Error", widget_width / 2, currentY + canvas.height / 2);
                        ctx.fillStyle = "#999";
                        ctx.font = "10px Arial";
                        ctx.fillText("Check console for details", widget_width / 2, currentY + canvas.height / 2 + 20);
                        ctx.textAlign = "left";
                    }
                }
                
                currentY += canvas.height + 10;
                
                // 绘制状态文本（如果有）
                if (node._previewStatusMessage) {
                    ctx.fillStyle = "#777";
                    ctx.font = "9px Arial";
                    ctx.textAlign = "center";
                    ctx.fillText(node._previewStatusMessage, widget_width / 2, currentY);
                    ctx.textAlign = "left";
                    currentY += 15;
                }
                
                return currentY - y; // 返回widget高度
            },
            
            computeSize: function() {
                // 计算预览widget的尺寸
                const nodeWidth = node.size[0];
                const previewMargin = 20;
                const previewWidth = Math.max(260, nodeWidth - previewMargin);
                const previewHeight = previewWidth; // 1:1比例
                
                // 计算总高度：预览高度 + 边距 + 状态文本高度
                let totalHeight = previewHeight + 20; // 10px上边距 + 10px下边距
                
                // 如果有状态消息，增加15px高度
                if (node._previewStatusMessage) {
                    totalHeight += 15;
                }
                
                return [previewWidth + 20, totalHeight]; // 宽度包含左右边距
            }
        };
        
        // 添加widget到节点
        if (!node.widgets) {
            node.widgets = [];
        }
        node.widgets.push(previewWidget);
        
        // 存储引用
        node._previewWidget = previewWidget;
        node._previewCanvas = null; // 将在第一次绘制时创建
        node._previewExpanded = true; // 总是展开
        node._previewStatusMessage = "";
    }
    
    // 标记预览为可见状态
    node._previewVisible = true;
    
    // 立即更新预览内容
    updatePreview(node);
    
    // 调整节点高度
    nodeFitHeightRobustly(node);
}

/**
 * 隐藏嵌入式预览
 * @param {LGraphNode} node - Overlay Text节点实例
 */
function hideEmbeddedPreview(node) {
    if (node._previewWidget) {
        // 从widgets数组中移除预览widget
        const index = node.widgets.indexOf(node._previewWidget);
        if (index !== -1) {
            node.widgets.splice(index, 1);
        }
        node._previewWidget = null;
        node._previewCanvas = null;
    }
    node._previewVisible = false;
    
    // 调整节点高度
    nodeFitHeightRobustly(node);
}

/**
 * 切换嵌入式预览的显示状态
 * @param {LGraphNode} node - Overlay Text节点实例
 */
function toggleEmbeddedPreview(node) {
    if (!node._previewWidget) {
        showEmbeddedPreview(node);
        return;
    }
    
    // 切换展开/收缩状态
    node._previewExpanded = !node._previewExpanded;
    
    if (node._previewExpanded) {
        // 更新预览内容
        updatePreview(node);
    }
    
    // 调整节点高度
    nodeFitHeightRobustly(node);
    
    // 强制重绘节点
    if (node.graph && node.graph.canvas) {
        node.graph.canvas.setDirty(true);
    }
}

/**
 * 收集连接的文本块数据
 * @param {LGraphNode} node - Overlay Text节点实例
 * @returns {Array} 文本块数据数组
 */
function collectTextBlocks(node) {
    const textBlocks = [];
    
    try {
        // 遍历所有动态输入
        const dynamicInputs = getDynamicInputs(node);
        
        for (const input of dynamicInputs) {
            if (input.link !== null) {
                const link = app.graph.links[input.link];
                if (link) {
                    const sourceNode = app.graph.getNodeById(link.origin_id);
                    if (sourceNode && sourceNode.type === "Text Block") {
                        // 从Text Block节点获取当前的widget值
                        const blockData = extractTextBlockData(sourceNode);
                        if (blockData) {
                            textBlocks.push(blockData);
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error('[WBLESS] Error collecting text blocks:', error);
    }
    
    return textBlocks;
}

/**
 * 从Text Block节点提取数据
 * @param {LGraphNode} textBlockNode - Text Block节点
 * @returns {Object|null} 提取的文本块数据
 */
function extractTextBlockData(textBlockNode) {
    try {
        const data = {};
        
        // 遍历所有可见的widgets获取当前值
        for (const widget of textBlockNode.widgets || []) {
            data[widget.name] = widget.value;
        }
        
        // 遍历隐藏的高级选项widgets（如果存在）
        if (textBlockNode._hiddenWidgets) {
            for (const widget of textBlockNode._hiddenWidgets) {
                data[widget.name] = widget.value;
            }
        }
        
        // 调试信息：输出提取到的数据（只在开发模式下）
        if (window.WBLESS_DEBUG) {
            console.log('[WBLESS] Extracted Text Block data:', data);
        }
        
        return data;
    } catch (error) {
        console.error('[WBLESS] Error extracting text block data:', error);
        return null;
    }
}

/**
 * 收集Overlay Text节点的设置
 * @param {LGraphNode} node - Overlay Text节点实例
 * @returns {Object} 节点设置对象
 */
function collectOverlaySettings(node) {
    const settings = {};
    
    try {
        // 遍历所有widgets获取当前值
        for (const widget of node.widgets || []) {
            settings[widget.name] = widget.value;
        }
    } catch (error) {
        console.error('[WBLESS] Error collecting overlay settings:', error);
    }
    
    return settings;
}



/**
 * 立即更新预览（用于justify等快速响应参数）
 * @param {LGraphNode} node - Overlay Text节点实例
 */
function updatePreviewImmediate(node) {
    if (!node._previewVisible || !node._previewCanvas) {
        return;
    }
    
    try {
        // 收集数据
        const textBlocks = collectTextBlocks(node);
        const overlaySettings = collectOverlaySettings(node);
        
        // 清除缓存，确保下次正常更新时能检测到变化
        node._lastUIHash = null;
        node._lastComplexHash = null;
        
        // 更新状态信息
        if (textBlocks.length === 0) {
            node._previewStatusMessage = 'Connect Text Block nodes to see preview';
        } else {
            node._previewStatusMessage = `${textBlocks.length} text block(s) connected`;
        }
        
        // 立即绘制预览
        drawTextPreview(node._previewCanvas, textBlocks, overlaySettings);
        node._previewNeedsRedraw = false;
        
        // 强制重绘节点以显示更新的预览
        if (node.graph && node.graph.canvas) {
            node.graph.canvas.setDirty(true);
        }
        
        // 调试信息
        if (window.WBLESS_DEBUG) {
            console.log('[WBLESS] Preview updated immediately for parameter change');
        }
        
    } catch (error) {
        console.error('[WBLESS] Error updating preview immediately:', error);
        
        // 设置错误状态
        node._previewStatusMessage = 'Preview error';
        
        // 强制重绘节点
        if (node.graph && node.graph.canvas) {
            node.graph.canvas.setDirty(true);
        }
    }
}

/**
 * 更新预览内容（带缓存优化）
 * @param {LGraphNode} node - Overlay Text节点实例
 */
function updatePreview(node) {
    if (!node._previewVisible || !node._previewCanvas) {
        return;
    }
    
    try {
        // 收集数据
        const textBlocks = collectTextBlocks(node);
        const overlaySettings = collectOverlaySettings(node);
        
        // 分离快速响应的UI参数和复杂计算参数
        const uiParams = {
            justify: overlaySettings.justify,
            align: overlaySettings.align,
            rotation_angle: overlaySettings.rotation_angle,
            // 文本颜色等应该快速响应的参数
            textBlockColors: textBlocks.map(block => ({
                font_color: block?.font_color,
                font_color_hex: block?.font_color_hex,
                opacity: block?.opacity
            }))
        };
        
        const complexParams = {
            textBlocks: textBlocks.map(block => ({
                text: block?.text,
                font_family: block?.font_family,
                font_weight: block?.font_weight,
                font_size: block?.font_size,
                newline: block?.newline,
                auto_newline: block?.auto_newline,  // 添加自动换行开关
                auto_newline_width: block?.auto_newline_width,  // 添加自动换行宽度
                horizontal_spacing: block?.horizontal_spacing,
                vertical_spacing: block?.vertical_spacing,
                letter_spacing: block?.letter_spacing,
                rotation_angle: block?.rotation_angle,
                rotation_options: block?.rotation_options,
                italic: block?.italic,
                bold: block?.bold,
                underline: block?.underline,
                strikethrough: block?.strikethrough,
                text_case: block?.text_case,
                vertical_align: block?.vertical_align
                // 颜色和透明度移到uiParams中，因为它们应该快速响应
            })),
            line_spacing: overlaySettings.line_spacing,
            position_x: overlaySettings.position_x,
            position_y: overlaySettings.position_y
        };
        
        // 计算UI参数哈希（轻量级）
        const uiHash = JSON.stringify(uiParams);
        const complexHash = JSON.stringify(complexParams);
        
        // 检查是否只有UI参数变化
        const onlyUIChanged = (
            node._lastComplexHash === complexHash && 
            node._lastUIHash !== uiHash
        );
        
        // 如果没有任何变化，跳过重绘
        if (node._lastUIHash === uiHash && node._lastComplexHash === complexHash && !node._previewNeedsRedraw) {
            return;
        }
        
        node._lastUIHash = uiHash;
        node._lastComplexHash = complexHash;
        
        // 更新状态信息
        if (textBlocks.length === 0) {
            node._previewStatusMessage = 'Connect Text Block nodes to see preview';
        } else {
            node._previewStatusMessage = `${textBlocks.length} text block(s) connected`;
        }
        
        // 绘制预览
        drawTextPreview(node._previewCanvas, textBlocks, overlaySettings);
        node._previewNeedsRedraw = false;
        
        // 强制重绘节点以显示更新的预览
        if (node.graph && node.graph.canvas) {
            node.graph.canvas.setDirty(true);
        }
        
        // 调试信息
        if (window.WBLESS_DEBUG) {
            if (onlyUIChanged) {
                console.log('[WBLESS] Preview updated with UI changes only:', uiParams);
            } else {
                console.log('[WBLESS] Preview updated with', textBlocks.length, 'text blocks');
            }
        }
        
    } catch (error) {
        console.error('[WBLESS] Error updating preview:', error);
        
        // 设置错误状态
        node._previewStatusMessage = 'Preview error';
        
        // 强制重绘节点
        if (node.graph && node.graph.canvas) {
            node.graph.canvas.setDirty(true);
        }
    }
}

app.registerExtension({
    name: `WBLESS.${NODE_NAME}`,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        // --- Hijack Lifecycle Methods ---

        // 1. onNodeCreated: Called when a new node is created.
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            
            // 初始化预览相关属性
            this._previewVisible = false;
            this._previewContainer = null;
            this._previewCanvas = null;
            this._previewStatusText = null;
            
            // 创建优化的防抖预览函数 - 使用requestAnimationFrame提高性能
            this.updatePreview = debounceRAF(() => updatePreview(this), 30); // 使用30ms + RAF优化
            
            // 创建立即更新预览函数（用于UI参数）
            this.updatePreviewImmediate = () => updatePreviewImmediate(this);
            
            // 包装所有widget的回调函数以支持实时预览更新
            setTimeout(() => {
                for (const widget of this.widgets || []) {
                    const originalCallback = widget.callback;
                    
                    // 检查是否为需要立即响应的UI参数
                    const isUIParam = ['justify', 'align', 'rotation_angle'].includes(widget.name);
                    
                    widget.callback = (value) => {
                        // 先调用原始回调
                        if (originalCallback) {
                            originalCallback.call(widget, value);
                        }
                        
                        // 根据参数类型选择更新方式
                        if (isUIParam) {
                            // UI参数立即更新，无防抖
                            this.updatePreviewImmediate();
                        } else {
                            // 其他参数使用防抖更新
                            this.updatePreview();
                        }
                    };
                }
                
                manageInputs(this);
                nodeFitHeightRobustly(this);
                
                // 默认显示预览
                showEmbeddedPreview(this);
                
                // 设置更好看的默认尺寸
                const defaultNodeWidth = 350; // 默认节点宽度（更宽）
                const minNodeWidth = 280; // 最小节点宽度
                if (this.size[0] < defaultNodeWidth) {
                    this.size[0] = defaultNodeWidth;
                }
                
                // 让computeSize()自动计算合适的默认高度
                setTimeout(() => {
                    nodeFitHeightRobustly(this);
                }, 50); // 稍微延迟确保预览widget已经创建
            }, 10);
        };
        
        // 2. onConnectionsChange: Called when any connection is made or broken.
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
            onConnectionsChange?.apply(this, arguments);
            manageInputs(this);
            nodeFitHeightRobustly(this);
            
            // 当连接变化时，延迟更新预览以确保连接信息完全建立
            setTimeout(() => {
                // 连接变化后更新预览，让computeSize()自动计算高度
                this.updatePreview();
            }, 100);
        };

        // 3. onConfigure: Called when a node is loaded from a workflow.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function() {
            onConfigure?.apply(this, arguments);
            
            // 初始化预览相关属性
            this._previewVisible = false;
            this._previewContainer = null;
            this._previewCanvas = null;
            this._previewStatusText = null;
            
            // 创建优化的防抖预览函数 - 使用requestAnimationFrame提高性能
            this.updatePreview = debounceRAF(() => updatePreview(this), 30); // 使用30ms + RAF优化
            
            // 创建立即更新预览函数（用于UI参数）
            this.updatePreviewImmediate = () => updatePreviewImmediate(this);
            
            setTimeout(() => {
                // 包装所有widget的回调函数以支持实时预览更新
                for (const widget of this.widgets || []) {
                    const originalCallback = widget.callback;
                    
                    // 检查是否为需要立即响应的UI参数
                    const isUIParam = ['justify', 'align', 'rotation_angle'].includes(widget.name);
                    
                    widget.callback = (value) => {
                        // 先调用原始回调
                        if (originalCallback) {
                            originalCallback.call(widget, value);
                        }
                        
                        // 根据参数类型选择更新方式
                        if (isUIParam) {
                            // UI参数立即更新，无防抖
                            this.updatePreviewImmediate();
                        } else {
                            // 其他参数使用防抖更新
                            this.updatePreview();
                        }
                    };
                }
                
                manageInputs(this);
                nodeFitHeightRobustly(this);
                
                // 默认显示预览
                showEmbeddedPreview(this);
                
                // 设置更好看的默认宽度
                const defaultNodeWidth = 350; // 默认节点宽度（更宽）
                const minNodeWidth = 280; // 最小节点宽度
                if (this.size[0] < defaultNodeWidth) {
                    this.size[0] = defaultNodeWidth;
                }
                
                // 让computeSize()自动计算合适的默认高度
                setTimeout(() => {
                    nodeFitHeightRobustly(this);
                }, 50); // 稍微延迟确保预览widget已经创建
                
                // 加载完成后更新预览
                this.updatePreview();
            }, 10);
        };
        
        // 4. 添加右键菜单选项
        const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function(_, options) {
            getExtraMenuOptions?.apply(this, arguments);
            
            options.push({
                content: this._previewVisible ? "Hide Text Preview" : "Show Text Preview",
                callback: () => {
                    if (this._previewVisible) {
                        hideEmbeddedPreview(this);
                    } else {
                        showEmbeddedPreview(this);
                    }
                }
            });
            
            options.push({
                content: window.WBLESS_DEBUG ? "Disable Preview Debug" : "Enable Preview Debug",
                callback: () => {
                    window.WBLESS_DEBUG = !window.WBLESS_DEBUG;
                    console.log(`[WBLESS] Debug mode ${window.WBLESS_DEBUG ? 'enabled' : 'disabled'}`);
                    this.updatePreview(); // 重新绘制预览以应用调试信息
                }
            });
        };
        
        // 5. 监听节点尺寸变化
        const onResize = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function(size) {
            // 设置最小尺寸限制，但不强制增加尺寸
            const minNodeWidth = 280; // 最小宽度
            let minNodeHeight = 200; // 基础最小高度
            
            // 使用computeSize()来计算理想高度
            const computedSize = this.computeSize();
            if (computedSize && computedSize[1]) {
                minNodeHeight = Math.max(minNodeHeight, computedSize[1]);
            }
            
            // 使用平滑的最小尺寸限制，减少跳跃感
            let sizeChanged = false;
            
            // 宽度限制
            if (this.size[0] < minNodeWidth) {
                this.size[0] = minNodeWidth;
                sizeChanged = true;
            }
            
            // 高度限制：只有当明显小于最小高度时才干预
            const heightTolerance = 10; // 10px容差，减少跳跃感
            if (this.size[1] < (minNodeHeight - heightTolerance)) {
                this.size[1] = minNodeHeight;
                sizeChanged = true;
            }
            
            // 调用原始的onResize处理
            const result = onResize?.apply(this, arguments);
            
            // 当节点尺寸变化时，重绘节点以触发预览更新
            if (this._previewVisible && !sizeChanged) {
                // 只有在不是强制尺寸调整时才重绘，避免无限循环
                this.setDirtyCanvas(true, true);
            }
            
            return result;
        };
        
        // 6. 节点被删除时清理预览
        const onRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function() {
            onRemoved?.apply(this, arguments);
            
            // 清理预览相关资源
            if (this._previewWidget) {
                this._previewWidget = null;
                this._previewCanvas = null;
            }
        };
    },
});

