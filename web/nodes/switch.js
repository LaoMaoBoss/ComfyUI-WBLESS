import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";

const _id = "Switch";
const _type = "*";

function getDynamicInputs(node) {
    return node.inputs?.filter(i => i.name.startsWith("Input_")) || [];
}

function manageInputs(node) {
    const dynamicInputs = getDynamicInputs(node);
    const connectedCount = dynamicInputs.reduce((acc, input) => acc + (input.link !== null ? 1 : 0), 0);
    const desiredCount = connectedCount + 1;
    let currentCount = dynamicInputs.length;

    while (currentCount < desiredCount) {
        node.addInput(`Input_${currentCount + 1}`, _type);
        currentCount++;
    }

    while (currentCount > desiredCount) {
        const lastInput = node.inputs[node.inputs.length - 1];
        if (lastInput && lastInput.name.startsWith("Input_") && lastInput.link === null) {
            node.removeInput(node.inputs.length - 1);
            currentCount--;
        } else {
            break;
        }
    }

    if (getDynamicInputs(node).length === 0) {
        node.addInput("Input_1", _type);
    }
    
    let dynamicInputIndex = 1;
    node.inputs.forEach(input => {
        if (input.name.startsWith("Input_")) {
            input.name = `Input_${dynamicInputIndex}`;
            input.label = input.name;
            dynamicInputIndex++;
        }
    });

    const pathWidget = node.widgets.find(w => w.name === "Path");
    if (pathWidget) {
        const finalInputCount = getDynamicInputs(node).length;
        pathWidget.options.max = finalInputCount > 0 ? finalInputCount : 1;
        pathWidget.value = Math.min(pathWidget.value, pathWidget.options.max);
    }
}

function updateTypes(node) {
    const dynamicInputs = getDynamicInputs(node);
    const outputPort = node.outputs.find(o => o.name === "output");

    if (!outputPort) return;

    let newType = _type;

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

    dynamicInputs.forEach(input => {
        if (input.type !== newType) {
            input.type = newType;
        }
    });

    if (outputPort.type !== newType) {
        outputPort.type = newType;
        outputPort.label = newType;
    }
}

app.registerExtension({
    name: "wbless.node." + _id,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== _id) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            manageInputs(this);
            updateTypes(this);

            const pathWidget = this.widgets.find(w => w.name === "Path");
            if (pathWidget) {
                const originalCallback = pathWidget.callback;
                pathWidget.callback = (value, ...args) => {
                    if (originalCallback) {
                        return originalCallback.call(pathWidget, value, ...args);
                    }
                };
            }
            nodeFitHeightRobustly(this);
        };
        
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info, slot) {
            onConnectionsChange?.apply(this, arguments);
            manageInputs(this);
            updateTypes(this);
            nodeFitHeightRobustly(this);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            onConfigure?.apply(this, arguments);
            setTimeout(() => {
                manageInputs(this);
                updateTypes(this);
                nodeFitHeightRobustly(this);
            }, 10);
        };
    },
}); 