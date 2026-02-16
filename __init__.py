# plugins_human/eh_preview/__init__.py
import asyncio
import datetime
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from sqlalchemy.orm import Session
from src.adapters.base import Adapter
from src.api import API_FAILED
from src.bot import Bot
from src.event import GroupMessageEvent
from src.logger import logger
from src.matcher import on_regex, on_shutdown, on_startup
from src.message import Message
from src.plugin import PROJECT_ROOT

from . import database, models
from .config import Config as PluginConfig
from .scrapers import Scraper, ScrapeResult
from .utils import add_watermark_to_image

# --- 1. 状态定义：用数据类来管理任务，清晰又安全 ---
TaskStatus = Literal["waiting", "downloading", "success", "failed"]


@dataclass
class DownloadRequest:
    """封装一次用户请求的信息."""

    group_id: str
    user_id: str
    message_id: str
    self_id: str


@dataclass
class DownloadTask:
    """管理一个下载任务的完整状态."""

    url: str
    status: TaskStatus = "waiting"
    requests: list[DownloadRequest] = field(default_factory=list)
    task: asyncio.Task | None = None
    result_path: Path | None = None
    result_message: str | None = None
    finished_event: asyncio.Event = field(default_factory=asyncio.Event)


# --- 2. 全局变量：插件的记忆中枢 ---
download_tasks: dict[str, DownloadTask] = {}
scraper: Scraper | None = None


async def _cleanup_cache(session: Session, config: PluginConfig) -> None:
    """清理过期的和超出数量限制的缓存."""
    logger.info("开始执行 EhPreview 缓存清理程序...")
    now = datetime.datetime.now(datetime.timezone.utc)

    # 策略一：清理过期的缓存 (TTL)
    if config.cache_max_days > 0:
        cutoff_date = now - datetime.timedelta(days=config.cache_max_days)
        expired_records = (
            session.query(models.DownloadRecord)
            .filter(models.DownloadRecord.updated_at < cutoff_date)
            .all()
        )

        if expired_records:
            logger.info(f"发现 {len(expired_records)} 条过期缓存，准备清理...")
            for record in expired_records:
                # 从硬盘删除文件！
                if record.result_path and Path(record.result_path).exists():
                    try:
                        shutil.rmtree(record.result_path)
                        logger.debug(f"已删除过期缓存文件夹: {record.result_path}")
                    except Exception as e:
                        logger.error(f"删除缓存文件夹 {record.result_path} 失败: {e}")
                # 从数据库删除记录
                session.delete(record)
            session.commit()
            logger.success(f"成功清理了 {len(expired_records)} 条过期缓存。")

    # 策略二：清理超出数量的缓存 (Size-Based)
    if config.cache_max_entries > 0:
        current_count = session.query(models.DownloadRecord).count()
        if current_count > config.cache_max_entries:
            num_to_delete = current_count - config.cache_max_entries
            logger.info(
                f"缓存数量 ({current_count}) 超出上限 ({config.cache_max_entries})，"
                f"准备清理 {num_to_delete} 条最旧的缓存..."
            )

            oldest_records = (
                session.query(models.DownloadRecord)
                .order_by(models.DownloadRecord.created_at.asc())
                .limit(num_to_delete)
                .all()
            )

            for record in oldest_records:
                if record.result_path and Path(record.result_path).exists():
                    try:
                        shutil.rmtree(record.result_path)
                        logger.debug(f"已删除超量缓存文件夹: {record.result_path}")
                    except Exception as e:
                        logger.error(f"删除缓存文件夹 {record.result_path} 失败: {e}")
                session.delete(record)
            session.commit()
            logger.success(f"成功清理了 {len(oldest_records)} 条超量缓存。")


# --- 3. 生命周期钩子：极致简洁的初始化与清理 ---
@on_startup
async def _(bot: Bot) -> None:
    """插件启动时，从框架获取已加载的配置，并初始化 Scraper.

    所有繁琐的IO和校验工作都已由框架在加载时完成.
    """
    global scraper, download_tasks
    plugin_config: PluginConfig | None = bot.get_plugin_config(__name__)
    if not plugin_config:
        logger.error(f"EhPreview 插件 ({__name__}) 的配置未找到，请检查插件配置文件。")
        return

    scraper = Scraper(config=plugin_config)
    logger.success(f"EhPreview 插件 ({__name__}) 已启动，Scraper 初始化完成。")

    # --- 使用我们自己的数据库初始化函数 ---
    logger.info("正在初始化 EhPreview 插件的专属数据库...")
    try:
        database.init_database()
        logger.success("EhPreview 数据库及表结构确认完毕。")
    except Exception as e:
        logger.error(f"初始化 EhPreview 数据库失败: {e}", exc_info=True)
        return

    try:
        with database.SessionFactory() as session:
            # 把 session 和 config 传给我们的环卫队！
            await _cleanup_cache(session, plugin_config)
    except Exception as e:
        logger.error(f"执行 EhPreview 缓存清理时发生错误: {e}", exc_info=True)

    logger.info("正在从插件专属数据库加载历史缓存...")
    try:
        with database.SessionFactory() as session:
            records: list[models.DownloadRecord] = session.query(models.DownloadRecord).all()
            for record in records:
                task = DownloadTask(
                    url=record.url,
                    status=record.status,
                    result_path=Path(record.result_path) if record.result_path else None,
                    result_message=record.result_message,
                )
                task.finished_event.set()
                download_tasks[record.url] = task
        logger.success(f"成功从 EhPreview 数据库加载了 {len(records)} 条历史下载记录！")
    except Exception as e:
        logger.error(f"从 EhPreview 数据库加载缓存失败: {e}", exc_info=True)


@on_shutdown
async def _(_bot: Bot) -> None:
    """插件关闭时，优雅地关闭 Scraper 的客户端并取消任务."""
    if scraper:
        await scraper.close()
        logger.info(f"EhPreview 插件 ({__name__}) 已关闭，Scraper 客户端已释放。")

    for task_info in download_tasks.values():
        if task_info.task and not task_info.task.done():
            task_info.task.cancel()


# --- 4. 核心响应器：精准捕获URL ---
URL_PATTERN = re.compile("|".join(p.pattern for p in Scraper.SCRAPER_MAPPING), re.IGNORECASE)
eh_matcher = on_regex(URL_PATTERN.pattern)


@eh_matcher.handle()
async def handle_gallery_url(adapter: Adapter, event: GroupMessageEvent, matched: re.Match) -> None:
    """处理捕获到的画廊链接."""
    # 在处理函数的一开始，检查 scraper 是否成功初始化
    if not scraper:
        logger.warning("Scraper 未初始化，EhPreview 插件无法处理请求。")
        await adapter.send_message(
            event.group_id,
            "group",
            Message()
            .reply(event.message_id)
            .text("呜... EhPreview 插件初始化失败了，请检查后台日志。"),
        )
        return

    url = matched.group(0).strip()
    if "e-hentai.org" in url:
        url = url.replace("e-hentai.org", "exhentai.org")

    request = DownloadRequest(
        group_id=event.group_id,
        user_id=event.user_id,
        message_id=event.message_id,
        self_id=event.self_id,
    )

    if url in download_tasks:
        task_info = download_tasks[url]
        task_info.requests.append(request)
        logger.info(f"链接 {url} 已在任务队列中，追加新请求。")

        if task_info.status in ["waiting", "downloading"]:
            await adapter.send_message(
                event.group_id,
                "group",
                Message()
                .reply(event.message_id)
                .text("这个本子已经在下载队列里啦，请稍等片刻哦~ (｡･ω･｡)ﾉ"),
            )
            await task_info.finished_event.wait()
        elif task_info.status == "success":
            await adapter.send_message(
                event.group_id,
                "group",
                Message().reply(event.message_id).text("这个本子已经下载好啦，正在为你发送~"),
            )
            await send_result(adapter, request, task_info)
        elif task_info.status == "failed":
            await adapter.send_message(
                event.group_id,
                "group",
                Message()
                .reply(event.message_id)
                .text(f"这个本子之前下载失败了欸... 原因: {task_info.result_message}"),
            )
    else:
        await adapter.send_message(
            event.group_id,
            "group",
            Message()
            .reply(event.message_id)
            .text("收到！新的本子已加入下载队列，请不要重复发送哦~"),
        )
        task_info = DownloadTask(url=url, requests=[request])
        download_tasks[url] = task_info

        bg_task = asyncio.create_task(download_gallery(adapter, task_info))
        task_info.task = bg_task
        bg_task.add_done_callback(lambda t: logger.info(f"后台任务 {t.get_name()} 完成。"))


# --- 5. 下载与处理核心函数 ---
async def download_gallery(adapter: Adapter, task_info: DownloadTask) -> None:
    """真正的后台下载、处理、发送结果的函数."""
    task_info.status = "downloading"
    task_info.task.set_name(f"Downloader-{task_info.url[:30]}")
    logger.info(f"开始下载: {task_info.url}")

    scrape_result = None  # 在 try 外部初始化
    try:
        matched_pattern = next(p for p in Scraper.SCRAPER_MAPPING if p.match(task_info.url))
        scraper_func_name = Scraper.SCRAPER_MAPPING[matched_pattern]
        scraper_func = getattr(scraper, scraper_func_name)
        scrape_result: ScrapeResult = await scraper_func(task_info.url)

        # 使用 PROJECT_ROOT 来构建一个绝对路径！
        download_dir = (
            PROJECT_ROOT
            / scraper.config.download_dir
            / re.sub(r'[\\/:*?"<>|]', "_", scrape_result.title[:50])
        )
        download_dir.mkdir(parents=True, exist_ok=True)

        # 将 scraper 返回的专属请求头传递给下载函数
        image_tasks = [
            download_image(url, download_dir, index, headers=scrape_result.download_headers)
            for index, url in enumerate(scrape_result.image_urls)
        ]
        image_paths = await asyncio.gather(*image_tasks)

        valid_image_paths = sorted([p for p in image_paths if p])
        if not valid_image_paths:
            raise ValueError("所有图片都下载失败了！")

        watermark_tasks = [add_watermark_to_image(p) for p in valid_image_paths]
        await asyncio.gather(*watermark_tasks)

        task_info.status = "success"
        task_info.result_path = download_dir

        title_text = f"标题: {scrape_result.title}"
        if scrape_result.author:
            title_text += f"\n作者: {scrape_result.author}"
        task_info.result_message = title_text

    except Exception as e:
        logger.error(f"下载任务 {task_info.url} 失败: {e}", exc_info=True)
        task_info.status = "failed"
        task_info.result_message = f"下载失败了 T_T，错误: {e}"

    finally:
        # --- 将结果写入我们自己的数据库 ---
        try:
            with database.SessionFactory() as session:
                existing_record = session.query(models.DownloadRecord).get(task_info.url)
                if existing_record:
                    existing_record.status = task_info.status
                    existing_record.result_path = (
                        str(task_info.result_path) if task_info.result_path else None
                    )
                    existing_record.result_message = task_info.result_message
                    logger.info(f"更新 EhPreview 数据库缓存记录: {task_info.url}")
                else:
                    new_record = models.DownloadRecord(
                        url=task_info.url,
                        status=task_info.status,
                        title=scrape_result.title if scrape_result else "未知标题",
                        result_path=str(task_info.result_path) if task_info.result_path else None,
                        result_message=task_info.result_message,
                    )
                    session.add(new_record)
                    logger.info(f"创建新的 EhPreview 数据库缓存记录: {task_info.url}")
                session.commit()
        except Exception as e:
            logger.error(f"写入 EhPreview 数据库缓存时出错: {e}", exc_info=True)

        for request in task_info.requests:
            try:
                await send_result(adapter, request, task_info)
            except Exception as e:
                logger.error(f"向群 {request.group_id} 发送结果时出错: {e}", exc_info=True)

        task_info.finished_event.set()


# 重构 download_image 函数，使其更简单、更可靠
async def download_image(
    url: str, save_dir: Path, index: int, headers: dict | None = None
) -> Path | None:
    """下载单张图片.

    Args:
        url (str): 要下载的图片的精确 URL.
        save_dir (Path): 保存目录.
        index (int): 图片序号，用于命名.
        headers (dict | None, optional): 下载时使用的请求头. Defaults to None.

    Returns:
        Path | None: 成功则返回文件路径，否则返回 None.
    """
    try:
        # 直接使用全局 scraper 的 client 进行下载，保持 User-Agent 和代理等设置一致
        # 并传入从 scraper 获取的、针对特定网站的 headers (例如 Pixiv 的 Referer)
        resp = await scraper.client.get(url, headers=headers)
        resp.raise_for_status()

        # 从原始、准确的 URL 中提取文件扩展名，不再进行猜测
        ext = Path(url).suffix
        if not ext:  # 如果URL碰巧没有扩展名，提供一个备用方案
            content_type = resp.headers.get("content-type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
            else:
                ext = ".jpg"  # 默认

        file_path = save_dir / f"{index:03d}{ext}"
        with open(file_path, "wb") as f:
            f.write(resp.content)
        return file_path

    except Exception as e:
        logger.warning(f"下载单张图片失败: {url}, 最终错误: {e}")
        return None


async def send_result(adapter: Adapter, request: DownloadRequest, task_info: DownloadTask) -> None:
    """向单个请求者发送最终结果."""
    if task_info.status == "success" and task_info.result_path:
        image_files = sorted(task_info.result_path.glob("*.*"))

        forward_message = Message().node(
            uin=request.self_id,
            name="DaY-Core 下载助手",
            content=task_info.result_message,
        )

        # 限制预览数量，防止消息过长或风控
        for img_path in image_files[:30]:
            forward_message.node(
                uin=request.self_id, name="枫", content=Message().image(img_path.as_uri())
            )
        if len(image_files) > 30:
            forward_message.node(
                uin=request.self_id,
                name="DaY-Core 下载助手",
                content=f"...等共 {len(image_files)} 张图片。",
            )

        result = await adapter.send_group_forward_msg(request.group_id, forward_message)
        if result is API_FAILED:
            await adapter.send_message(
                request.group_id,
                "group",
                Message().reply(request.message_id).text("呜... 合并转发失败了，可能是被风控了。"),
            )
    else:
        await adapter.send_message(
            request.group_id,
            "group",
            Message().reply(request.message_id).text(task_info.result_message),
        )
