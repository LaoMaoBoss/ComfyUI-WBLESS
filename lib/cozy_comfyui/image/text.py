""" Text Font Support """

import textwrap
from enum import Enum

from matplotlib import font_manager
from PIL import Image, ImageFont, ImageDraw

from .. import \
    logger

from . import \
    PixelType, ImageType

from .convert import \
    pil_to_cv

# ==============================================================================
# === ENUMERATION ===
# ==============================================================================

class EnumAlignment(Enum):
    TOP = 10
    CENTER = 0
    BOTTOM = 20

class EnumJustify(Enum):
    LEFT = 10
    CENTER = 0
    RIGHT = 20

# ==============================================================================
# === SUPPORT ===
# ==============================================================================

def font_names() -> list[str]:
    try:
        mgr = font_manager.FontManager()
        return {font.name: font.fname for font in mgr.ttflist}
    except Exception as e:
        logger.warn(e)
    return {}

def text_size(draw: ImageDraw, text:str, font:ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    return text_width, text_height

def text_autosize(text:str, font:str, width:int, height:int, columns:int=0) -> tuple[str, int, int, int]:
    img = Image.new("L", (width, height))
    draw = ImageDraw.Draw(img)
    if columns != 0:
        text = text.split('\n')
        lines = []
        for x in text:
            line = textwrap.wrap(x, columns, break_long_words=False)
            lines.extend(line)
        text = '\n'.join(lines)

    font_size = 1
    test_text = text if columns == 0 else ' ' * columns
    while 1:
        ttf = ImageFont.truetype(font, font_size)
        w, h = text_size(draw, test_text, ttf)
        if w >= width or h >= height:
            break
        font_size += 1
    # * 0.6543
    return text, font_size * 0.33, w, h

def text_draw(full_text: str, font: ImageFont,
              width: int, height: int,
              align: EnumAlignment=EnumAlignment.CENTER,
              justify: EnumJustify=EnumJustify.CENTER,
              margin: int=0, line_spacing: int=0,
              color: PixelType=(255,255,255,255)) -> ImageType:

    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    text_lines = full_text.split('\n')
    count = len(text_lines)
    height_max = text_size(draw, full_text, font)[1] + line_spacing * (count-1)
    height_delta = height_max / count
    # find the bounding box of this

    if align == EnumAlignment.TOP:
        y = margin
    elif align == EnumAlignment.BOTTOM:
        y = height - height_max * 1.5 - margin
    else:
        y = height * 0.5 - height_max

    for line in text_lines:
        line_width = text_size(draw, line, font)[0]
        if justify == EnumJustify.LEFT:
            x = margin
        elif justify == EnumJustify.RIGHT:
            x = width - line_width - margin
        else:
            x = (width - line_width) / 2

        # x = min(width - line_width, max(line_width, x))
        draw.text((x, y), line, fill=color, font=font)
        y += height_delta
    return pil_to_cv(img)
