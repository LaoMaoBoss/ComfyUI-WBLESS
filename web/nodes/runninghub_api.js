import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";
import { ComfyWidgets } from "../../../scripts/widgets.js";

const NODE_NAME = "RunningHUB API";
const API_HOST = "www.runninghub.cn";

/**
 * 获取指定名称的 widget
 * @param {Object} node - 节点对象
 * @param {string} widgetName - widget 名称
 * @returns {Object|null} widget 对象
 */
function getWidgetByName(node, widgetName) {
    return node.widgets?.find(w => w.name === widgetName);
}

/**
 * 获取节点的所有动态图片输入
 * @param {Object} node - 节点对象
 * @returns {Array} 动态图片输入数组
 */
function getDynamicImageInputs(node) {
    return node.inputs?.filter(i => i.name.startsWith("image_")) || [];
}

/**
 * 管理动态图片输入端口
 * 根据节点信息中的 IMAGE 类型字段创建对应的输入端口
 * @param {Object} node - 节点对象
 * @param {Array} nodeInfoList - 节点信息列表
 */
function manageImageInputs(node, nodeInfoList) {
    if (!nodeInfoList || nodeInfoList.length === 0) {
        // 如果没有节点信息，清除所有动态输入
        clearDynamicImageInputs(node);
        return;
    }

    // 找出所有 IMAGE 类型的字段
    const imageFields = nodeInfoList.filter(info => info.fieldType === "IMAGE");

    // 获取当前的动态输入
    const currentInputs = getDynamicImageInputs(node);

    // 创建期望的输入端口映射 {inputName: nodeInfo}
    const desiredInputs = {};
    imageFields.forEach(info => {
        const inputName = `image_${info.nodeId}_${info.fieldName}`;
        desiredInputs[inputName] = info;
    });

    // 移除不再需要的输入端口（从后往前删除）
    for (let i = node.inputs.length - 1; i >= 0; i--) {
        const input = node.inputs[i];
        if (input.name.startsWith("image_") && !desiredInputs[input.name]) {
            node.removeInput(i);
        }
    }

    // 添加缺失的输入端口
    Object.entries(desiredInputs).forEach(([inputName, nodeInfo]) => {
        const existingInput = node.inputs?.find(i => i.name === inputName);
        if (!existingInput) {
            const label = `[${nodeInfo.nodeId}] ${nodeInfo.description || nodeInfo.fieldName}`;
            node.addInput(inputName, "IMAGE");
            // 设置输入端口的标签
            const addedInput = node.inputs[node.inputs.length - 1];
            if (addedInput) {
                addedInput.label = label;
                // 存储节点信息到输入端口
                addedInput._nodeInfo = nodeInfo;
            }
        }
    });

    console.log("[WBLESS][RunningHub API] 动态图片输入端口已更新:", Object.keys(desiredInputs));
}

/**
 * 清除所有动态图片输入端口
 * @param {Object} node - 节点对象
 */
function clearDynamicImageInputs(node) {
    if (!node.inputs) return;

    for (let i = node.inputs.length - 1; i >= 0; i--) {
        const input = node.inputs[i];
        if (input.name.startsWith("image_")) {
            node.removeInput(i);
        }
    }
}

/**
 * 从 RunningHub API 获取节点信息列表
 * @param {string} apiKey - API 密钥
 * @param {string} webappId - WebApp ID
 * @returns {Promise<Array>} 节点信息列表
 */
async function fetchNodeInfoList(apiKey, webappId) {
    try {
        const url = `https://${API_HOST}/api/webapp/apiCallDemo?apiKey=${apiKey}&webappId=${webappId}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const nodeInfoList = data?.data?.nodeInfoList || [];

        console.log("[WBLESS][RunningHub API] 获取到节点信息:", nodeInfoList);
        return nodeInfoList;

    } catch (error) {
        console.error("[WBLESS][RunningHub API] 获取节点信息失败:", error);
        throw error;
    }
}

/**
 * 清除动态生成的 widgets
 * @param {Object} node - 节点对象
 */
function clearDynamicWidgets(node) {
    if (!node.widgets) return;

    // 保留基础 widgets（api_key, webapp_id, node_modifications, timeout）
    const baseWidgetNames = ["api_key", "webapp_id", "node_modifications", "timeout"];

    // 找到所有需要删除的 widget 索引（从后往前删除）
    for (let i = node.widgets.length - 1; i >= 0; i--) {
        const widget = node.widgets[i];
        if (!baseWidgetNames.includes(widget.name)) {
            // 清理 widget 的 DOM 元素
            if (widget.inputEl && widget.inputEl.parentNode) {
                widget.inputEl.parentNode.removeChild(widget.inputEl);
            }
            if (widget.element && widget.element.parentNode) {
                widget.element.parentNode.removeChild(widget.element);
            }

            // 删除 widget
            node.widgets.splice(i, 1);
        }
    }
}

/**
 * 根据节点信息列表生成动态 widgets
 * @param {Object} node - 节点对象
 * @param {Array} nodeInfoList - 节点信息列表
 * @param {Boolean} skipUpdateModifications - 是否跳过更新 node_modifications（用于恢复时）
 * @param {Boolean} skipFitHeight - 是否跳过调整节点高度（用于恢复时）
 */
function generateDynamicWidgets(node, nodeInfoList, skipUpdateModifications = false, skipFitHeight = false) {
    // 清除之前的动态 widgets
    clearDynamicWidgets(node);

    // 管理动态图片输入端口
    manageImageInputs(node, nodeInfoList);

    // 为每个节点字段创建对应的 widget（排除 IMAGE 类型，因为已经创建了输入端口）
    nodeInfoList.forEach((nodeInfo, index) => {
        const { nodeId, nodeName, fieldName, fieldValue, fieldType, description, fieldData } = nodeInfo;

        // IMAGE 类型不创建 widget，因为已经创建了输入端口
        if (fieldType === "IMAGE") {
            return;
        }

        const widgetName = `node_${index}_${nodeId}_${fieldName}`;
        const widgetLabel = `[${nodeId}] ${description || fieldName}`;

        let widget;

        if (fieldType === "STRING") {
            // 多行文本输入框 - 使用 ComfyWidgets 创建
            const widgetInfo = ComfyWidgets["STRING"](
                node,
                widgetName,
                ["STRING", { multiline: true }],
                app
            );
            widget = widgetInfo.widget;
            widget.label = widgetLabel;
            widget.value = fieldValue || "";

            // 添加回调
            const originalCallback = widget.callback;
            widget.callback = function (value) {
                originalCallback?.apply(this, arguments);
                updateNodeModifications(node);
            };


        } else if (fieldType === "LIST") {
            // 下拉选择框
            const options = fieldData || [fieldValue];
            widget = node.addWidget(
                "combo",
                widgetName,
                fieldValue || options[0],
                (value) => {
                    updateNodeModifications(node);
                },
                { values: options }
            );
            widget.label = widgetLabel;

        } else if (fieldType === "AUDIO" || fieldType === "VIDEO") {
            // 其他文件类型，显示提示信息
            widget = node.addWidget(
                "text",
                widgetName,
                `[${fieldType}] 请手动填写文件路径`,
                (value) => {
                    updateNodeModifications(node);
                },
                {}
            );
            widget.label = widgetLabel;
        } else {
            // 其他类型，使用文本输入
            widget = node.addWidget(
                "text",
                widgetName,
                fieldValue || "",
                (value) => {
                    updateNodeModifications(node);
                },
                {}
            );
            widget.label = widgetLabel;
        }

        // 存储原始节点信息到 widget
        if (widget) {
            widget._nodeInfo = nodeInfo;
        }
    });

    // 更新 node_modifications（除非是恢复时）
    if (!skipUpdateModifications) {
        updateNodeModifications(node);
    }

    // 调整节点高度（除非是恢复时）
    if (!skipFitHeight) {
        nodeFitHeightRobustly(node);
    }
}

/**
 * 更新 node_modifications widget 的值
 * @param {Object} node - 节点对象
 */
function updateNodeModifications(node) {
    const nodeModsWidget = getWidgetByName(node, "node_modifications");
    if (!nodeModsWidget) return;

    // 收集所有节点信息（包括 widgets 和 inputs）
    const modifications = [];

    // 1. 从 widgets 收集节点信息（非 IMAGE 类型）
    node.widgets.forEach(widget => {
        if (widget._nodeInfo) {
            const nodeInfo = { ...widget._nodeInfo };

            // 更新 fieldValue（除了 IMAGE/AUDIO/VIDEO 类型，这些由后端处理）
            if (!["IMAGE", "AUDIO", "VIDEO"].includes(nodeInfo.fieldType)) {
                nodeInfo.fieldValue = widget.value;
            }

            modifications.push(nodeInfo);
        }
    });

    // 2. 从 inputs 收集节点信息（IMAGE 类型）
    if (node.inputs) {
        node.inputs.forEach(input => {
            if (input._nodeInfo) {
                const nodeInfo = { ...input._nodeInfo };
                // IMAGE 类型的 fieldValue 由后端处理，保持原值
                modifications.push(nodeInfo);
            }
        });
    }

    // 更新 node_modifications widget
    nodeModsWidget.value = JSON.stringify(modifications, null, 2);

    console.log("[WBLESS][RunningHub API] 更新节点修改配置:", modifications);
    console.log("[WBLESS][RunningHub API] 从 inputs 收集到的节点数:", node.inputs?.filter(i => i._nodeInfo).length || 0);
}

/**
 * 刷新节点信息
 * @param {Object} node - 节点对象
 */
async function refreshNodeInfo(node) {
    const apiKeyWidget = getWidgetByName(node, "api_key");
    const webappIdWidget = getWidgetByName(node, "webapp_id");

    if (!apiKeyWidget || !webappIdWidget) {
        console.warn("[WBLESS][RunningHub API] 缺少必要的 widget");
        return;
    }

    const apiKey = apiKeyWidget.value?.trim();
    const webappId = webappIdWidget.value?.trim();

    if (!apiKey || !webappId) {
        console.warn("[WBLESS][RunningHub API] 请先输入 API Key 和 WebApp ID");
        alert("请先输入 API Key 和 WebApp ID");
        return;
    }

    // 防止重复刷新
    if (node._refreshing) {
        console.info("[WBLESS][RunningHub API] 正在刷新中，请稍候...");
        return;
    }

    try {
        node._refreshing = true;
        console.log("[WBLESS][RunningHub API] 开始刷新节点信息...");

        // 获取节点信息列表
        const nodeInfoList = await fetchNodeInfoList(apiKey, webappId);

        if (!nodeInfoList || nodeInfoList.length === 0) {
            console.warn("[WBLESS][RunningHub API] 未获取到节点信息");
            alert("未获取到节点信息，请检查 API Key 和 WebApp ID 是否正确");
            return;
        }

        // 生成动态 widgets
        generateDynamicWidgets(node, nodeInfoList);

        console.log("[WBLESS][RunningHub API] 节点信息刷新成功");

        // 标记节点已初始化
        node._nodeInfoInitialized = true;

    } catch (error) {
        console.error("[WBLESS][RunningHub API] 刷新节点信息失败:", error);
        alert(`刷新节点信息失败: ${error.message}`);
    } finally {
        node._refreshing = false;
    }
}

/**
 * 监听 API Key 和 WebApp ID 的变化，实现智能刷新
 * @param {Object} node - 节点对象
 */
function watchApiKeyAndWebappId(node) {
    const apiKeyWidget = getWidgetByName(node, "api_key");
    const webappIdWidget = getWidgetByName(node, "webapp_id");

    if (!apiKeyWidget || !webappIdWidget) return;

    // 避免重复添加监听
    if (apiKeyWidget._runninghubWatched) return;

    // 保存原始回调
    const originalApiKeyCallback = apiKeyWidget.callback;
    const originalWebappIdCallback = webappIdWidget.callback;

    // 初始化时记录当前值，避免页面刷新时触发刷新
    node._lastApiKey = apiKeyWidget.value?.trim() || "";
    node._lastWebappId = webappIdWidget.value?.trim() || "";

    // 智能刷新函数
    const smartRefresh = () => {
        const apiKey = apiKeyWidget.value?.trim();
        const webappId = webappIdWidget.value?.trim();

        // 检查是否与上次的值相同
        const lastApiKey = node._lastApiKey || "";
        const lastWebappId = node._lastWebappId || "";

        // 只有当两个值都不为空时才自动刷新
        if (apiKey && webappId) {
            // 检查是否真的改变了
            const apiKeyChanged = apiKey !== lastApiKey;
            const webappIdChanged = webappId !== lastWebappId;

            // 只有当 API Key 或 WebApp ID 改变时才刷新
            if (apiKeyChanged || webappIdChanged) {
                // 更新记录的值
                node._lastApiKey = apiKey;
                node._lastWebappId = webappId;

                // 使用防抖，避免频繁刷新
                if (node._smartRefreshTimeout) {
                    clearTimeout(node._smartRefreshTimeout);
                }

                node._smartRefreshTimeout = setTimeout(() => {
                    console.log("[WBLESS][RunningHub API] 检测到 API Key 或 WebApp ID 改变，自动刷新节点信息");
                    refreshNodeInfo(node);
                }, 800); // 800ms 防抖延迟
            }
        } else {
            // 如果任一值为空，清除动态内容
            if (!apiKey || !webappId) {
                clearDynamicWidgets(node);
                clearDynamicImageInputs(node);
                const nodeModsWidget = getWidgetByName(node, "node_modifications");
                if (nodeModsWidget) {
                    nodeModsWidget.value = "[]";
                }
                node._nodeInfoInitialized = false;
                node._lastApiKey = "";
                node._lastWebappId = "";
            }
        }
    };

    // 添加新的回调
    apiKeyWidget.callback = function () {
        originalApiKeyCallback?.apply(this, arguments);
        smartRefresh();
    };

    webappIdWidget.callback = function () {
        originalWebappIdCallback?.apply(this, arguments);
        smartRefresh();
    };

    // 标记已添加监听
    apiKeyWidget._runninghubWatched = true;
    webappIdWidget._runninghubWatched = true;
}

// 注册扩展
app.registerExtension({
    name: "wbless.node.RunningHubApi",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        // 只处理 RunningHUB API 节点
        if (nodeData.name !== NODE_NAME) return;

        // 重写节点创建方法
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);

            // 监听 API Key 和 WebApp ID 变化（智能刷新）
            watchApiKeyAndWebappId(this);

            // 调整节点高度
            nodeFitHeightRobustly(this);
        };

        // 重写配置方法（用于加载保存的工作流）
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            onConfigure?.apply(this, arguments);

            setTimeout(() => {
                // 如果有保存的 node_modifications，尝试恢复动态 widgets
                const nodeModsWidget = getWidgetByName(this, "node_modifications");
                if (nodeModsWidget && nodeModsWidget.value && nodeModsWidget.value !== "[]") {
                    try {
                        const nodeInfoList = JSON.parse(nodeModsWidget.value);
                        if (nodeInfoList.length > 0) {
                            // 恢复动态 widgets（跳过更新 node_modifications 和高度调整，保留原有值和用户设置的高度）
                            generateDynamicWidgets(this, nodeInfoList, true, true);
                            this._nodeInfoInitialized = true;

                            // 记录当前的 API Key 和 WebApp ID，避免触发智能刷新
                            const apiKeyWidget = getWidgetByName(this, "api_key");
                            const webappIdWidget = getWidgetByName(this, "webapp_id");
                            if (apiKeyWidget && webappIdWidget) {
                                this._lastApiKey = apiKeyWidget.value?.trim() || "";
                                this._lastWebappId = webappIdWidget.value?.trim() || "";
                            }
                        }
                    } catch (e) {
                        console.warn("[WBLESS][RunningHub API] 恢复节点信息失败:", e);
                    }
                }

                // 监听 API Key 和 WebApp ID 变化（智能刷新）
                // 放在恢复之后，避免触发不必要的刷新
                watchApiKeyAndWebappId(this);
            }, 10);
        };
    },
});
