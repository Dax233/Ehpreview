import re
from PIL import Image, ImageDraw, ImageFont
import sys
import os
import json
import time

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取父目录
parent_dir = os.path.dirname(current_dir)
# 将父目录添加到 sys.path
sys.path.append(parent_dir)

from e_hentai import download_images as download_e_hentai_images
from exhentai import download_images as download_exhentai_images
from nhentai import download_images as download_nhentai_images
from pixiv import download_images as download_pixiv_images

# Regular expressions to match different types of URLs
EHENTAI_RE = re.compile(r'https://e-hentai\.org/g/\d+/[\w-]+')
EXHENTAI_RE = re.compile(r'https://exhentai\.org/g/\d+/[\w-]+')
NHENTAI_RE = re.compile(r'https://nhentai\.(net|to)/g/\d+')
PIXIV_RE = re.compile(r'https://www\.pixiv\.net/artworks/\d+')

json_path = current_dir + '/cache/data.json'

def add_watermark(image_path, watermark_text=f"刻上属于你的痕迹 {time.localtime}", font_path="src/fonts/lolita.ttf"):
    base = Image.open(image_path).convert('RGBA')
    width, height = base.size

    # Create a transparent overlay
    txt = Image.new('RGBA', base.size, (255, 255, 255, 0))

    # Load the font
    font_size = 36  # You can adjust the font size as needed
    font = ImageFont.truetype(font_path, font_size)
    draw = ImageDraw.Draw(txt)

    # Position the text at the bottom right
    text_width, text_height = draw.textsize(watermark_text, font)
    position = (width - text_width - 10, height - text_height - 10)

    # Apply the text to the overlay
    draw.text(position, watermark_text, fill=(255, 255, 255, 128), font=font)

    # Combine the base image with the overlay
    watermarked = Image.alpha_composite(base, txt)

    # Save the result
    parts = image_path.split('.')
    if parts[1] == 'jpeg' or parts[1] == 'jpg' or parts[1] == 'webp':
        new_path = parts[0] + '.png'
        watermarked.save(new_path)
        os.remove(image_path)
        image_path = new_path
    else:
        watermarked.save(image_path)
    return image_path

def download_images(url, save_dir):
    if EHENTAI_RE.match(url):
        print("Detected e-hentai URL")
        title = download_e_hentai_images(url, save_dir, e_COOKIE)
    elif EXHENTAI_RE.match(url):
        print("Detected exhentai URL")
        title = download_exhentai_images(url, save_dir, e_COOKIE)
    elif NHENTAI_RE.match(url):
        print("Detected nhentai URL")
        title = download_nhentai_images(url, save_dir, e_COOKIE)
    elif PIXIV_RE.match(url):
        print("Detected Pixiv URL")
        title = download_pixiv_images(url, save_dir, p_COOKIE)
    else:
        return '暂不支持'
    
    
    # Add watermark to all images in save_dir
    try:
        for filename in os.listdir(save_dir):
            if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                add_watermark(os.path.join(save_dir, filename))
    except Exception as e:
        print(f'Floder Not Exist: {e}')
        data = load_json()
        data[url]['mode'] = 4
        save_json(data)
    
    return title

# 读取本子信息
def load_json():
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# 保存本子信息
def save_json(data):
    print("save process")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

data = load_json()
# print("data:" + str(data))
e_COOKIE = data['mod']['E_COOKIE']
p_COOKIE = data['mod']['P_COOKIE']

# 保留最近三十份资源与未下载完成文件
for key, value in data.items():
    if key != 'mod' and isinstance(value, dict):
        if value.get('mode') == 1:
            data = load_json()
            folder_path = current_dir + '/cache/' + data[key]['file_path']
            if os.path.exists(folder_path):
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                os.rmdir(folder_path)
            data = load_json()
            del data[key]
            save_json(data)
data = load_json()
sorted_keys = sorted(data.keys(), key=lambda k: int(data[k]['file_path']) if k != 'mod' and isinstance(data[k], dict) else 0, reverse=True)
for key in sorted_keys[10:]:
    data = load_json()
    if key != 'mod' and isinstance(data[key], dict):
        folder_path = current_dir + '/cache/' + data[key]['file_path']
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            os.rmdir(folder_path)
        data = load_json()
        del data[key]
        save_json(data)


for key, value in data.items():
    if key != 'mod' and isinstance(value, dict):
        if value.get('mode') == 0:
            data = load_json()
            data[key]['mode'] = 1
            save_json(data)
            title = download_images(key, current_dir + '/cache/' + data[key]['file_path'])
            data = load_json()
            data[key]['title'] = title
            if data[key]['mode'] != 4:
                data[key]['mode'] = 2
            save_json(data)
data = load_json()
data['mod']['mode'] = 0
save_json(data)
