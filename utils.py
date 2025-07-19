# plugins_human/eh_preview/utils.py
import asyncio
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from src.logger import logger
from src.plugin import PROJECT_ROOT

# 把字体路径也定义成常量，避免硬编码
# 假设你的字体在项目根目录的 assets/fonts/ 文件夹下
FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "lolita.ttf"


async def add_watermark_to_image(image_path: Path) -> Path:
    """为一个图片异步地添加水印.

    Args:
        image_path (Path): 图片文件的路径.

    Returns:
        Path: 添加水印后的图片路径 (如果格式转换，则为新路径).
    """

    def _blocking_add_watermark() -> Path:
        """这是一个同步函数，包含了所有耗时的图像处理操作."""
        try:
            # 确保字体文件存在
            if not FONT_PATH.exists():
                logger.warning(f"水印字体文件未找到: {FONT_PATH}，跳过加水印。")
                return image_path

            base = Image.open(image_path).convert("RGBA")
            width, height = base.size
            txt = Image.new("RGBA", base.size, (255, 255, 255, 0))

            font_size = max(18, int(width / 40))  # 动态调整字体大小
            font = ImageFont.truetype(str(FONT_PATH), font_size)
            draw = ImageDraw.Draw(txt)

            watermark_text = "Powered by DaY-Core"
            # textbbox 在新版 Pillow 中替代了 textsize
            bbox = draw.textbbox((0, 0), watermark_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            position = (width - text_width - 10, height - text_height - 10)

            draw.text(position, watermark_text, fill=(255, 255, 255, 128), font=font)
            watermarked = Image.alpha_composite(base, txt)

            # 如果是jpeg/jpg/webp，统一转成png，避免透明度丢失
            if image_path.suffix.lower() in [".jpeg", ".jpg", ".webp"]:
                new_path = image_path.with_suffix(".png")
                watermarked.convert("RGB").save(new_path, "PNG")
                image_path.unlink()  # 删除原文件
                return new_path
            else:
                watermarked.save(image_path)
                return image_path
        except Exception as e:
            logger.error(f"添加水印失败: {image_path}, 错误: {e}", exc_info=True)
            return image_path

    # --- 核心改造！---
    # PIL/Pillow 是阻塞库，直接在主线程运行会卡住整个机器人。
    # 我们用 loop.run_in_executor 把它扔到线程池里执行，
    # 这样就不会影响我们响应其他消息了！这才是异步编程的精髓！
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _blocking_add_watermark)
