import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { TypeSlot, TypeSlotEvent, nodeFitHeight } from "../util.js";

const nodeId = "Get Global Variable";
const scopeType = "COZY_SCOPE";
const anyType = "*";
const passthroughPrefix = 'Input';

app.registerExtension({
    name: 'wbless.node.' + nodeId,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== nodeId) return;

        nodeType.prototype.updateTypes = function() {
            const passthrough_input = this.inputs?.find(i => i.name === passthroughPrefix);
            const passthrough_output = this.outputs?.find(o => o.name === 'Output');

            if (passthrough_input && passthrough_output) {
                const linkId = passthrough_input.link;
                if (linkId) {
                    const link = app.graph.links[linkId];
                    const originNode = app.graph.getNodeById(link.origin_id);
                    if (originNode) {
                        const originSlot = originNode.outputs[link.origin_slot];
                        if (originSlot) {
                            const type = originSlot.type;
                            passthrough_input.type = type;
                            passthrough_input.label = type;
                            passthrough_output.type = type;
                            passthrough_output.label = type;
                        }
                    }
                } else {
                    passthrough_input.type = anyType;
                    passthrough_input.label = passthroughPrefix;
                    passthrough_output.type = anyType;
                    passthrough_output.label = "Output";
                }
            }

            const widget = this.widgets.find(w => w.name === "variable_name");
            if (widget && this.updateOutputType) {
                this.updateOutputType(widget.value);
            }

            nodeFitHeight(this);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function() {
            onConfigure?.apply(this, arguments);
            setTimeout(() => this.updateTypes(), 10);
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (slotType, slot_idx, event, link_info, node_slot) {
            onConnectionsChange?.apply(this, arguments);
            this.updateTypes();
        };

        nodeType.prototype.updateVariableList = function(oldName, newName) {
            const widget = this.widgets.find(w => w.name === "variable_name");
            if (!widget) return;

            const setterNodes = app.graph._nodes.filter(node => node.type === "Set Global Variable");
            const validVariableNames = setterNodes.map(node => {
                const setterWidget = node.widgets.find(w => w.name === "variable_name");
                return setterWidget ? setterWidget.value : null;
            }).filter(Boolean);
            const validValues = validVariableNames.length > 0 ? [...new Set(validVariableNames)] : ["none"];
            
            const originalValue = widget.value;
            let didValueChange = false;

            if (oldName && newName && originalValue === oldName) {
                const otherSettersWithOldName = app.graph._nodes.filter(node =>
                    node.type === "Set Global Variable" &&
                    node.widgets.find(w => w.name === "variable_name")?.value === oldName
                );

                if (otherSettersWithOldName.length === 0) {
                    widget.value = newName;
                    didValueChange = true;
                }
            }
            
            let finalOptions = [...new Set(validVariableNames)];
            if (finalOptions.length === 0) {
                finalOptions.push("none");
            }
            widget.options.values = finalOptions;
            
            if (didValueChange && widget.callback) {
                widget.callback(widget.value);
            }
        };

        nodeType.prototype.updateOutputType = function(variableName) {
            const dataOutput = this.outputs.find(o => o.name === "variable data");
            if (!dataOutput) return;

            let newType = anyType;

            if (variableName && variableName !== "none") {
                const setterNode = app.graph._nodes.find(node =>
                    node.type === "Set Global Variable" &&
                    node.widgets.find(w => w.name === "variable_name")?.value === variableName
                );

                if (setterNode) {
                    const storeDataInput = setterNode.inputs?.find(i => i.name === 'variable data');
                    if (storeDataInput && storeDataInput.type) {
                        newType = storeDataInput.type;
                    }
                }
            }

            if (dataOutput.type !== newType) {
                dataOutput.type = newType;
                dataOutput.label = newType === anyType ? "variable data" : newType;
                this.setDirtyCanvas(true, true);
            }
        };

        nodeType.prototype.initialize = function(retries) {
            if (retries < 0) {
                console.error("WBLESS: Get node failed to initialize after multiple retries.");
                return;
            }

            this.updateVariableList(null, null);
            const widget = this.widgets.find(w => w.name === "variable_name");
            if (widget) {
                this.updateOutputType(widget.value);
            }

            const setterNodesExist = app.graph._nodes.some(n => n.type === "Set Global Variable");
            if (setterNodesExist && widget && widget.options.values.length <= 1 && (widget.options.values[0] === "none" || !widget.options.values.includes(widget.value))) {
                setTimeout(() => this.initialize(retries - 1), 250);
            }
        };

        const onAdded = nodeType.prototype.onAdded;
        nodeType.prototype.onAdded = function(graph) {
            onAdded?.apply(this, arguments);
            this.initialize(5);
        };

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);

            if (!this.outputs?.some(o => o.name === "Output")) this.addOutput("Output", anyType, { y: 0 });
            if (!this.inputs?.some(i => i.name === passthroughPrefix)) this.addInput(passthroughPrefix, anyType, { y: 0 });

            if (!this.outputs?.some(o => o.name === "variable data")) this.addOutput("variable data", anyType);
            if (!this.outputs?.some(o => o.name === "scope")) this.addOutput("scope", scopeType);
            if (!this.inputs?.some(i => i.name === "scope")) this.addInput("scope", scopeType);

            const widgetIndex = this.widgets.findIndex(w => w.name === "variable_name");
            if (widgetIndex !== -1) {
                const oldWidget = this.widgets[widgetIndex];
                
                this.widgets.splice(widgetIndex, 1);

                this.addWidget(
                    "combo",
                    "variable_name",
                    oldWidget.value,
                    (value) => { this.updateOutputType(value); },
                    { values: ["none"] }
                );

                const addedWidget = this.widgets.pop();
                this.widgets.splice(widgetIndex, 0, addedWidget);
            }
        };
    },
}); 