import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";

const _id = "API Core-RustFS";
const _type = "IMAGE";
const MODEL_WIDGET_NAME = "model";
const API_KEY_WIDGET_NAME = "api_key";
const N_WIDGET_NAME = "n";
const DEFAULT_MODEL_OPTIONS = [
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-hd",
];
const MODEL_API_ENDPOINT = "https://api.apicore.ai/v1/models";

/**
 * 获取节点的所有动态image输入
 * @param {Object} node - 节点对象
 * @returns {Array} 动态image输入数组
 */
function getDynamicInputs(node) {
    return node.inputs?.filter(i => i.name.startsWith("image_")) || [];
}

/**
 * 获取节点的所有动态preview输出
 * @param {Object} node - 节点对象
 * @returns {Array} 动态preview输出数组
 */
function getDynamicOutputs(node) {
    return node.outputs?.filter(o => o.name.startsWith("preview_")) || [];
}

/**
 * 管理动态输入端口 - 添加或删除输入端口
 * 当一个输入被连接时，自动添加一个新的输入端口
 * @param {Object} node - 节点对象
 */
function manageInputs(node) {
    const dynamicInputs = getDynamicInputs(node);
    const connectedCount = dynamicInputs.reduce((acc, input) => acc + (input.link !== null ? 1 : 0), 0);
    const desiredCount = connectedCount + 1;
    let currentCount = dynamicInputs.length;

    // 添加缺失的输入端口
    while (currentCount < desiredCount) {
        node.addInput(`image_${currentCount + 1}`, _type);
        currentCount++;
    }

    // 移除末尾未连接的输入端口
    while (currentCount > desiredCount) {
        const lastInput = node.inputs[node.inputs.length - 1];
        if (lastInput && lastInput.name.startsWith("image_") && lastInput.link === null) {
            node.removeInput(node.inputs.length - 1);
            currentCount--;
        } else {
            break;
        }
    }

    // 确保至少有一个输入端口
    if (getDynamicInputs(node).length === 0) {
        node.addInput("image_1", _type);
    }
    
    // 重新编号所有输入端口
    let dynamicInputIndex = 1;
    node.inputs.forEach(input => {
        if (input.name.startsWith("image_")) {
            input.name = `image_${dynamicInputIndex}`;
            input.label = `Image ${dynamicInputIndex}`;
            dynamicInputIndex++;
        }
    });
}

/**
 * 管理动态输出端口 - 根据n的值添加或删除输出端口
 * @param {Object} node - 节点对象
 */
function manageOutputs(node) {
    const nWidget = getWidgetByName(node, N_WIDGET_NAME);
    if (!nWidget) return;

    const nValue = parseInt(nWidget.value, 10) || 1;
    const desiredCount = Math.max(1, Math.min(nValue, 10)); // 限制最多10个输出
    const dynamicOutputs = getDynamicOutputs(node);
    let currentCount = dynamicOutputs.length;

    // 添加缺失的输出端口
    while (currentCount < desiredCount) {
        node.addOutput(`preview_${currentCount + 1}`, _type);
        currentCount++;
    }

    // 移除多余的输出端口
    while (currentCount > desiredCount) {
        const lastOutput = node.outputs[node.outputs.length - 1];
        if (lastOutput && lastOutput.name.startsWith("preview_")) {
            node.removeOutput(node.outputs.length - 1);
            currentCount--;
        } else {
            break;
        }
    }

    // 重新编号所有输出端口
    let dynamicOutputIndex = 1;
    node.outputs.forEach(output => {
        if (output.name.startsWith("preview_")) {
            output.name = `preview_${dynamicOutputIndex}`;
            output.label = `Preview ${dynamicOutputIndex}`;
            dynamicOutputIndex++;
        }
    });
}

/**
 * 更新输入和输出端口的类型
 * 确保端口类型与连接的节点匹配
 * @param {Object} node - 节点对象
 */
function updateTypes(node) {
    const dynamicInputs = getDynamicInputs(node);
    const dynamicOutputs = getDynamicOutputs(node);

    let newType = _type;

    // 检查所有连接的输入，确定输出类型
    for (const input of dynamicInputs) {
        if (input.link !== null) {
            const linkInfo = app.graph.links[input.link];
            if (linkInfo) {
                const originNode = app.graph.getNodeById(linkInfo.origin_id);
                if (originNode && originNode.outputs && originNode.outputs[linkInfo.origin_slot]) {
                    newType = originNode.outputs[linkInfo.origin_slot].type;
                    break;
                }
            }
        }
    }

    // 更新所有动态输入的类型
    dynamicInputs.forEach(input => {
        if (input.type !== newType) {
            input.type = newType;
        }
    });

    // 更新所有动态输出的类型
    dynamicOutputs.forEach(output => {
        if (output.type !== newType) {
            output.type = newType;
        }
    });
}

function getWidgetByName(node, widgetName) {
    return node.widgets?.find(w => w.name === widgetName);
}

function setModelWidgetValues(node, values, { updateCanvas = true } = {}) {
    ensureModelCombo(node);
    const widget = getWidgetByName(node, MODEL_WIDGET_NAME);
    if (!widget) return;

    const cleaned = [...new Set((values || []).filter(v => typeof v === "string" && v.trim().length > 0))];
    const finalValues = cleaned.length > 0 ? cleaned : DEFAULT_MODEL_OPTIONS;

    widget.options = widget.options || {};
    widget.options.values = finalValues;

    if (!finalValues.includes(widget.value)) {
        widget.value = finalValues[0];
        if (node.onWidgetChanged) {
            node.onWidgetChanged(widget, widget.value, undefined, undefined);
        }
    }

    if (updateCanvas && node.graph) {
        node.graph.setDirtyCanvas(true, true);
    }
}


function ensureApiKeyWatcher(node) {
    const widget = getWidgetByName(node, API_KEY_WIDGET_NAME);
    if (!widget || widget.__apicorePatched) return;
    const original = widget.callback;
    widget.callback = function () {
        original?.apply(this, arguments);
        scheduleModelRefresh(node);
    };
    widget.__apicorePatched = true;
}

function ensureNWatcher(node) {
    const widget = getWidgetByName(node, N_WIDGET_NAME);
    if (!widget || widget.__apicoreNWatched) return;
    const original = widget.callback;
    // 使用闭包捕获node引用，确保callback中能正确访问node
    widget.callback = function () {
        original?.apply(this, arguments);
        manageOutputs(node);
        nodeFitHeightRobustly(node);
    };
    widget.__apicoreNWatched = true;
}

function scheduleModelRefresh(node) {
    if (node.__apicoreModelDebounce) {
        clearTimeout(node.__apicoreModelDebounce);
    }
    node.__apicoreModelDebounce = setTimeout(() => refreshModelList(node, false), 400);
}

async function refreshModelList(node, manual = false) {
    ensureModelCombo(node);
    const apiKeyWidget = getWidgetByName(node, API_KEY_WIDGET_NAME);
    const modelWidget = getWidgetByName(node, MODEL_WIDGET_NAME);
    if (!apiKeyWidget || !modelWidget) return;

    const apiKey = (apiKeyWidget.value || "").trim();
    if (!apiKey || apiKey === "sk-xxxx") {
        setModelWidgetValues(node, ["请先输入API Key"]);
        return;
    }

    if (node.__apicoreModelLoading) {
        if (manual) {
            console.info("[WBLESS][API Core] 模型列表正在刷新，请稍候...");
        }
        return;
    }

    node.__apicoreModelLoading = true;
    setModelWidgetValues(node, ["加载中..."]);

    try {
        const response = await fetch(MODEL_API_ENDPOINT, {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${apiKey}`,
                "Content-Type": "application/json",
            },
        });

        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || `HTTP ${response.status}`);
        }

        const payload = await response.json();
        const ids = Array.isArray(payload?.data)
            ? payload.data
                .map(item => (typeof item?.id === "string" ? item.id.trim() : ""))
                .filter(id => id.length > 0)
            : [];

        if (ids.length === 0) {
            ids.push("无可用模型");
        }

        setModelWidgetValues(node, ids);
    } catch (err) {
        console.error("[WBLESS][API Core] 获取模型列表失败：", err);
        // 检查是否是默认值或空值
        const apiKey = (apiKeyWidget.value || "").trim();
        if (!apiKey || apiKey === "sk-xxxx") {
            setModelWidgetValues(node, ["请先输入API Key"]);
        } else {
            setModelWidgetValues(node, ["获取失败，请检查控制台"]);
        }
    } finally {
        node.__apicoreModelLoading = false;
    }
}

function initializeModelSelector(node) {
    ensureModelCombo(node);
    ensureApiKeyWatcher(node);
    if (!node.__apicoreModelInitialized) {
        setModelWidgetValues(node, DEFAULT_MODEL_OPTIONS, { updateCanvas: false });
        node.__apicoreModelInitialized = true;
        setTimeout(() => refreshModelList(node, false), 100);
    }
}

function ensureModelCombo(node) {
    if (!node.widgets) return;
    const widgetIndex = node.widgets.findIndex(w => w.name === MODEL_WIDGET_NAME);
    if (widgetIndex === -1) return;
    const currentWidget = node.widgets[widgetIndex];
    if (currentWidget.type === "combo" && currentWidget.options) {
        return;
    }

    const initialValue = currentWidget.value;
    const originalCallback = currentWidget.callback;

    node.widgets.splice(widgetIndex, 1);

    const comboWidget = node.addWidget(
        "combo",
        MODEL_WIDGET_NAME,
        initialValue,
        (value) => {
            originalCallback?.call(node, value);
        },
        { values: DEFAULT_MODEL_OPTIONS.slice() }
    );

    node.widgets.pop();
    comboWidget.options = comboWidget.options || {};
    if (!comboWidget.options.values || comboWidget.options.values.length === 0) {
        comboWidget.options.values = DEFAULT_MODEL_OPTIONS.slice();
    }
    node.widgets.splice(widgetIndex, 0, comboWidget);
    node.__apicoreModelComboInitialized = true;
}

// 注册扩展
app.registerExtension({
    name: "wbless.node." + _id,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        // 只处理APICore节点
        if (nodeData.name !== _id) return;

        // 重写节点创建方法
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            manageInputs(this);
            manageOutputs(this);
            updateTypes(this);
            initializeModelSelector(this);
            ensureNWatcher(this);
            nodeFitHeightRobustly(this);
        };
        
        // 重写连接变化方法
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info, slot) {
            onConnectionsChange?.apply(this, arguments);
            manageInputs(this);
            updateTypes(this);
            nodeFitHeightRobustly(this);
        };

        // 重写控件变化方法
        const onWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function(widget, value, old_value, app) {
            if (onWidgetChanged) {
                onWidgetChanged.apply(this, arguments);
            }
            // 当n控件的值变化时，实时更新输出端口
            if (widget && widget.name === N_WIDGET_NAME) {
                manageOutputs(this);
                nodeFitHeightRobustly(this);
            }
        };

        // 重写配置方法
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            onConfigure?.apply(this, arguments);
            setTimeout(() => {
                manageInputs(this);
                manageOutputs(this);
                updateTypes(this);
                initializeModelSelector(this);
                ensureNWatcher(this);
                nodeFitHeightRobustly(this);
            }, 10);
        };
    },
});
