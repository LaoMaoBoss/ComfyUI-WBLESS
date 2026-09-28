/**
 * ToAPIs GPT Image 2 VIP 节点前端实现
 * 负责参考图动态输入端口管理、参数联动校验和右键快捷菜单
 */

import { app } from "../../../scripts/app.js";
import { nodeFitHeightRobustly } from "../util.js";

const _id = "ToAPIs GPT Image 2 VIP";
// 与后端 MAX_IMAGE_INPUTS 保持一致
const MAX_IMAGE_INPUTS = 10;

// 预设比例：与后端 PRESET_SIZES 保持一致（用于判断是否需要提示自定义比例）
const PRESET_SIZES = [
    "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "21:9", "9:21", "auto",
];

// 任意比例约束（与文档一致）
const MAX_CUSTOM_RATIO = 3.0;
const RATIO_PATTERN = /^(\d+)\s*:\s*(\d+)$/;

// 注册 ToAPIs GPT Image 2 VIP 节点
app.registerExtension({
    name: "wbless.node." + _id,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== _id) return;

        console.log(`[ToAPIs GPT Image 2 VIP] 前端扩展已加载`);

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            // 调用原始方法
            if (originalOnNodeCreated) {
                originalOnNodeCreated.apply(this, arguments);
            }

            this.title = "ToAPIs GPT Image 2 VIP";

            // 记录自定义状态（会随工作流序列化）
            this.toapis_config = {
                show_all_inputs: false,
            };

            // 初始化时管理参考图输入端口
            this.manageToapisImageInputs();

            setTimeout(() => {
                this.setupToapisCallbacks();
                this.validateToapisInputs();
            }, 100);

            nodeFitHeightRobustly(this);
        };

        /**
         * 获取动态参考图输入端口
         */
        nodeType.prototype.getToapisImageInputs = function () {
            return this.inputs?.filter(i => i.name && i.name.startsWith("image_")) || [];
        };

        /**
         * 管理参考图端口的动态增减：始终保持“已连接数量 + 1”个端口
         * 最多 MAX_IMAGE_INPUTS 个；手动展开全部端口时不自动回收
         */
        nodeType.prototype.manageToapisImageInputs = function () {
            const dynamicInputs = this.getToapisImageInputs();
            const connectedCount = dynamicInputs.reduce(
                (acc, input) => acc + (input.link !== null ? 1 : 0), 0
            );

            let desiredCount = this.toapis_config?.show_all_inputs
                ? MAX_IMAGE_INPUTS
                : Math.min(connectedCount + 1, MAX_IMAGE_INPUTS);

            desiredCount = Math.max(1, desiredCount);
            let currentCount = dynamicInputs.length;

            // 补齐缺少的端口
            while (currentCount < desiredCount) {
                this.addInput(`image_${currentCount + 1}`, "IMAGE");
                console.log(`[ToAPIs GPT Image 2 VIP] 新增参考图端口: image_${currentCount + 1}`);
                currentCount++;
            }

            // 回收尾部未连接的冗余端口
            while (currentCount > desiredCount && currentCount > 1) {
                const lastInput = this.inputs[this.inputs.length - 1];
                if (lastInput && lastInput.name.startsWith("image_") && lastInput.link === null) {
                    this.removeInput(this.inputs.length - 1);
                    console.log(`[ToAPIs GPT Image 2 VIP] 回收参考图端口: ${lastInput.name}`);
                    currentCount--;
                } else {
                    break;
                }
            }

            // 端口名称必须与后端 image_{i} 严格对应，
            // 后端按端口名收集参考图，所以这里不做重新编号，避免连线错位。
            console.log(
                `[ToAPIs GPT Image 2 VIP] 参考图端口: 已连接 ${connectedCount} 个 / 当前 ${currentCount} 个`
            );

            nodeFitHeightRobustly(this);
        };

        /**
         * 绑定控件回调，用于参数联动校验
         */
        nodeType.prototype.setupToapisCallbacks = function () {
            const watched = ["custom_size", "size", "resolution", "n", "poll_interval", "timeout"];

            watched.forEach(name => {
                const widget = this.widgets?.find(w => w.name === name);
                if (!widget || widget._wblessWrapped) return;

                const originalCallback = widget.callback;
                widget.callback = (value) => {
                    if (originalCallback) {
                        originalCallback.call(widget, value);
                    }
                    this.validateToapisInputs();
                };
                widget._wblessWrapped = true;
            });
        };

        /**
         * 参数校验：给出即时告警，避免运行时才失败
         */
        nodeType.prototype.validateToapisInputs = function () {
            const customSize = this.widgets?.find(w => w.name === "custom_size")?.value;
            const presetSize = this.widgets?.find(w => w.name === "size")?.value;

            const raw = (customSize || "").toString().trim();
            const effective = raw || (presetSize || "").toString().trim();

            if (raw) {
                const match = RATIO_PATTERN.exec(raw.replace("：", ":"));
                if (!match) {
                    console.warn(`[ToAPIs GPT Image 2 VIP] custom_size 格式非法: ${raw}，应为 宽:高（如 7:4）`);
                } else {
                    const width = parseInt(match[1], 10);
                    const height = parseInt(match[2], 10);
                    if (width <= 0 || height <= 0) {
                        console.warn(`[ToAPIs GPT Image 2 VIP] custom_size 宽高必须为正整数: ${raw}`);
                    } else {
                        const ratio = Math.max(width, height) / Math.min(width, height);
                        if (ratio > MAX_CUSTOM_RATIO + 1e-9) {
                            console.warn(
                                `[ToAPIs GPT Image 2 VIP] custom_size 宽高比 ${ratio.toFixed(2)}:1 超过 ${MAX_CUSTOM_RATIO}:1 上限: ${raw}`
                            );
                        } else if (width % 16 !== 0 || height % 16 !== 0) {
                            // 非硬性要求：服务端按 resolution 推导实际像素，这里只做提醒
                            console.info(
                                `[ToAPIs GPT Image 2 VIP] custom_size ${raw} 的宽高不是 16 的倍数，实际像素将由服务端按 resolution 推导`
                            );
                        }
                    }
                }
            } else if (effective && !PRESET_SIZES.includes(effective)) {
                console.warn(`[ToAPIs GPT Image 2 VIP] size 不在预设列表中: ${effective}`);
            }

            const n = this.widgets?.find(w => w.name === "n")?.value;
            if (typeof n === "number" && (n < 1 || n > 10)) {
                console.warn(`[ToAPIs GPT Image 2 VIP] n 应在 1-10 之间，当前: ${n}`);
            }

            const pollInterval = this.widgets?.find(w => w.name === "poll_interval")?.value;
            const timeout = this.widgets?.find(w => w.name === "timeout")?.value;
            if (typeof pollInterval === "number" && typeof timeout === "number" && pollInterval > timeout) {
                console.warn(`[ToAPIs GPT Image 2 VIP] 轮询间隔(${pollInterval}s) 大于总超时(${timeout}s)，可能一次都没轮询就超时`);
            }
        };

        // 连接变化时重新管理端口
        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
            if (originalOnConnectionsChange) {
                originalOnConnectionsChange.apply(this, arguments);
            }

            if (type === 1) {
                const input = this.inputs?.[index];
                if (input && input.name.startsWith("image_")) {
                    // 手动展开过全部端口时，取消一次连接也保持展开状态
                    if (!this.toapis_config?.show_all_inputs) {
                        setTimeout(() => this.manageToapisImageInputs(), 10);
                    }
                }
            }
        };

        // 加载已有工作流后恢复端口结构
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            if (originalOnConfigure) {
                originalOnConfigure.apply(this, arguments);
            }

            if (info?.toapis_config) {
                this.toapis_config = { ...this.toapis_config, ...info.toapis_config };
            }

            setTimeout(() => {
                this.manageToapisImageInputs();
                this.setupToapisCallbacks();
                this.validateToapisInputs();
            }, 100);
        };

        // 序列化自定义状态
        const originalOnSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (info) {
            if (originalOnSerialize) {
                originalOnSerialize.apply(this, arguments);
            }
            info.toapis_config = this.toapis_config;
        };

        // 右键菜单：常用操作
        const originalGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (_, options) {
            if (originalGetExtraMenuOptions) {
                originalGetExtraMenuOptions.apply(this, arguments);
            }

            options.push({
                content: "显示全部参考图输入端口",
                callback: () => {
                    this.toapis_config = this.toapis_config || {};
                    this.toapis_config.show_all_inputs = true;
                    this.manageToapisImageInputs();
                }
            });

            options.push({
                content: "收起多余的参考图输入端口",
                callback: () => {
                    this.toapis_config = this.toapis_config || {};
                    this.toapis_config.show_all_inputs = false;
                    this.manageToapisImageInputs();
                }
            });

            options.push({
                content: "重置为推荐设置",
                callback: () => {
                    const recommended = {
                        api_base: "https://toapis.com",
                        size: "1:1",
                        custom_size: "",
                        resolution: "1k",
                        quality: "medium",
                        background: "auto",
                        n: 1,
                        timeout: 600,
                        poll_interval: 5,
                    };

                    for (const [name, value] of Object.entries(recommended)) {
                        const widget = this.widgets?.find(w => w.name === name);
                        if (widget) {
                            widget.value = value;
                        }
                    }

                    this.validateToapisInputs();
                    console.log("[ToAPIs GPT Image 2 VIP] 已重置为推荐设置");
                }
            });

            options.push(null); // 分隔线

            options.push({
                content: "API 使用帮助",
                callback: () => {
                    const helpText = `🔑 ToAPIs GPT Image 2 VIP 使用帮助

1. API Key：
   • 访问 https://toapis.com/console/token 获取
   • 也可设置环境变量 TOAPIS_API_KEY，节点留空时自动读取

2. 接口地址（api_base）：
   • 国际站：https://toapis.com（默认）
   • 中国大陆：https://toapis.cn

3. 参考图（图生图）：
   • 接口只接受公开 http(s) URL，不支持 base64
   • 把本地图片连到 image_1 端口即可，节点会自动上传到
     ToAPIs /v1/uploads/images 换取 URL
   • 单个文件上限 10MB；PNG 超限会自动降级为 JPEG

4. 尺寸（size / custom_size）：
   • 预设：1:1 3:2 2:3 4:3 3:4 5:4 4:5 16:9 9:16 2:1 1:2 21:9 9:21
   • 任意比例填 custom_size，如 7:4、1:3（宽高比上限 3:1）
   • resolution 决定实际像素：1k / 2k / 4k（4K 长边最长 3840）

5. 其他：
   • quality：low 快速省钱 / medium 平衡 / high 最高精度
   • background：transparent 需要 PNG 输出才保留透明通道
   • 任务为异步执行，timeout 为轮询总超时（秒）`;

                    alert(helpText);
                }
            });

            options.push({
                content: "打开 ToAPIs 控制台",
                callback: () => {
                    const base = (this.widgets?.find(w => w.name === "api_base")?.value || "https://toapis.com").toString();
                    let consoleUrl = "https://toapis.com/console/token";
                    try {
                        const origin = new URL(base.includes("://") ? base : `https://${base}`).origin;
                        consoleUrl = `${origin}/console/token`;
                    } catch (e) {
                        // base 非法时回退到国际站
                    }
                    window.open(consoleUrl, "_blank");
                }
            });
        };
    }
});
