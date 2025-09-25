/**
 * Jimeng Image 4.0 节点前端实现
 * 基于即梦4.0 API的图像生成节点
 */

import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";

const _id = "Jimeng Image 4.0";

// 注册 Jimeng Image 4.0 节点
app.registerExtension({
    name: "WBLESS.JimengImage",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== _id) return;
        
        // 保存原始的 onNodeCreated 方法
        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        
        nodeType.prototype.onNodeCreated = function() {
            // 调用原始方法
            if (originalOnNodeCreated) {
                originalOnNodeCreated.apply(this, arguments);
            }
            
            // 设置节点标题
            this.title = "Jimeng Image 4.0";
            
            // 添加自定义属性
            this.jimeng_config = {
                last_size_mode: "auto",
                visible_images: []
            };
            
            // 初始化时管理图像输入端口
            this.manageImageInputs();
            
            // 初始化控件管理和回调监听
            setTimeout(() => {
                this.setupControlCallbacks();
                this.updateSizeControls();
                this.updateWatermarkControls();
            }, 100);
            
            // 设置初始尺寸
            nodeFitHeightRobustly(this);
        };
        
        // 获取动态图像输入端口
        nodeType.prototype.getDynamicImageInputs = function() {
            return this.inputs?.filter(i => i.name.startsWith("image_")) || [];
        };
        
        // 管理图像输入端口的动态增减
        nodeType.prototype.manageImageInputs = function() {
            const dynamicInputs = this.getDynamicImageInputs();
            const connectedCount = dynamicInputs.reduce((acc, input) => acc + (input.link !== null ? 1 : 0), 0);
            const desiredCount = Math.min(connectedCount + 1, 10); // 最多10个输入
            let currentCount = dynamicInputs.length;
            
            // 添加需要的输入端口
            while (currentCount < desiredCount) {
                this.addInput(`image_${currentCount + 1}`, "IMAGE");
                currentCount++;
            }
            
            // 移除多余的输入端口（从后往前移除未连接的）
            while (currentCount > desiredCount && currentCount > 1) {
                const lastInput = this.inputs[this.inputs.length - 1];
                if (lastInput && lastInput.name.startsWith("image_") && lastInput.link === null) {
                    this.removeInput(this.inputs.length - 1);
                    currentCount--;
                } else {
                    break;
                }
            }
            
            // 确保至少有一个图像输入
            if (this.getDynamicImageInputs().length === 0) {
                this.addInput("image_1", "IMAGE");
            }
            
            // 重新编号所有图像输入端口
            let imageInputIndex = 1;
            this.inputs.forEach(input => {
                if (input.name.startsWith("image_")) {
                    input.name = `image_${imageInputIndex}`;
                    input.label = input.name;
                    imageInputIndex++;
                }
            });
            
            // 调整节点大小
            nodeFitHeightRobustly(this);
        };
        
        // 设置控件回调监听器
        nodeType.prototype.setupControlCallbacks = function() {
            // 设置size_mode控件的回调监听
            const sizeModeWidget = this.widgets?.find(w => w.name === "size_mode");
            if (sizeModeWidget) {
                const originalCallback = sizeModeWidget.callback;
                
                sizeModeWidget.callback = (value) => {
                    // 先调用原始回调
                    if (originalCallback) {
                        originalCallback.call(sizeModeWidget, value);
                    }
                    
                    console.log(`[Jimeng Image 4.0] size_mode 回调触发: ${value}`);
                    // 然后更新控件显示
                    this.updateSizeControls();
                };
            }
            
            // 设置add_watermark控件的回调监听
            const addWatermarkWidget = this.widgets?.find(w => w.name === "add_watermark");
            if (addWatermarkWidget) {
                const originalCallback = addWatermarkWidget.callback;
                
                addWatermarkWidget.callback = (value) => {
                    // 先调用原始回调
                    if (originalCallback) {
                        originalCallback.call(addWatermarkWidget, value);
                    }
                    
                    console.log(`[Jimeng Image 4.0] add_watermark 回调触发: ${value}`);
                    // 然后更新控件显示
                    this.updateWatermarkControls();
                };
            }
        };
        
        // 添加自定义方法：管理尺寸相关控件的显示/隐藏
        nodeType.prototype.updateSizeControls = function() {
            const sizeMode = this.widgets.find(w => w.name === "size_mode")?.value;
            
            console.log(`[Jimeng Image 4.0] updateSizeControls: ${this.jimeng_config.last_size_mode} -> ${sizeMode}`);
            
            // 初始化隐藏控件数组和原始顺序（只在第一次调用时）
            if (!this._hiddenSizeWidgets) {
                this._hiddenSizeWidgets = [];
            }
            if (!this._originalWidgetOrder) {
                this._originalWidgetOrder = this.widgets.map(w => w.name);
            }
            
            // 先恢复所有之前隐藏的尺寸控件
            const restoreWidgets = [...this._hiddenSizeWidgets];
            this._hiddenSizeWidgets = [];
            
            restoreWidgets.forEach(widget => {
                if (!this.widgets.includes(widget)) {
                    // 找到正确的插入位置
                    const insertIndex = this._originalWidgetOrder.indexOf(widget.name);
                    if (insertIndex >= 0) {
                        let actualIndex = 0;
                        for (let i = 0; i < insertIndex; i++) {
                            const originalName = this._originalWidgetOrder[i];
                            if (this.widgets.find(w => w.name === originalName)) {
                                actualIndex++;
                            }
                        }
                        this.widgets.splice(actualIndex, 0, widget);
                        console.log(`[Jimeng Image 4.0] 恢复控件: ${widget.name} 到位置 ${actualIndex}`);
                    }
                }
            });
            
            // 根据模式隐藏相应的控件
            let widgetsToHide = [];
            
            if (sizeMode === "auto") {
                // 自动模式：隐藏所有尺寸控件
                widgetsToHide = ["size", "width", "height"];
            } else if (sizeMode === "custom_size") {
                // 自定义面积模式：隐藏width/height
                widgetsToHide = ["width", "height"];
            } else if (sizeMode === "custom_dimensions") {
                // 自定义尺寸模式：隐藏size
                widgetsToHide = ["size"];
            }
            
            // 隐藏指定的控件
            widgetsToHide.forEach(widgetName => {
                const widgetIndex = this.widgets.findIndex(w => w.name === widgetName);
                if (widgetIndex >= 0) {
                    const widget = this.widgets[widgetIndex];
                    this.widgets.splice(widgetIndex, 1);
                    this._hiddenSizeWidgets.push(widget);
                    console.log(`[Jimeng Image 4.0] 隐藏控件: ${widgetName}`);
                }
            });
            
            // 更新最后的模式状态
            this.jimeng_config.last_size_mode = sizeMode;
            
            // 调整节点大小
            nodeFitHeightRobustly(this);
        };
        
        // 添加自定义方法：管理水印相关控件的显示/隐藏
        nodeType.prototype.updateWatermarkControls = function() {
            const addWatermark = this.widgets.find(w => w.name === "add_watermark")?.value;
            
            console.log(`[Jimeng Image 4.0] updateWatermarkControls: ${addWatermark}`);
            
            // 初始化隐藏控件数组
            if (!this._hiddenWatermarkWidgets) {
                this._hiddenWatermarkWidgets = [];
            }
            if (!this._originalWidgetOrder) {
                this._originalWidgetOrder = this.widgets.map(w => w.name);
            }
            
            const watermarkControlNames = ["watermark_position", "watermark_language", "watermark_opacity", "watermark_text"];
            
            if (addWatermark) {
                // 启用水印：恢复所有水印控件
                const restoreWidgets = [...this._hiddenWatermarkWidgets];
                this._hiddenWatermarkWidgets = [];
                
                restoreWidgets.forEach(widget => {
                    if (!this.widgets.includes(widget)) {
                        // 找到正确的插入位置
                        const insertIndex = this._originalWidgetOrder.indexOf(widget.name);
                        if (insertIndex >= 0) {
                            let actualIndex = 0;
                            for (let i = 0; i < insertIndex; i++) {
                                const originalName = this._originalWidgetOrder[i];
                                if (this.widgets.find(w => w.name === originalName)) {
                                    actualIndex++;
                                }
                            }
                            this.widgets.splice(actualIndex, 0, widget);
                            console.log(`[Jimeng Image 4.0] 恢复水印控件: ${widget.name} 到位置 ${actualIndex}`);
                        }
                    }
                });
            } else {
                // 禁用水印：隐藏所有水印控件
                watermarkControlNames.forEach(widgetName => {
                    const widgetIndex = this.widgets.findIndex(w => w.name === widgetName);
                    if (widgetIndex >= 0) {
                        const widget = this.widgets[widgetIndex];
                        this.widgets.splice(widgetIndex, 1);
                        this._hiddenWatermarkWidgets.push(widget);
                        console.log(`[Jimeng Image 4.0] 隐藏水印控件: ${widgetName}`);
                    }
                });
            }
            
            // 调整节点大小
            nodeFitHeightRobustly(this);
        };
        
        // 重写 onConnectionsChange 方法
        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function(type, index, connected, link_info) {
            // 调用原始方法
            if (originalOnConnectionsChange) {
                originalOnConnectionsChange.apply(this, arguments);
            }
            
            // 如果是图像输入的连接变化，更新端口管理
            if (type === 1) { // 输入连接
                const input = this.inputs[index];
                if (input && input.name.startsWith("image_")) {
                    setTimeout(() => {
                        this.manageImageInputs();
                    }, 10);
                }
            }
        };
        
        // 重写 onConfigure 方法
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            // 调用原始方法
            if (originalOnConfigure) {
                originalOnConfigure.apply(this, arguments);
            }
            
            // 延迟执行初始化，确保所有数据都已加载
            setTimeout(() => {
                this.manageImageInputs();
                this.setupControlCallbacks();
                this.updateSizeControls();
                this.updateWatermarkControls();
            }, 100);
        };
        
        // 添加控件变化监听器
        const originalOnWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function(widget, value, old_value, app) {
            // 调用原始方法
            if (originalOnWidgetChanged) {
                originalOnWidgetChanged.apply(this, arguments);
            }
            
            // 验证输入参数（控件显示/隐藏现在通过回调处理）
            this.validateInputs(widget, value);
        };
        
        // 添加输入验证方法
        nodeType.prototype.validateInputs = function(widget, value) {
            if (widget.name === "min_ratio" || widget.name === "max_ratio") {
                const minRatio = this.widgets.find(w => w.name === "min_ratio")?.value || 0.33;
                const maxRatio = this.widgets.find(w => w.name === "max_ratio")?.value || 3.0;
                
                if (minRatio >= maxRatio) {
                    console.warn("[Jimeng Image 4.0] 警告：最小宽高比应小于最大宽高比");
                }
            }
            
            if (widget.name === "width" || widget.name === "height") {
                const width = this.widgets.find(w => w.name === "width")?.value || 2048;
                const height = this.widgets.find(w => w.name === "height")?.value || 2048;
                const area = width * height;
                
                if (area < 1048576 || area > 16777216) {
                    console.warn("[Jimeng Image 4.0] 警告：图像面积应在 1024x1024 到 4096x4096 之间");
                }
                
                const ratio = width / height;
                if (ratio < 0.0625 || ratio > 16) {
                    console.warn("[Jimeng Image 4.0] 警告：宽高比应在 1/16 到 16 之间");
                }
            }
            
            if (widget.name === "scale") {
                if (value < 0 || value > 1) {
                    console.warn("[Jimeng Image 4.0] 警告：Scale 值应在 0 到 1 之间");
                }
            }
        };
        
        // 添加节点右键菜单选项
        const originalGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function(_, options) {
            // 调用原始方法
            if (originalGetExtraMenuOptions) {
                originalGetExtraMenuOptions.apply(this, arguments);
            }
            
            options.push({
                content: "重置为推荐设置",
                callback: () => {
                    // 重置为推荐的参数值
                    const widgets = {
                        "size_mode": "auto",
                        "scale": 0.5,
                        "force_single": true,
                        "min_ratio": 0.33,
                        "max_ratio": 3.0,
                        "add_watermark": false,
                        "timeout": 300,
                        "poll_interval": 5
                    };
                    
                    for (const [name, value] of Object.entries(widgets)) {
                        const widget = this.widgets.find(w => w.name === name);
                        if (widget) {
                            widget.value = value;
                        }
                    }
                    
                    // 更新控件显示状态
                    this.updateSizeControls();
                    this.updateWatermarkControls();
                    
                    console.log("[Jimeng Image 4.0] 已重置为推荐设置");
                }
            });
            
            options.push({
                content: "API密钥设置帮助",
                callback: () => {
                    const helpText = `🔑 API密钥设置帮助

1. 火山引擎密钥：
   • 访问火山引擎控制台
   • 开通即梦4.0服务
   • 创建访问密钥
   • Access Key: 通常以AKIA开头
   • Secret Key: 长度较长的随机字符串

2. PicGo API密钥（必需）：
   • 访问 https://www.picgo.net
   • 注册账户并获取API密钥
   • 用于上传输入图片到图床
   • ⚠️ 即梦4.0只支持公开URL，必须提供PicGo密钥
   • 如有图片输入但无PicGo密钥将报错

3. 常见问题：
   • Access Denied: 检查密钥是否正确
   • 账户余额是否充足
   • 服务是否已开通

4. 安全提醒：
   • 不要在公开场所暴露密钥
   • 定期更换密钥`;
                    
                    alert(helpText);
                }
            });
            
            options.push({
                content: "显示API文档",
                callback: () => {
                    const docUrl = "https://www.volcengine.com/docs/6791/1295829";
                    window.open(docUrl, "_blank");
                }
            });
            
            options.push({
                content: "检查SDK状态",
                callback: async () => {
                    try {
                        // 发送一个测试请求来检查SDK状态
                        const response = await fetch('/wbless/check_jimeng_sdk', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({})
                        });
                        
                        const result = await response.json();
                        
                        if (result.available) {
                            alert("✅ 火山引擎SDK状态正常！");
                        } else {
                            alert(`❌ SDK不可用: ${result.message}\n\n建议:\n1. 重启ComfyUI\n2. 手动安装: pip install volcengine`);
                        }
                    } catch (error) {
                        alert(`❌ 无法检查SDK状态: ${error.message}`);
                    }
                }
            });
            
            options.push(null); // 分隔线
            
            options.push({
                content: "显示所有图像输入",
                callback: () => {
                    // 添加所有10个图像输入端口
                    const currentImageInputs = this.getDynamicImageInputs();
                    const currentCount = currentImageInputs.length;
                    
                    for (let i = currentCount; i < 10; i++) {
                        this.addInput(`image_${i + 1}`, "IMAGE");
                    }
                    
                    // 重新编号
                    let imageInputIndex = 1;
                    this.inputs.forEach(input => {
                        if (input.name.startsWith("image_")) {
                            input.name = `image_${imageInputIndex}`;
                            input.label = input.name;
                            imageInputIndex++;
                        }
                    });
                    
                    nodeFitHeightRobustly(this);
                    console.log("[Jimeng Image 4.0] 已显示所有图像输入端口");
                }
            });
            
            options.push({
                content: "重新管理图像输入端口",
                callback: () => {
                    this.manageImageInputs();
                    console.log("[Jimeng Image 4.0] 已重新管理图像输入端口");
                }
            });
        };
        
        // 添加序列化支持
        const originalOnSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function(info) {
            // 调用原始方法
            if (originalOnSerialize) {
                originalOnSerialize.apply(this, arguments);
            }
            
            // 保存自定义配置
            info.jimeng_config = this.jimeng_config;
        };
        
        const originalOnConfigure2 = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            // 调用原始方法
            if (originalOnConfigure2) {
                originalOnConfigure2.apply(this, arguments);
            }
            
            // 恢复自定义配置
            if (info.jimeng_config) {
                this.jimeng_config = { ...this.jimeng_config, ...info.jimeng_config };
            }
        };
    }
});
