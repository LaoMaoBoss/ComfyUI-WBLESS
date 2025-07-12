import { app } from "../../../scripts/app.js"
import {
    TypeSlot, TypeSlotEvent, nodeFitHeight
}  from "../util.js"

const _id = "Set Global Variable";
const passthroughPrefix = 'Input';
const dataPrefix = 'variable data';
const _dynamic_type = "*";
const scopeType = "COZY_SCOPE";

app.registerExtension({
	name: 'wbless.node.' + _id,
	async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== _id) return;

        nodeType.prototype.updateDataType = function(newType) {
            const dataInput = this.inputs?.find(i => i.name === dataPrefix);
            if (dataInput && !dataInput.link && dataInput.type !== newType) {
                dataInput.type = newType;
                dataInput.label = newType === _dynamic_type ? dataPrefix : newType;
                nodeFitHeight(this);
            }
        };
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
                    passthrough_input.type = _dynamic_type;
                    passthrough_input.label = passthroughPrefix;
                    passthrough_output.type = _dynamic_type;
                    passthrough_output.label = "Output";
                }
            }

            const data_input = this.inputs?.find(i => i.name === dataPrefix);
            if (data_input) {
                const linkId = data_input.link;
                if (linkId) {
                    const link = app.graph.links[linkId];
                    const originNode = app.graph.getNodeById(link.origin_id);
                     if (originNode) {
                        const originSlot = originNode.outputs[link.origin_slot];
                        if (originSlot) {
                            const type = originSlot.type;
                            data_input.type = type;
                            data_input.label = type;

                            const variableName = this.widgets.find(w => w.name === "variable_name")?.value;
                            if (variableName) {
                                for (const node of app.graph._nodes) {
                                    if (node.id !== this.id && node.type === "Set Global Variable") {
                                        const otherWidget = node.widgets.find(w => w.name === "variable_name");
                                        if (otherWidget && otherWidget.value === variableName && node.updateDataType) {
                                            node.updateDataType(type);
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    let newType = _dynamic_type;
                    const variableName = this.widgets.find(w => w.name === "variable_name")?.value;

                    if (variableName) {
                        const sourceOfTruthNode = app.graph._nodes.find(node =>
                            node.type === "Set Global Variable" &&
                            node.widgets.find(w => w.name === "variable_name")?.value === variableName &&
                            node.inputs?.find(i => i.name === dataPrefix)?.link
                        );

                        if (sourceOfTruthNode) {
                            const sourceDataInput = sourceOfTruthNode.inputs.find(i => i.name === dataPrefix);
                            const sourceLink = app.graph.links[sourceDataInput.link];
                            const sourceOriginNode = app.graph.getNodeById(sourceLink.origin_id);
                            const sourceOriginSlot = sourceOriginNode.outputs[sourceLink.origin_slot];
                            newType = sourceOriginSlot.type;
                        }
                    }
                    
                    if (data_input.type !== newType) {
                        data_input.type = newType;
                        data_input.label = newType === _dynamic_type ? dataPrefix : newType;
                    }

                    if (variableName) {
                        for (const node of app.graph._nodes) {
                            if (node.id !== this.id && node.type === "Set Global Variable") {
                                const otherWidget = node.widgets.find(w => w.name === "variable_name");
                                if (otherWidget && otherWidget.value === variableName && node.updateDataType) {
                                    node.updateDataType(newType);
                                }
                            }
                        }
                    }
                }
            }
            nodeFitHeight(this);
        };
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            onConfigure?.apply(this, arguments);

            const widget = this.widgets.find(w => w.name === "variable_name");
            if (widget) {
                if (!this.properties) this.properties = {};
                this.properties.previousName = widget.value;
            }

            setTimeout(() => this.updateTypes(), 10);
        };
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = async function () {
            await onNodeCreated?.apply(this, arguments);

            if (!this.properties) this.properties = {};
            const widget = this.widgets.find(w => w.name === "variable_name");
            this.properties.previousName = widget ? widget.value : undefined;
            if (!this.inputs?.some(i => i.name === passthroughPrefix)) this.addInput(passthroughPrefix, _dynamic_type);
            if (!this.inputs?.some(i => i.name === dataPrefix)) this.addInput(dataPrefix, _dynamic_type);
            if (!this.inputs?.some(i => i.name === "scope")) this.addInput("scope", scopeType);
            if (!this.outputs?.some(o => o.name === "Output")) this.addOutput("Output", _dynamic_type);
            if (!this.outputs?.some(o => o.name === "scope")) this.addOutput("scope", scopeType);
            if (widget) {
                const originalCallback = widget.callback;
                widget.callback = (...args) => {
                    originalCallback?.apply(this, args);
                    const newName = widget.value;
                    const oldName = this.properties.previousName;
                    if (oldName !== newName) {
                        this.broadcastUpdates(oldName, newName);
                    }
                    
                    const dataInput = this.inputs?.find(i => i.name === dataPrefix);
                    if (dataInput && !dataInput.link) {
                        let newType = _dynamic_type; 
                        const otherSetter = app.graph._nodes.find(node =>
                            node.id !== this.id &&
                            node.type === "Set Global Variable" &&
                            node.widgets.find(w => w.name === "variable_name")?.value === newName
                        );

                        if (otherSetter) {
                            const otherDataInput = otherSetter.inputs?.find(i => i.name === dataPrefix);
                            if (otherDataInput) newType = otherDataInput.type;
                        }

                        if (dataInput.type !== newType) {
                            dataInput.type = newType;
                            dataInput.label = newType === _dynamic_type ? dataPrefix : newType;
                            nodeFitHeight(this);
                        }
                    }
                    const currentType = dataInput ? dataInput.type : _dynamic_type;
                    if (newName) {
                        for (const node of app.graph._nodes) {
                            if (node.id !== this.id && node.type === "Set Global Variable") {
                                const otherWidget = node.widgets.find(w => w.name === "variable_name");
                                if (otherWidget && otherWidget.value === newName && node.updateDataType) {
                                    node.updateDataType(currentType);
                                }
                            }
                        }
                    }

                    this.properties.previousName = newName;
                };
            }
        };

        nodeType.prototype.broadcastUpdates = function(oldName, newName) {
            for (const node of app.graph._nodes) {
                if (node.type === "Get Global Variable") {
                    if (node.updateVariableList) {
                        node.updateVariableList(oldName, newName);
                    }
                    const widget = node.widgets.find(w => w.name === "variable_name");
                    if (widget && widget.value === oldName && node.updateOutputType) {
                        setTimeout(() => node.updateOutputType(oldName), 0);
                    }
                }
                else if (node.type === "Set Global Variable" && node.id !== this.id) {
                    const widget = node.widgets.find(w => w.name === "variable_name");
                    if (widget && widget.value === oldName && node.updateTypes) {
                        node.updateTypes();
                    }
                }
            }
        };
        const onRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function() {
            onRemoved?.apply(this, arguments);
            const oldName = this.properties.previousName;
            setTimeout(() => {
                for (const node of app.graph._nodes) {
                    if (node.type === "Get Global Variable" && node.updateVariableList) {
                        node.updateVariableList(oldName, null);
                    }
                }
            }, 0);
        };
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (slotType, slot_idx, event, link_info, node_slot) {
            const me = onConnectionsChange?.apply(this, arguments);
            this.updateTypes();
            if (node_slot && node_slot.name === dataPrefix) {
                const variableName = this.widgets.find(w => w.name === "variable_name")?.value;
                if (variableName) {
                    for (const node of app.graph._nodes) {
                        if (node.type === "Get Global Variable") {
                            const getterWidget = node.widgets.find(w => w.name === "variable_name");
                            if (getterWidget && getterWidget.value === variableName && node.updateOutputType) {
                                node.updateOutputType(variableName);
                            }
                        }
                    }
                }
            }
            nodeFitHeight(this);
            return me;
        }
	}
})
