import { app } from "../../scripts/app.js"

export const TypeSlot = {
    Input: 1,
    Output: 2,
};

export const TypeSlotEvent = {
    Connect: true,
    Disconnect: false,
};

export function nodeFitHeight(node) {
    const size_old = node.size;
    node.computeSize();
    node.setSize([Math.max(size_old[0], node.size[0]), node.size[1]]);
    node.setDirtyCanvas(!0, !1);
    app.graph.setDirtyCanvas(!0, !1);
}

export function nodeFitHeightRobustly(node) {
    if (!node) return;
    const size_old = node.size;
    const new_size = node.computeSize();
    node.setSize([Math.max(size_old[0], new_size[0]), new_size[1]]);
    node.setDirtyCanvas(!0, !1);
    app.graph.setDirtyCanvas(!0, !1);
}

export async function nodeAddDynamic(nodeType, prefix, dynamic_type='*') {
    const onNodeCreated = nodeType.prototype.onNodeCreated
    nodeType.prototype.onNodeCreated = async function () {
        const me = await onNodeCreated?.apply(this, arguments);

        if (this.inputs.length == 0 || this.inputs[this.inputs.length-1].name != prefix) {
            this.addInput(prefix, dynamic_type);
        }
        return me;
    }

    function slot_name(slot) {
        return slot.name.split('_');
    }

    const onConnectionsChange = nodeType.prototype.onConnectionsChange
    nodeType.prototype.onConnectionsChange = async function (slotType, slot_idx, event, link_info, node_slot) {
        const me = onConnectionsChange?.apply(this, arguments);
        const slot_parts = slot_name(node_slot);
        if ((node_slot.type === dynamic_type || slot_parts.length > 1) && slotType === TypeSlot.Input && link_info !== null) {
            const fromNode = this.graph._nodes.find(
                (otherNode) => otherNode.id == link_info.origin_id
            )
            const parent_slot = fromNode.outputs[link_info.origin_slot];
            if (event === TypeSlotEvent.Connect) {
                node_slot.type = parent_slot.type;
                node_slot.name = `0_${parent_slot.name}`;
            } else {
                this.removeInput(slot_idx);
                node_slot.type = dynamic_type;
                node_slot.name = prefix;
                node_slot.link = null;
            }

            let idx = 0;
            let offset = 0;
            while (idx < this.inputs.length) {
                const parts = slot_name(this.inputs[idx]);
                if (parts.length > 1) {
                    const name = parts.slice(1).join('');
                    this.inputs[idx].name = `${offset}_${name}`;
                    offset += 1;
                }
                idx += 1;
            }
        }
        let last = this.inputs[this.inputs.length-1];
        if (last.type != dynamic_type || last.name != prefix) {
            this.addInput(prefix, dynamic_type);
        }
        nodeFitHeight(this);
        return me;
    }
}

export function nodeVirtualLinkRoot(node) {
    while (node) {
        const { isVirtualNode, findSetter } = node;

        if (!isVirtualNode || !findSetter) break;
        const nextNode = findSetter(node.graph);

        if (!nextNode) break;
        node = nextNode;
    }
    return node;
}

function nodeVirtualLinkChild(node) {
    while (node) {
        const { isVirtualNode, findGetter } = node;

        if (!isVirtualNode || !findGetter) break;
        const nextNode = findGetter(node.graph);

        if (!nextNode) break;
        node = nextNode;
    }
    return node;
}

export function nodeInputsClear(node, stop = 0) {
    while (node.inputs?.length > stop) {
        node.removeInput(node.inputs.length - 1);
    }
}

export function nodeOutputsClear(node, stop = 0) {
    while (node.outputs?.length > stop) {
        node.removeOutput(node.outputs.length - 1);
    }
}
