import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";

const _id = "Inversed Switch";
const _type = "*";
const MIN_OUTPUTS = 1;

function manageOutputs(node) {
    const connectedPortCount = node.outputs.reduce((acc, output) => {
        return acc + (output.links && output.links.length > 0 ? 1 : 0);
    }, 0);

    const desiredCount = Math.max(MIN_OUTPUTS, connectedPortCount + 1);
    let currentCount = node.outputs.length;

    while (currentCount < desiredCount) {
        node.addOutput(`Output_${currentCount + 1}`, _type);
        currentCount++;
    }

    while (currentCount > desiredCount) {
        const lastOutput = node.outputs[node.outputs.length - 1];
        if (lastOutput && (!lastOutput.links || lastOutput.links.length === 0)) {
            node.removeOutput(node.outputs.length - 1);
            currentCount--;
        } else {
            break;
        }
    }

    node.outputs.forEach((output, i) => {
        const newName = `Output_${i + 1}`;
        if (output.name !== newName) {
            output.name = newName;
            output.label = newName;
        }
    });
}

function updatePathWidget(node) {
    const pathWidget = node.widgets.find(w => w.name === "Path");
    if (pathWidget) {
        const outputCount = node.outputs.length;
        pathWidget.options.max = outputCount > 0 ? outputCount : 1;
        pathWidget.value = Math.min(pathWidget.value, pathWidget.options.max);
    }
}

function updateTypes(node) {
    const inputPort = node.inputs.find(i => i.name === "Input");
    let newType = _type;

    if (inputPort && inputPort.link) {
        const link = app.graph.links[inputPort.link];
        if (link) {
            const originNode = app.graph.getNodeById(link.origin_id);
            if (originNode && originNode.outputs && originNode.outputs[link.origin_slot]) {
                newType = originNode.outputs[link.origin_slot].type;
            }
        }
    }

    if (inputPort) {
        inputPort.type = newType;
        inputPort.label = newType === _type ? "Input" : newType;
    }

    node.outputs?.forEach(output => {
        output.type = newType;
        output.label = output.name;
    });
}

app.registerExtension({
    name: "wbless.node." + _id,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== _id) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            manageOutputs(this);
            updateTypes(this);
            updatePathWidget(this);
            nodeFitHeightRobustly(this);
        };
        
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info, slot) {
            onConnectionsChange?.apply(this, arguments);

            if (type === 1) {
                if (this.inputs[index]?.name === 'Input') {
                    updateTypes(this);
                }
            } else {
                manageOutputs(this);
                updateTypes(this);
                updatePathWidget(this);
            }
            
            nodeFitHeightRobustly(this);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            onConfigure?.apply(this, arguments);
            setTimeout(() => {
                manageOutputs(this);
                updateTypes(this);
                updatePathWidget(this);
                nodeFitHeightRobustly(this);
            }, 10);
        };
    },
});