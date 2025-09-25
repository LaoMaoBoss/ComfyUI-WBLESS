/**
 * 预览窗口功能模块
 * 包含文本预览画布的创建、绘制和相关工具函数
 */
import { app } from "../../scripts/app.js"

/**
 * 创建预览画布元素
 * @param {number} width - 画布宽度
 * @param {number} height - 画布高度
 * @returns {HTMLCanvasElement} 创建的画布元素
 */
export function createPreviewCanvas(width = 200, height = 150) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.style.border = '1px solid #666';
    canvas.style.borderRadius = '4px';
    canvas.style.background = '#222';
    canvas.style.display = 'block';
    canvas.style.margin = '5px 0';
    
    // 优化：设置willReadFrequently属性，提高频繁读取性能
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    
    return canvas;
}

/**
 * 清除画布并绘制默认背景
 * @param {HTMLCanvasElement} canvas - 目标画布
 */
export function clearPreviewCanvas(canvas) {
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#222';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 绘制网格背景
    ctx.strokeStyle = '#444';
    ctx.lineWidth = 1;
    
    // 水平线
    for (let y = 0; y <= canvas.height; y += 20) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
    }
    
    // 垂直线
    for (let x = 0; x <= canvas.width; x += 20) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
    }
}

/**
 * 测量所有文本块的实际尺寸
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {Array} textBlocks - 文本块数组
 * @returns {Object} 包含所有文本块测量结果和边界框的对象
 */
function measureAllTextBlocks(ctx, textBlocks, overlaySettings = {}) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const blockMeasurements = [];
    
    let currentY = 20; // 初始Y位置
    let currentX = 20; // 初始X位置
    
    // 先分组文本块（按newline分组）
    const textGroups = [];
    let currentGroup = [];
    
    for (let i = 0; i < textBlocks.length; i++) {
        const block = textBlocks[i];
        if (!block || !block.text) continue;
        
        // 如果当前块设置了newline且不是第一个块，开始新组
        if (block.newline && currentGroup.length > 0) {
            textGroups.push(currentGroup);
            currentGroup = [];
        }
        
        currentGroup.push({block, index: i});
    }
    
    // 添加最后一组
    if (currentGroup.length > 0) {
        textGroups.push(currentGroup);
    }
    
    // 逐组测量文本
    for (let groupIndex = 0; groupIndex < textGroups.length; groupIndex++) {
        const group = textGroups[groupIndex];
        let groupStartX = currentX;
        let groupMaxHeight = 0;
        let groupMaxFontSize = 0; // 记录当前组的最大字体大小，用于基线对齐
        
        // 预览窗口特殊处理：先计算当前行的总宽度，用于内部对齐
        const justify = overlaySettings.justify || "center";
        let totalGroupWidth = 0;
        
        // 第一遍：计算当前组的总宽度和最大字体大小
        for (const {block} of group) {
            const originalFontSize = block.font_size || 50;
            const fontFamily = block.font_family || 'Arial';
            let processedText = processTextCase(block.text || '', block.text_case);
            
            // 检查是否启用自动换行
            if (block.auto_newline && block.auto_newline_width && block.auto_newline_width > 0) {
                const originalText = processedText;
                processedText = wrapTextForPreview(ctx, processedText, fontFamily, originalFontSize, block.auto_newline_width, block.letter_spacing || 0);
                
                // 添加调试信息
                if (originalText !== processedText) {
                    console.log('[WBLESS] Auto-wrap applied in preview (group width calc):');
                    console.log('  Original:', originalText);
                    console.log('  Wrapped:', processedText);
                    console.log('  Width limit:', block.auto_newline_width);
                    console.log('  Lines count:', processedText.split('\n').length);
                }
            }
            
            // 临时设置字体来测量
            const savedFont = ctx.font;
            ctx.font = `${originalFontSize}px ${fontFamily}`;
            
            // 处理多行文本的宽度测量
            const lines = processedText.split('\n');
            let maxLineWidth = 0;
            
            for (const line of lines) {
                const textMetrics = ctx.measureText(line);
                let lineWidth = textMetrics.width;
                
                if (block.letter_spacing && block.letter_spacing !== 0 && line.length > 1) {
                    lineWidth += (line.length - 1) * block.letter_spacing;
                }
                
                maxLineWidth = Math.max(maxLineWidth, lineWidth);
            }
            
            ctx.font = savedFont;
            let textWidth = maxLineWidth;
            
            totalGroupWidth += textWidth + (block.horizontal_spacing || 0);
            groupMaxFontSize = Math.max(groupMaxFontSize, originalFontSize); // 记录最大字体大小
        }
        
        // 第二遍：创建测量结果，使用统一的基线
        for (let itemIndex = 0; itemIndex < group.length; itemIndex++) {
            const {block, index} = group[itemIndex];
            
            // 获取原始字体大小
            const originalFontSize = block.font_size || 50;
            const fontFamily = block.font_family || 'Arial';
            
            // 应用文本样式进行测量
            let processedText = processTextCase(block.text || '', block.text_case);
            
            // 检查是否启用自动换行
            if (block.auto_newline && block.auto_newline_width && block.auto_newline_width > 0) {
                const originalText = processedText;
                processedText = wrapTextForPreview(ctx, processedText, fontFamily, originalFontSize, block.auto_newline_width, block.letter_spacing || 0);
                
                // 添加调试信息
                if (originalText !== processedText) {
                    console.log('[WBLESS] Auto-wrap applied in preview (measurement):');
                    console.log('  Original:', originalText);
                    console.log('  Wrapped:', processedText);
                    console.log('  Width limit:', block.auto_newline_width);
                    console.log('  Lines count:', processedText.split('\n').length);
                }
            }
            
            ctx.font = `${originalFontSize}px ${fontFamily}`;
            
            // 处理多行文本的尺寸测量
            const lines = processedText.split('\n');
            let maxLineWidth = 0;
            let totalHeight = 0;
            
            for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
                const line = lines[lineIndex];
                const textMetrics = ctx.measureText(line);
                let lineWidth = textMetrics.width;
                
                // 计算字间距对宽度的影响
                if (block.letter_spacing && block.letter_spacing !== 0 && line.length > 1) {
                    lineWidth += (line.length - 1) * block.letter_spacing;
                }
                
                maxLineWidth = Math.max(maxLineWidth, lineWidth);
            }
            
            // 计算总高度（考虑行间距）
            const baseLineHeight = originalFontSize * 1.2; // 基础行高
            const lineSpacingForMeasurement = overlaySettings.line_spacing || 0; // 获取行间距
            const actualLineHeight = baseLineHeight + lineSpacingForMeasurement;
            totalHeight = lines.length > 0 ? ((lines.length - 1) * actualLineHeight + baseLineHeight) : 0;
            
            const blockWidth = maxLineWidth + (block.horizontal_spacing || 0);
            const blockHeight = totalHeight + (block.vertical_spacing || 0);
            
            // 记录这个文本块的位置和尺寸
            const measurement = {
                x: currentX,
                y: currentY,
                width: blockWidth,
                height: blockHeight,
                originalFontSize,
                text: processedText,
                block: block,
                groupWidth: totalGroupWidth, // 添加组宽度信息，用于后续对齐计算
                groupIndex: groupIndex,
                groupMaxFontSize: groupMaxFontSize // 添加组最大字体大小，用于基线对齐
            };
            
            blockMeasurements.push(measurement);
            
            // 更新边界框
            minX = Math.min(minX, currentX);
            minY = Math.min(minY, currentY);
            maxX = Math.max(maxX, currentX + blockWidth);
            maxY = Math.max(maxY, currentY + blockHeight);
            
            // 更新当前位置
            currentX += blockWidth;
            groupMaxHeight = Math.max(groupMaxHeight, blockHeight);
        }
        
        // 换行（应用行间距）
        const lineSpacing = overlaySettings.line_spacing || 0;
        currentY += groupMaxHeight + lineSpacing;
        currentX = groupStartX;
    }
    
    return {
        blocks: blockMeasurements,
        bounds: {
            minX: minX === Infinity ? 0 : minX,
            minY: minY === Infinity ? 0 : minY,
            maxX: maxX === -Infinity ? 0 : maxX,
            maxY: maxY === -Infinity ? 0 : maxY,
            width: (maxX === -Infinity || minX === Infinity) ? 0 : maxX - minX,
            height: (maxY === -Infinity || minY === Infinity) ? 0 : maxY - minY
        }
    };
}

/**
 * 计算全局缩放比例，确保所有文本都能适应画布
 * @param {HTMLCanvasElement} canvas - 目标画布
 * @param {Object} textMeasurements - 文本测量结果
 * @returns {number} 全局缩放比例
 */
function calculateGlobalScale(canvas, textMeasurements) {
    const { bounds } = textMeasurements;
    
    // 如果没有文本，返回默认缩放
    if (bounds.width === 0 || bounds.height === 0) {
        return 0.5;
    }
    
    // 计算画布可用空间（留出边距）
    const margin = 20;
    const availableWidth = canvas.width - margin * 2;
    const availableHeight = canvas.height - margin * 2;
    
    // 计算宽度和高度的缩放比例
    const scaleX = availableWidth / bounds.width;
    const scaleY = availableHeight / bounds.height;
    
    // 使用较小的缩放比例，确保文本完全适应
    const scale = Math.min(scaleX, scaleY);
    
    // 限制缩放范围，避免过小或过大
    return Math.max(0.1, Math.min(2.0, scale));
}

/**
 * 处理文本大小写转换
 * @param {string} text - 原始文本
 * @param {string} textCase - 大小写类型
 * @returns {string} 处理后的文本
 */
function processTextCase(text, textCase) {
    if (!text || !textCase || textCase === 'normal') return text;
    
    switch (textCase) {
        case 'uppercase': return text.toUpperCase();
        case 'lowercase': return text.toLowerCase();
        case 'capitalize': return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
        case 'title': return text.replace(/\w\S*/g, (txt) => 
            txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase());
        default: return text;
    }
}

/**
 * 为预览系统实现文本自动换行（在最大宽度处直接换行，不考虑单词边界）
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {string} text - 要换行的文本
 * @param {string} fontFamily - 字体家族
 * @param {number} fontSize - 字体大小
 * @param {number} maxWidth - 最大宽度（像素）
 * @param {number} letterSpacing - 字间距
 * @returns {string} 换行后的文本（用\n分隔）
 */
function wrapTextForPreview(ctx, text, fontFamily, fontSize, maxWidth, letterSpacing = 0) {
    if (!text || maxWidth <= 0) {
        return text;
    }
    
    // 调试信息
    if (letterSpacing && letterSpacing !== 0) {
        console.log('[WBLESS] wrapTextForPreview with letter spacing:');
        console.log('  Letter spacing:', letterSpacing);
        console.log('  Max width:', maxWidth);
        console.log('  Font size:', fontSize);
    }
    
    // 设置字体用于测量
    const savedFont = ctx.font;
    ctx.font = `${fontSize}px ${fontFamily}`;
    
    // 将文本按现有的换行符分割
    const paragraphs = text.split('\n');
    const wrappedParagraphs = [];
    
    for (const paragraph of paragraphs) {
        if (!paragraph.trim()) {
            wrappedParagraphs.push("");
            continue;
        }
        
        const wrappedLines = [];
        let currentLine = "";
        
        // 逐字符处理，不考虑单词边界
        for (const char of paragraph) {
            // 计算添加这个字符后的行宽
            const testLine = currentLine + char;
            
            // 计算测试行的实际宽度（考虑字间距）
            let lineWidth;
            if (letterSpacing === 0) {
                lineWidth = ctx.measureText(testLine).width;
            } else {
                lineWidth = 0;
                for (let i = 0; i < testLine.length; i++) {
                    lineWidth += ctx.measureText(testLine[i]).width;
                    if (i < testLine.length - 1) {  // 最后一个字符后不加间距
                        lineWidth += letterSpacing;
                    }
                }
            }
            
            // 如果测试行宽度超过限制且当前行不为空，开始新行
            if (lineWidth > maxWidth && currentLine) {
                wrappedLines.push(currentLine);
                currentLine = char;
            } else {
                currentLine = testLine;
            }
        }
        
        // 添加最后一行
        if (currentLine) {
            wrappedLines.push(currentLine);
        }
        
        wrappedParagraphs.push(...wrappedLines);
    }
    
    // 恢复字体设置
    ctx.font = savedFont;
    
    return wrappedParagraphs.join('\n');
}

/**
 * 使用全局缩放绘制所有文本块
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {Object} textMeasurements - 文本测量结果
 * @param {number} globalScale - 全局缩放比例
 * @param {HTMLCanvasElement} canvas - 画布
 * @param {boolean} debugMode - 调试模式
 */
function renderScaledTextBlocks(ctx, textMeasurements, globalScale, canvas, debugMode, overlaySettings = {}) {
    const { blocks, bounds } = textMeasurements;
    
    // 预览窗口优化：让文本充满整个预览窗口，justify控制行内对齐
    const scaledWidth = bounds.width * globalScale;
    const scaledHeight = bounds.height * globalScale;
    
    // 预览窗口中，我们总是让文本组合居中显示，充满预览窗口
    const baseOffsetX = (canvas.width - scaledWidth) / 2 - bounds.minX * globalScale;
    const baseOffsetY = (canvas.height - scaledHeight) / 2 - bounds.minY * globalScale;
    
    // 获取设置，用于控制每行内部的文字对齐和行间距
    const justify = overlaySettings.justify || "center";
    const lineSpacing = (overlaySettings.line_spacing || 0) * globalScale; // 应用缩放
    
    // 按组分组文本块，用于行内对齐处理
    const blocksByGroup = {};
    for (const measurement of blocks) {
        const groupIndex = measurement.groupIndex || 0;
        if (!blocksByGroup[groupIndex]) {
            blocksByGroup[groupIndex] = [];
        }
        blocksByGroup[groupIndex].push(measurement);
    }
    
    // 绘制每个文本块
    for (const measurement of blocks) {
        const { x, y, originalFontSize, text, block, groupWidth, groupIndex, groupMaxFontSize } = measurement;
        
        // 计算当前组的行内对齐偏移
        let lineAlignOffset = 0;
        if (groupWidth && justify !== "left") {
            const currentGroup = blocksByGroup[groupIndex || 0];
            const scaledGroupWidth = groupWidth * globalScale;
            const availableWidth = canvas.width - 40; // 预留左右各20px边距
            
            if (scaledGroupWidth < availableWidth) {
                if (justify === "center") {
                    // 当前行在预览窗口中居中显示
                    lineAlignOffset = (availableWidth - scaledGroupWidth) / 2;
                } else if (justify === "right") {
                    // 当前行在预览窗口中右对齐
                    lineAlignOffset = availableWidth - scaledGroupWidth;
                }
            }
        }
        
        // 应用全局缩放和行内对齐偏移
        const scaledX = x * globalScale + baseOffsetX + lineAlignOffset;
        const scaledY = y * globalScale + baseOffsetY;
        const scaledFontSize = Math.max(6, originalFontSize * globalScale);
        
        // 设置文本样式
        const fontFamily = block.font_family || 'Arial';
        let fontWeight = 'normal';
        
        // 处理字重（不包括bold参数，因为bold使用多次绘制模拟）
        if (block.font_weight && block.font_weight !== 'Regular') {
            const weightMap = {
                'Thin': '100', 'ExtraLight': '200', 'UltraLight': '200', 'Light': '300',
                'Regular': '400', 'Normal': '400', 'Medium': '500', 'SemiBold': '600', 
                'DemiBold': '600', 'Bold': '700', 'ExtraBold': '800', 'UltraBold': '800', 
                'Black': '900', 'Heavy': '900'
            };
            fontWeight = weightMap[block.font_weight] || '400';
        }
        // 注意：不再使用CSS font-weight处理bold参数，改用多次绘制模拟
        
        // 设置字体样式
        let fontStyle = 'normal';
        if (block.italic) {
            fontStyle = 'italic';
        }
        
        ctx.font = `${fontStyle} ${fontWeight} ${scaledFontSize}px ${fontFamily}`;
        
        // 设置颜色和透明度
        const color = getColorValue(block.font_color, block.font_color_hex);
        const opacity = block.opacity !== undefined ? block.opacity : 1.0;
        ctx.fillStyle = color;
        ctx.globalAlpha = opacity;
        
        if (debugMode) {
            console.log(`[WBLESS] Block color: font_color="${block.font_color}", font_color_hex="${block.font_color_hex}" -> "${color}"`);
        }
        
        // 计算垂直对齐偏移（上标/下标）
        let verticalOffset = 0;
        let verticalScale = 1;
        if (block.vertical_align === 'superscript') {
            verticalOffset = -scaledFontSize * 0.3; // 上移30%
            verticalScale = 0.7; // 缩小到70%
        } else if (block.vertical_align === 'subscript') {
            verticalOffset = scaledFontSize * 0.2; // 下移20%
            verticalScale = 0.7; // 缩小到70%
        }
        
        // 应用垂直对齐的字体大小
        const adjustedFontSize = scaledFontSize * verticalScale;
        if (verticalScale !== 1) {
            ctx.font = `${fontStyle} ${fontWeight} ${adjustedFontSize}px ${fontFamily}`;
        }
        
        // 计算当前实际使用的字体大小（用于bold偏移计算）
        const currentFontSize = verticalScale !== 1 ? adjustedFontSize : scaledFontSize;
        
        // 计算基线对齐的Y坐标
        // 使用组内最大字体大小作为基线参考，确保同一行中所有文本共享相同的基线
        const scaledGroupMaxFontSize = (groupMaxFontSize || originalFontSize) * globalScale;
        const baselineY = scaledY + scaledGroupMaxFontSize * 0.8; // 基于组内最大字体的基线
        const finalY = baselineY + verticalOffset;
        
        // 应用旋转（如果有）
        const rotationAngle = (block.rotation_angle || 0) * Math.PI / 180; // 转换为弧度
        if (rotationAngle !== 0) {
            ctx.save();
            
            // 根据rotation_options确定旋转中心
            const rotationOptions = block.rotation_options || "text center";
            let rotationCenterX = scaledX;
            let rotationCenterY = finalY;
            
            if (rotationOptions === "text center") {
                // 文字中心旋转：计算文本中心点
                let textWidth = ctx.measureText(text).width;
                if (block.letter_spacing && block.letter_spacing !== 0 && text.length > 1) {
                    textWidth += (text.length - 1) * block.letter_spacing * globalScale;
                }
                rotationCenterX = scaledX + textWidth / 2;
                rotationCenterY = finalY - adjustedFontSize / 2; // 文本垂直中心
            } else if (rotationOptions === "image center") {
                // 图像中心旋转：使用画布中心
                rotationCenterX = canvas.width / 2;
                rotationCenterY = canvas.height / 2;
            }
            // 如果是其他值或默认，使用文本左下角（当前位置）
            
            ctx.translate(rotationCenterX, rotationCenterY);
            ctx.rotate(rotationAngle);
            
            // 计算文本相对于旋转中心的偏移
            const textOffsetX = scaledX - rotationCenterX;
            const textOffsetY = finalY - rotationCenterY;
            
            // 绘制文本（支持字间距和加粗模拟）
            if (block.bold) {
                // 在预览环境中，应该基于原始字体大小计算偏移，然后缩放到预览大小
                const originalFontSizeForBold = verticalScale !== 1 ? (originalFontSize * verticalScale) : originalFontSize;
                const baseBoldOffset = Math.max(1, Math.floor(originalFontSizeForBold / 30)); // 基于原始字体大小
                const actualBoldOffset = Math.max(0.5, baseBoldOffset * globalScale); // 缩放到预览大小，允许小于1的偏移
                
                // 调试信息
                if (window.WBLESS_DEBUG) {
                    console.log(`[WBLESS] Bold calculation (rotated): originalFontSize=${originalFontSize}, scaledFontSize=${scaledFontSize}, globalScale=${globalScale.toFixed(3)}, baseBoldOffset=${baseBoldOffset}, actualBoldOffset=${actualBoldOffset.toFixed(2)}`);
                }
                
                // 在周围位置绘制文本来模拟加粗（密集步长，避免分离同时控制性能）
                const stepSize = Math.max(0.25, Math.min(0.5, actualBoldOffset / 2)); // 动态步长，但不小于0.25px
                const maxSteps = Math.ceil(actualBoldOffset / stepSize); // 计算最大步数
                
                for (let i = -maxSteps; i <= maxSteps; i++) {
                    for (let j = -maxSteps; j <= maxSteps; j++) {
                        const dx = i * stepSize;
                        const dy = j * stepSize;
                        if (Math.abs(dx) > 0.1 || Math.abs(dy) > 0.1) { // 不在原位置重复绘制
                            if (block.letter_spacing && block.letter_spacing !== 0) {
                            drawTextWithLetterSpacing(ctx, text, textOffsetX + dx, textOffsetY + dy, block.letter_spacing * globalScale, lineSpacing);
                        } else {
                            drawMultiLineText(ctx, text, textOffsetX + dx, textOffsetY + dy, scaledFontSize, lineSpacing);
                        }
                        }
                    }
                }
            }
            
            // 绘制主文本
            if (block.letter_spacing && block.letter_spacing !== 0) {
                drawTextWithLetterSpacing(ctx, text, textOffsetX, textOffsetY, block.letter_spacing * globalScale, lineSpacing);
            } else {
                drawMultiLineText(ctx, text, textOffsetX, textOffsetY, scaledFontSize, lineSpacing);
            }
            
            ctx.restore();
        } else {
                    // 绘制文本（支持字间距和加粗模拟）
        if (block.bold) {
            // 在预览环境中，应该基于原始字体大小计算偏移，然后缩放到预览大小
            // 这样可以保持与实际输出的比例一致
            const originalFontSizeForBold = verticalScale !== 1 ? (originalFontSize * verticalScale) : originalFontSize;
            const baseBoldOffset = Math.max(1, Math.floor(originalFontSizeForBold / 30)); // 基于原始字体大小
            const actualBoldOffset = Math.max(0.5, baseBoldOffset * globalScale); // 缩放到预览大小，允许小于1的偏移
            
            // 调试信息
            if (window.WBLESS_DEBUG) {
                console.log(`[WBLESS] Bold calculation: originalFontSize=${originalFontSize}, scaledFontSize=${scaledFontSize}, globalScale=${globalScale.toFixed(3)}, baseBoldOffset=${baseBoldOffset}, actualBoldOffset=${actualBoldOffset.toFixed(2)}`);
            }
            
            // 在周围位置绘制文本来模拟加粗（密集步长，避免分离同时控制性能）
            const stepSize = Math.max(0.25, Math.min(0.5, actualBoldOffset / 2)); // 动态步长，但不小于0.25px
            const maxSteps = Math.ceil(actualBoldOffset / stepSize); // 计算最大步数
            
            for (let i = -maxSteps; i <= maxSteps; i++) {
                for (let j = -maxSteps; j <= maxSteps; j++) {
                    const dx = i * stepSize;
                    const dy = j * stepSize;
                    if (Math.abs(dx) > 0.1 || Math.abs(dy) > 0.1) { // 不在原位置重复绘制
                        if (block.letter_spacing && block.letter_spacing !== 0) {
                            drawTextWithLetterSpacing(ctx, text, scaledX + dx, finalY + dy, block.letter_spacing * globalScale, lineSpacing);
                        } else {
                            drawMultiLineText(ctx, text, scaledX + dx, finalY + dy, scaledFontSize, lineSpacing);
                        }
                    }
                }
            }
        }
        
        // 绘制主文本（处理多行文本）
        if (block.letter_spacing && block.letter_spacing !== 0) {
            drawTextWithLetterSpacing(ctx, text, scaledX, finalY, block.letter_spacing * globalScale, lineSpacing);
        } else {
            drawMultiLineText(ctx, text, scaledX, finalY, scaledFontSize, lineSpacing);
        }
        }
        
        // 绘制文本装饰（下划线、删除线）- 只在没有旋转时绘制，避免复杂的旋转计算
        if ((block.underline || block.strikethrough) && rotationAngle === 0) {
            ctx.strokeStyle = color;
            ctx.lineWidth = Math.max(1, adjustedFontSize * 0.05);
            
            // 计算文本宽度（考虑字间距）
            let textWidth = ctx.measureText(text).width;
            if (block.letter_spacing && block.letter_spacing !== 0 && text.length > 1) {
                textWidth += (text.length - 1) * block.letter_spacing * globalScale;
            }
            
            if (block.underline) {
                const underlineY = finalY + adjustedFontSize * 0.1; // 相对于文本基线
                ctx.beginPath();
                ctx.moveTo(scaledX, underlineY);
                ctx.lineTo(scaledX + textWidth, underlineY);
                ctx.stroke();
            }
            
            if (block.strikethrough) {
                const strikeY = finalY - adjustedFontSize * 0.3; // 相对于文本基线
                ctx.beginPath();
                ctx.moveTo(scaledX, strikeY);
                ctx.lineTo(scaledX + textWidth, strikeY);
                ctx.stroke();
            }
        }
        
        // 重置透明度
        ctx.globalAlpha = 1.0;
        
        if (debugMode) {
            console.log(`[WBLESS] Rendered text "${text}" at (${scaledX.toFixed(1)}, ${scaledY.toFixed(1)}) with font size ${scaledFontSize.toFixed(1)}px`);
        }
    }
}

/**
 * 在画布上绘制多行文本
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {string} text - 要绘制的文本（可包含\n）
 * @param {number} x - 起始x坐标
 * @param {number} y - 起始y坐标
 * @param {number} fontSize - 字体大小（用于计算行高）
 * @param {number} lineSpacing - 行间距（像素）
 */
function drawMultiLineText(ctx, text, x, y, fontSize, lineSpacing = 0) {
    if (!text) return;
    
    const lines = text.split('\n');
    const baseLineHeight = fontSize * 1.2; // 基础行高为字体大小的1.2倍
    const lineHeight = baseLineHeight + lineSpacing; // 加上行间距
    
    // 调试信息
    if (lines.length > 1) {
        console.log('[WBLESS] Drawing multi-line text:');
        console.log('  Text:', text);
        console.log('  Lines:', lines);
        console.log('  Position:', {x, y});
        console.log('  Font size:', fontSize);
        console.log('  Line spacing:', lineSpacing);
        console.log('  Line height:', lineHeight);
    }
    
    for (let i = 0; i < lines.length; i++) {
        const lineY = y + (i * lineHeight);
        ctx.fillText(lines[i], x, lineY);
        
        if (lines.length > 1) {
            console.log(`  Line ${i}: "${lines[i]}" at y=${lineY}`);
        }
    }
}

/**
 * 绘制带字间距的文本（支持多行）
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {string} text - 要绘制的文本（可包含\n）
 * @param {number} x - 起始X坐标
 * @param {number} y - 起始Y坐标
 * @param {number} letterSpacing - 字间距（像素）
 * @param {number} lineSpacing - 行间距（像素）
 */
function drawTextWithLetterSpacing(ctx, text, x, y, letterSpacing, lineSpacing = 0) {
    if (!text) return;
    
    const lines = text.split('\n');
    // 从字体设置中提取字体大小
    const fontSize = extractFontSizeFromFont(ctx.font);
    const baseLineHeight = fontSize * 1.2; // 基础行高
    const lineHeight = baseLineHeight + lineSpacing; // 加上行间距
    
    // 调试信息
    if (letterSpacing && letterSpacing !== 0) {
        console.log('[WBLESS] Drawing text with letter spacing:');
        console.log('  Text:', text);
        console.log('  Font:', ctx.font);
        console.log('  Extracted font size:', fontSize);
        console.log('  Letter spacing:', letterSpacing);
        console.log('  Line spacing:', lineSpacing);
        console.log('  Line height:', lineHeight);
    }
    
    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
        const line = lines[lineIndex];
        const lineY = y + (lineIndex * lineHeight);
        let currentX = x;
        
        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            ctx.fillText(char, currentX, lineY);
            const charWidth = ctx.measureText(char).width;
            currentX += charWidth + letterSpacing;
        }
    }
}

/**
 * 从字体字符串中提取字体大小
 * @param {string} fontString - CSS字体字符串，如 "italic bold 20px Arial"
 * @returns {number} 字体大小（像素）
 */
function extractFontSizeFromFont(fontString) {
    // 支持更复杂的字体字符串格式
    const match = fontString.match(/(\d+(?:\.\d+)?)px/);
    return match ? parseFloat(match[1]) : 16; // 默认16px
}

/**
 * 获取颜色值
 * @param {string} colorName - 颜色名称
 * @param {string} hexColor - 十六进制颜色
 * @returns {string} CSS颜色值
 */
function getColorValue(colorName, hexColor) {
    // 颜色映射表（与后端COLOR_MAPPING保持一致）
    const COLOR_MAPPING = {
        'white': '#FFFFFF', 'black': '#000000', 'red': '#FF0000', 'green': '#00FF00',
        'blue': '#0000FF', 'yellow': '#FFFF00', 'cyan': '#00FFFF', 'magenta': '#FF00FF',
        'orange': '#FFA500', 'purple': '#800080', 'pink': '#FFC0CB', 'brown': '#A0550F',
        'gray': '#808080', 'lightgray': '#D3D3D3', 'darkgray': '#666666',
        'olive': '#808000', 'lime': '#008000', 'teal': '#008080', 'navy': '#000080',
        'maroon': '#800000', 'fuchsia': '#FF0080', 'aqua': '#00FF80', 'silver': '#C0C0C0',
        'gold': '#FFD700', 'turquoise': '#40E0D0', 'lavender': '#E6E6FA', 'violet': '#EE82EE',
        'coral': '#FF7F50', 'indigo': '#4B0082'
    };
    
    // 处理可能的列表类型输入
    if (Array.isArray(colorName)) {
        colorName = colorName.length > 0 ? colorName[0] : 'white';
    }
    if (Array.isArray(hexColor)) {
        hexColor = hexColor.length > 0 ? hexColor[0] : '#FFFFFF';
    }
    
    // 如果选择了"custom"，优先使用十六进制颜色
    if (colorName === 'custom' && hexColor && hexColor.startsWith('#')) {
        return hexColor;
    }
    
    // 使用颜色名称映射
    if (colorName && COLOR_MAPPING[colorName.toLowerCase()]) {
        return COLOR_MAPPING[colorName.toLowerCase()];
    }
    
    // 如果没有找到颜色名称，但有有效的十六进制颜色，则使用它
    if (hexColor && hexColor.startsWith('#')) {
        return hexColor;
    }
    
    // 默认白色
    return '#FFFFFF';
}

/**
 * 在画布上绘制文本预览
 * @param {HTMLCanvasElement} canvas - 目标画布
 * @param {Array} textBlocks - 文本块数组
 * @param {Object} overlaySettings - Overlay Text节点的设置
 */
export function drawTextPreview(canvas, textBlocks, overlaySettings) {
    if (!canvas || !textBlocks || textBlocks.length === 0) {
        clearPreviewCanvas(canvas);
        return;
    }
    
    // 启用调试模式的全局开关
    const debugMode = window.WBLESS_DEBUG || false;
    
    if (debugMode) {
        console.log('[WBLESS] Drawing text preview with:', {
            textBlockCount: textBlocks.length,
            textBlocks: textBlocks,
            overlaySettings: overlaySettings,
            justifyMode: overlaySettings.justify || 'center'
        });
    }
    
    const ctx = canvas.getContext('2d');
    clearPreviewCanvas(canvas);
    
    // 第一步：测量所有文本的实际尺寸
    const textMeasurements = measureAllTextBlocks(ctx, textBlocks, overlaySettings);
    
    // 第二步：计算全局缩放比例，确保所有文本都能适应窗口
    const globalScale = calculateGlobalScale(canvas, textMeasurements);
    
    if (debugMode) {
        console.log('[WBLESS] Global scale calculated:', {
            canvasSize: `${canvas.width}x${canvas.height}`,
            textBounds: textMeasurements.bounds,
            globalScale: globalScale.toFixed(3),
            overlayRotation: `${overlaySettings.rotation_angle || 0}°`
        });
    }
    
    try {
        // 应用Overlay Text的旋转角度（整个画布旋转）
        const overlayRotationAngle = (overlaySettings.rotation_angle || 0) * Math.PI / 180;
        if (overlayRotationAngle !== 0) {
            ctx.save();
            // 以画布中心为旋转点
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate(overlayRotationAngle);
            ctx.translate(-canvas.width / 2, -canvas.height / 2);
        }
        
        // 第三步：使用全局缩放绘制所有文本
        renderScaledTextBlocks(ctx, textMeasurements, globalScale, canvas, debugMode, overlaySettings);
        
        // 恢复旋转变换
        if (overlayRotationAngle !== 0) {
            ctx.restore();
        }
    } catch (error) {
        console.error('[WBLESS] Error drawing text preview:', error);
        // 绘制错误信息
        ctx.fillStyle = '#ff6666';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Preview Error', canvas.width / 2, canvas.height / 2);
        ctx.fillStyle = '#999';
        ctx.font = '10px Arial';
        ctx.fillText('Check console for details', canvas.width / 2, canvas.height / 2 + 20);
    }
}

/**
 * 防抖函数
 * @param {Function} func - 要防抖的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} 防抖后的函数
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 优化的防抖函数，针对预览更新进行性能优化
 * 使用requestAnimationFrame确保在浏览器的绘制周期内执行
 * @param {Function} func - 要防抖的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} 防抖后的函数
 */
export function debounceRAF(func, wait = 16) {
    let timeout;
    let rafId;
    
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            if (rafId) {
                cancelAnimationFrame(rafId);
            }
            
            rafId = requestAnimationFrame(() => {
                func(...args);
                rafId = null;
            });
        };
        
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
