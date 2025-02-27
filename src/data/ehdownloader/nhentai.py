import requests
from retrying import retry
import os
import re
import random

NHAPI = "https://nhapi.cat42.uk/gallery/"
NHOAPI = 'https://nhentai.net/api/gallery/'
NH_CDN_LIST = [
    "https://i1.nhentai.net/galleries",
    "https://i2.nhentai.net/galleries",
    "https://i3.nhentai.net/galleries",
    "https://i4.nhentai.net/galleries",
]

@retry(stop_max_attempt_number=5, wait_fixed=200)
def fetch_url(url, headers, session):
    response = session.get(url, headers=headers)
    if response.status_code != 200:
        return "!200" ,f"无法访问该链接，状态码: {response.status_code}"
    response.raise_for_status()
    return response.json(), None

def download_images(url, save_dir, cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Cookie': cookies
    }
    session = requests.Session()
    proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "https://127.0.0.1:7890"
    }
    session.proxies.update(proxies)
    
    # Normalize URL
    parts = url.strip('/').split('/')
    if len(parts) < 3 or parts[3] != 'g':
        raise ValueError(f"Invalid input path({url}), gallery URL is expected (like https://nhentai.net/g/333678)")
    
    album_id = parts[4]
    api_url = f"{NHAPI}{album_id}"
    o_api_url = f"{NHOAPI}{album_id}"
    original_url = f"https://nhentai.net/g/{album_id}"
    print(f"[nhentai] process {api_url} (original URL {original_url})")

    # Fetch album data
    album, error = fetch_url(api_url, headers, session)
    if error == "无法访问该链接，状态码: 404":
        print(f"[nhentai] process {o_api_url} (original URL {original_url})")
        # Fetch album data
        album, error = fetch_url(o_api_url, headers, session)
    if album == '!200':
        return error
    title = album['title'].get('pretty') or album['title'].get('english') or album['title'].get('japanese') or f"nhentai-{album_id}"
    print(f"Gallery Title: {title}")

    image_page_links = [
        f"{random.choice(NH_CDN_LIST)}/{album['media_id']}/{idx + 1}{image_type_to_extension(image['t'])}"
        for idx, image in enumerate(album['images']['pages'])
    ]
    print(f"Found {len(image_page_links)} image page links.")
    if not image_page_links:
        print("No image page links found.")
        raise ValueError("Invalid URL or resource has been deleted.")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    for index, img_url in enumerate(image_page_links):
        print(f"Processing image URL: {img_url}")
        try:
            img_response = session.get(img_url, headers=headers)
            img_extension = os.path.splitext(img_url)[1]
            img_name = os.path.join(save_dir, f"{index + 1:03}{img_extension}")
            with open(img_name, 'wb') as f:
                f.write(img_response.content)
            print(f"Downloaded {img_name}")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image from {img_url}: {e}")

    return title

def image_type_to_extension(image_type):
    if image_type == 'j':
        return '.jpg'
    elif image_type == 'p':
        return '.png'
    elif image_type == 'g':
        return '.gif'
    elif image_type == 'w':
        return '.webp'
    else:
        return ''

# 示例使用
if __name__ == "__main__":
    cookies = "ipb_pass_hash=your_ipb_pass_hash;ipb_member_id=your_ipb_member_id;igneous=your_igneous;nw=1"
    download_images('https://nhentai.net/g/333678', './images', cookies)
