# I:/github/DaY-Core/plugins_human/eh_preview/scrapers.py
import asyncio
import re
from typing import Any, ClassVar, NamedTuple

import httpx
from bs4 import BeautifulSoup
from src.logger import logger

from .config import Config


class ScrapeResult(NamedTuple):
    """爬取结果的数据结构，包含画廊的标题、作者、描述和图片链接列表.

    Attributes:
        title (str): 画廊标题.
        author (str | None): 画廊作者，可能为 None.
        description (str | None): 画廊描述，可能为 None.
        image_urls (list[str]): 图片链接列表.
        download_headers (dict | None): 下载图片时可能需要的额外请求头.
    """

    title: str
    author: str | None
    description: str | None
    image_urls: list[str]
    download_headers: dict | None = None  # <-- 1. 在这里增加一个字段


EHENTAI_RE = re.compile(r"https?://e-hentai\.org/g/\d+/[\w-]+")
EXHENTAI_RE = re.compile(r"https?://exhentai\.org/g/\d+/[\w-]+")
NHENTAI_RE = re.compile(r"https?://nhentai\.(net|to)/g/\d+")
PIXIV_RE = re.compile(r"https?://www\.pixiv\.net/artworks/\d+")


class Scraper:
    """异步爬虫类，负责处理不同网站的画廊爬取逻辑."""

    SCRAPER_MAPPING: ClassVar = {
        EHENTAI_RE: "scrape_ehentai",
        EXHENTAI_RE: "scrape_ehentai",
        NHENTAI_RE: "scrape_nhentai",
        PIXIV_RE: "scrape_pixiv",
    }

    def __init__(self, config: Config, max_concurrency: int = 10) -> None:
        self.config = config
        self.semaphore = asyncio.Semaphore(max_concurrency)
        logger.info(f"Scraper 初始化，最大并发数设置为: {max_concurrency}")

        self.client = httpx.AsyncClient(
            proxy=config.proxy,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",  # noqa: E501
            },
            timeout=45.0,
            follow_redirects=True,
        )

    async def close(self) -> None:
        """优雅地关闭 HTTP 客户端."""
        await self.client.aclose()

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """异步 GET 请求，带有重试机制和并发控制.

        Args:
            url (str): 请求的 URL.
            **kwargs: 其他 httpx 请求参数.

        Returns:
            httpx.Response: 请求的响应对象.

        Raises:
            ConnectionError: 如果请求失败超过3次仍然无法成功.
        """
        async with self.semaphore:
            for attempt in range(3):
                try:
                    loop = asyncio.get_running_loop()
                    await asyncio.sleep(0.8 + 1.5 * loop.time() % 1)
                    logger.debug(f"正在请求 (第 {attempt + 1} 次): {url}")
                    resp = await self.client.get(url, **kwargs)
                    resp.raise_for_status()
                    return resp
                except httpx.RequestError as e:
                    logger.warning(f"请求失败: {url}, 错误: {e}")
                    await asyncio.sleep(2)
            raise ConnectionError(f"请求 {url} 3次后仍然失败。")

    async def _gather_image_urls(self, page_links: list[str], headers: dict) -> list[str]:
        tasks = [self.get(link, headers=headers) for link in page_links]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        image_urls = []
        for i, res in enumerate(results):
            if isinstance(res, httpx.Response):
                img_soup = BeautifulSoup(res.text, "html.parser")
                img_tag = img_soup.select_one("#img") or img_soup.select_one("#i3 > a > img")
                if img_tag and "src" in img_tag.attrs:
                    image_urls.append(img_tag["src"])
            else:
                logger.error(f"获取图片页面 {page_links[i]} 失败: {res}")
        return image_urls

    async def scrape_ehentai(self, url: str) -> ScrapeResult:
        """爬取 E-Hentai 或 Ex-Hentai 画廊主页，提取图片链接.

        Args:
            url (str): 画廊主页的 URL.

        Returns:
            ScrapeResult: 包含画廊标题、作者、描述和图片链接的结果对象.

        Raises:
            ValueError: 如果 URL 无效或未找到图片链接.
            ConnectionError: 如果访问主页时 Cookie 已失效或权限不足.
        """
        logger.info(f"开始爬取 E-Hentai/Ex-Hentai: {url}")
        headers = {"Cookie": self.config.e_cookie}

        if (
            "exhentai" not in url
            and self.config.e_cookie
            and "ipb_member_id" in self.config.e_cookie
        ):
            url = url.replace("e-hentai.org", "exhentai.org")
            logger.info(f"检测到ExHentai Cookie，URL已重定向至: {url}")

        main_page_resp = await self.get(url, headers=headers)
        soup = BeautifulSoup(main_page_resp.text, "html.parser")

        # 附魔第一层：检查标题，看看是不是伤心熊猫
        title_tag = soup.find("title")
        if not title_tag or "Sad Panda" in title_tag.text:
            raise ConnectionError("熊猫哭了！访问主页时Cookie失效或权限不足。")

        # 附魔第二层：在获取画廊标题前，先检查标签是否存在！
        gn_tag = soup.select_one("#gn")
        if not gn_tag:
            # 如果找不到标题，说明页面结构不对，直接抛出异常，让上层知道下载失败了
            raise ValueError("在画廊主页未找到标题标签(#gn)，可能是Cookie失效或页面结构已变更。")
        title = gn_tag.text

        # 附魔第三层：用同样的方式加固对链接列表的查找
        page_links = [a["href"] for a in soup.select("#gdt > a")]
        if not page_links:
            page_links = [a["href"] for a in soup.select("table.itg td.itd a")]
        if not page_links:
            page_links = [a["href"] for a in soup.find_all("a", href=re.compile(r"/s/"))]

        if not page_links:
            raise ValueError("在画廊主页未找到任何已知模式的缩略图链接。")

        image_urls = await self._gather_image_urls(page_links, headers)

        if not image_urls:
            raise ValueError("成功访问所有详情页，但未能提取到任何图片链接。")

        return ScrapeResult(title=title, author=None, description=None, image_urls=image_urls)

    # --- 决定性的最终修正！ ---
    async def scrape_nhentai(self, url: str) -> ScrapeResult:
        """通过官方API获取画廊信息，从根源上解决Cloudflare问题.

        Args:
            url (str): N-Hentai 画廊的 URL.

        Returns:
            ScrapeResult: 包含画廊标题和图片链接的结果对象.

        Raises:
            ValueError: 如果 URL 无效或无法提取到画廊ID.
            ConnectionError: 如果请求失败或无法访问API.
        """
        logger.info(f"开始通过API爬取 N-Hentai: {url}")
        match = re.search(r"/g/(\d+)", url)
        if not match:
            raise ValueError("无效的 N-Hentai URL。")
        album_id = match.group(1)

        # 1. 直接请求不设防的 API 端点
        api_url = f"https://nhentai.net/api/gallery/{album_id}"
        api_resp = await self.get(api_url)  # 这个请求不需要任何特殊的 header
        data = api_resp.json()

        # 2. 从返回的 JSON 中提取“圣印”(media_id) 和标题
        title = data.get("title", {}).get("pretty", f"nhentai-{album_id}")
        media_id = data["media_id"]

        # 3. 用“圣印”和页面信息，自己拼接出每一张图片的真实URL
        image_urls = []
        for i, page in enumerate(data["images"]["pages"]):
            ext = {"j": "jpg", "p": "png", "g": "gif", "w": "webp"}.get(page["t"], "jpg")
            # 使用 i.nhentai.net 作为图片服务器域名
            image_urls.append(f"https://i4.nhentai.net/galleries/{media_id}/{i + 1}.{ext}")

        logger.success(f"通过API成功获取到 {len(image_urls)} 张图片链接！")
        return ScrapeResult(title=title, author=None, description=None, image_urls=image_urls)

    # --- 修正结束 ---

    async def scrape_pixiv(self, url: str) -> ScrapeResult:
        """爬取 Pixiv 画廊主页，提取图片链接.

        Args:
            url (str): Pixiv 画廊主页的 URL.

        Returns:
            ScrapeResult: 包含画廊标题、作者、描述和图片链接的结果对象.

        Raises:
            ValueError: 如果 URL 无效或未找到图片链接.
            ConnectionError: 如果访问主页时 Cookie 已失效或权限不足.
        """
        logger.info(f"开始爬取 Pixiv: {url}")
        match = re.search(r"artworks/(\d+)", url)
        if not match:
            raise ValueError("无效的 Pixiv URL。")
        artwork_id = match.group(1)
        headers = {"Cookie": self.config.p_cookie, "Referer": "https://www.pixiv.net/"}
        pages_api_url = f"https://www.pixiv.net/ajax/illust/{artwork_id}/pages"
        details_api_url = f"https://www.pixiv.net/ajax/illust/{artwork_id}"
        pages_task = asyncio.create_task(self.get(pages_api_url, headers=headers))
        details_task = asyncio.create_task(self.get(details_api_url, headers=headers))
        pages_resp, details_resp = await asyncio.gather(pages_task, details_task)
        pages_data = pages_resp.json()
        details_data = details_resp.json()
        if pages_data.get("error") or details_data.get("error"):
            raise ValueError(
                f"Pixiv API 返回错误: {pages_data.get('message') or details_data.get('message')}"
            )
        body = details_data["body"]
        title = body.get("title", "未知标题")
        author = body.get("userName", "未知作者")
        desc_html = body.get("description", "")
        description = BeautifulSoup(desc_html, "html.parser").get_text("\n")
        image_urls = [page["urls"]["original"] for page in pages_data["body"]]
        
        # --- 2. 在这里返回结果时，附加上下载图片所需的 Referer 头 ---
        return ScrapeResult(
            title=title,
            author=author,
            description=description,
            image_urls=image_urls,
            download_headers={"Referer": "https://www.pixiv.net/"},
        )
