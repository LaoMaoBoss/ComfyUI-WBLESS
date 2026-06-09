/**
 * Qwen Chat 节点前端实现
 * 支持动态图像输入端口
 */

import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";

const NODE_NAME = "Qwen Chat";
const MAX_IMAGE_INPUTS = 10;

app.registerExtension({
    name: "WBLESS.QwenChat",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            originalOnNodeCreated?.apply(this, arguments);
            this.title = NODE_NAME;
            this.manageImageInputs();
            nodeFitHeightRobustly(this);
        };

        nodeType.prototype.getDynamicImageInputs = function () {
            return this.inputs?.filter((input) => input.name.startsWith("image_")) || [];
        };

        nodeType.prototype.manageImageInputs = function () {
            const dynamicInputs = this.getDynamicImageInputs();
            const connectedCount = dynamicInputs.reduce(
                (acc, input) => acc + (input.link !== null ? 1 : 0),
                0
            );
            const desiredCount = Math.min(connectedCount + 1, MAX_IMAGE_INPUTS);
            let currentCount = dynamicInputs.length;

            while (currentCount < desiredCount) {
                this.addInput(`image_${currentCount + 1}`, "IMAGE");
                currentCount++;
            }

            while (currentCount > desiredCount && currentCount > 1) {
                const lastInput = this.inputs[this.inputs.length - 1];
                if (lastInput?.name.startsWith("image_") && lastInput.link === null) {
                    this.removeInput(this.inputs.length - 1);
                    currentCount--;
                } else {
                    break;
                }
            }

            if (this.getDynamicImageInputs().length === 0) {
                this.addInput("image_1", "IMAGE");
            }

            let imageInputIndex = 1;
            this.inputs.forEach((input) => {
                if (input.name.startsWith("image_")) {
                    input.name = `image_${imageInputIndex}`;
                    input.label = input.name;
                    imageInputIndex++;
                }
            });

            nodeFitHeightRobustly(this);
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
            originalOnConnectionsChange?.apply(this, arguments);

            if (type === 1) {
                const input = this.inputs[index];
                if (input?.name.startsWith("image_")) {
                    setTimeout(() => {
                        this.manageImageInputs();
                    }, 10);
                }
            }
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            originalOnConfigure?.apply(this, arguments);
            setTimeout(() => {
                this.manageImageInputs();
            }, 100);
        };

        const originalGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (_, options) {
            originalGetExtraMenuOptions?.apply(this, arguments);

            options.push({
                content: "显示所有图像输入",
                callback: () => {
                    const currentCount = this.getDynamicImageInputs().length;
                    for (let i = currentCount; i < MAX_IMAGE_INPUTS; i++) {
                        this.addInput(`image_${i + 1}`, "IMAGE");
                    }
                    this.manageImageInputs();
                },
            });

            options.push({
                content: "重新管理图像输入端口",
                callback: () => {
                    this.manageImageInputs();
                },
            });
        };
    },
});
