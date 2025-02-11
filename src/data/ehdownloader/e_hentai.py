import requests
from bs4 import BeautifulSoup
from retrying import retry
import os
import re

PAGE_RE = re.compile(r'<a href="(https://e-hentai\.org/s/\w+/[\w-]+)">')
IMG_RE = re.compile(r'<img id="img" src="(.*?)"')
TITLE_RE = re.compile(r'<h1 id="gn">(.*?)</h1>')

@retry(stop_max_attempt_number=10, wait_fixed=500)
def fetch_url(url, headers, session):
    response = session.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def download_images(url, save_dir, cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Cookie': cookies
    }
    session = requests.Session()
    content = fetch_url(url, headers, session)
    soup = BeautifulSoup(content, 'html.parser')

    title_match = TITLE_RE.search(content)
    if title_match:
        title = title_match.group(1)
        print(f"Gallery Title: {title}")
    else:
        title = 'e-hentai'
        print("Title not found, using default title.")

    image_page_links = list(PAGE_RE.findall(content))  # 使用列表保持顺序
    print(f"Found {len(image_page_links)} image page links.")
    if not image_page_links:
        print("No image page links found.")
        raise ValueError("Invalid URL or resource has been deleted.")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    for index, page_link in enumerate(image_page_links):
        print(f"Processing page link: {page_link}")
        try:
            page_content = fetch_url(page_link, headers, session)
            img_match = IMG_RE.search(page_content)
            if img_match:
                img_url = img_match.group(1)
                print(f"Found image URL: {img_url}")
                img_response = session.get(img_url, headers=headers)
                img_extension = os.path.splitext(img_url)[1]
                img_name = os.path.join(save_dir, f"{index + 1:03}{img_extension}")
                with open(img_name, 'wb') as f:
                    f.write(img_response.content)
                print(f"Downloaded {img_name}")
            else:
                print(f"No image found on page: {page_link}")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image from {page_link}: {e}")
    return title

# 示例使用
if __name__ == "__main__":
    cookies = "nw=1"
    title = download_images('https://e-hentai.org/g/2122174/fd2525031e', 'src\data\ehdownloader\cache', cookies)
    print(f"Gallery Title: {title}")