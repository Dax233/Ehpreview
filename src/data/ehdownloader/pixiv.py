import requests
import os
import re
from bs4 import BeautifulSoup

def extract_artwork_id(url):
    match = re.search(r'artworks/(\d+)', url)
    if match:
        return match.group(1)
    else:
        raise ValueError("Invalid Pixiv URL")

def clean_description(description):
    soup = BeautifulSoup(description, 'html.parser')
    text = soup.get_text(separator='\n')
    return text

def download_images(url, save_dir, cookies):
    artwork_id = extract_artwork_id(url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Cookie': cookies,
        'Referer': 'https://www.pixiv.net/'
    }
    api_url = f'https://www.pixiv.net/ajax/illust/{artwork_id}/pages'
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        return f"无法访问该链接，状态码: {response.status_code}"
    response.raise_for_status()
    data = response.json()

    # 获取作品详细信息
    details_url = f'https://www.pixiv.net/ajax/illust/{artwork_id}'
    details_response = requests.get(details_url, headers=headers)
    details_response.raise_for_status()
    details_data = details_response.json()

    title = details_data['body']['title']
    author = details_data['body']['userName']
    description = clean_description(details_data['body']['description'])

    print(f"Gallery Title: {title}")

    image_urls = [page['urls']['original'] for page in data['body']]
    print(f"Found {len(image_urls)} image URLs.")
    if not image_urls:
        print("No image URLs found.")
        raise ValueError("Invalid URL or resource has been deleted.")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    for index, img_url in enumerate(image_urls):
        print(f"Processing image URL: {img_url}")
        try:
            img_response = requests.get(img_url, headers=headers)
            img_extension = os.path.splitext(img_url)[1]
            img_name = os.path.join(save_dir, f"{index + 1:03}{img_extension}")
            with open(img_name, 'wb') as f:
                f.write(img_response.content)
            print(f"Downloaded {img_name}")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image from {img_url}: {e}")

    return f"作品名：{title}\n作者：{author}\n简介：{description}"

# 示例使用
if __name__ == "__main__":
    cookies = "your_pixiv_cookies"
    result = download_images('https://www.pixiv.net/artworks/105231364', './images', cookies)
    print(result)
