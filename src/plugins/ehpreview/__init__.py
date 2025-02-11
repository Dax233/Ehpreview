from nonebot import get_plugin_config, on_message
from nonebot.plugin import PluginMetadata
from ..logger import model
from .config import Config
from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment, GroupMessageEvent
import re
import os
import json
import subprocess
import time

__plugin_meta__ = PluginMetadata(
    name="ehpreview",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

json_path = config.image_dir + '\\data.json'
image_dir = config.image_dir

# 读取本子信息
def load_json():
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# 保存本子信息
def save_json(data):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def create_combine_message(file_path, title, data, url):
    image_files = [os.path.join(file_path, f) for f in os.listdir(file_path) if f.endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    # 构造合并转发消息
    forward_nodes = [{
            "type": "node",
            "data": {
                "name": "ehdownloader",
                "uin": "1",
                "content": title
            }
        }]
    for image_file in image_files:
        forward_nodes.append({
            "type": "node",
            "data": {
                "name": "ehdownloader",
                "uin": "1",
                "content": MessageSegment.image(f'file:///{image_file}')
            }
        })
    if len(image_files) == 0:
        forward_nodes.append({
            "type": "node",
            "data": {
                "name": "ehdownloader",
                "uin": "1",
                "content": "图片获取失败，请稍后重试..."
            }
        })
        if os.path.exists(file_path):
            for filename in os.listdir(file_path):
                files_path = os.path.join(file_path, filename)
                if os.path.isfile(files_path):
                    os.remove(files_path)
            os.rmdir(file_path)
        data = load_json()
        del data[url]
        save_json(data)
    return forward_nodes

EHENTAI_RE = re.compile(r'https://e-hentai\.org/g/\d+/[\w-]+')
EXHENTAI_RE = re.compile(r'https://exhentai\.org/g/\d+/[\w-]+')
NHENTAI_RE = re.compile(r'https://nhentai\.(net|to)/g/\d+')
PIXIV_RE = re.compile(r'https://www\.pixiv\.net/artworks/\d+')

e_keyword = [EHENTAI_RE, EXHENTAI_RE, NHENTAI_RE, PIXIV_RE]
link_detector = on_message(rule=lambda event: isinstance(event, GroupMessageEvent))

@link_detector.handle()
async def handle_group_message(bot: Bot, event: Event):
    message = str(event.get_message())
    eurl = False
    isExist = False
    data = load_json()

    if 'mod' not in data:
        data = load_json()
        data['mod'] = {"mode":0, "E_COOKIE":config.E_COOKIE, "P_COOKIE": config.P_COOKIE}
        save_json(data)
    data = load_json()
    for key, value in data.items():
        if key != 'mod' and isinstance(value, dict):
            if value.get('mode') == 2 or value.get('mode') == 4:
                data = load_json()
                if value.get('mode') != 4:
                    data[key]["mode"] = 3
                save_json(data)
                isCreate = False
                respone = ''
                for group_id_key, message_ids in value.get('group_id', {}).items():
                    for message_id in message_ids:
                        print(f"{key}-{group_id_key}-{message_id}")
                        group_id = int(group_id_key)
                        file_path = os.path.abspath(image_dir + "\\" + data[key]['file_path'])
                        if  value.get('mode') == 4:
                            await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text(data[key]['title']))
                            model.save_message('group', group_id, event.get_user_id(), 'bot发出->触发者:', "[CQ:plugin,eh预览]")
                            continue
                        if not isCreate:
                            title = data[key]['title']
                            forward_nodes = create_combine_message(file_path, title, data , key)
                            isCreate = True
                            if forward_nodes:
                                try:
                                    respone = await bot.call_api("send_group_forward_msg", group_id=group_id, messages=forward_nodes, timeout=600)
                                except Exception as e:
                                    print(f"Error processing image: {e}")
                                    await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text("稍等片刻，也图图可能被麻花腾夹发不出来"))
                                await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text(title))
                            else:
                                print(group_id)
                                await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text("未找到任何图片。"))
                        else:
                            if respone != '':
                                try:
                                    forward_json = {
                                        "app": "com.tencent.multimsg",
                                        "config": {
                                            "autosize": 1,
                                            "forward": 1,
                                            "round": 1,
                                            "type": "normal",
                                            "width": 300
                                        },
                                        "desc": "[聊天记录]",
                                        "extra": "{\"filename\":\"5b04f3e5-f9f0-438d-a84f-f80ca37f43dc\",\"tsum\":2}\n",
                                        "meta": {
                                            "detail": {
                                                "news": [
                                                    {
                                                        "text": f"达Y: {data[key]['title']}"
                                                    },
                                                    {
                                                        "text": "达Y: [图片]"
                                                    }
                                                ],
                                                "resid": respone['forward_id'],
                                                "source": "达Y的聊天记录",
                                                "summary": "查看？条转发消息",
                                                "uniseq": "5b04f3e5-f9f0-438d-a84f-f80ca37f43dc"
                                            }
                                        },
                                        "prompt": "[聊天记录]",
                                        "ver": "0.0.0.5",
                                        "view": "contact"
                                    }
                                    forward_str = json.dumps(forward_json, ensure_ascii=False)
                                    await bot.send_group_msg(group_id=group_id, message=MessageSegment.json(forward_str))
                                except Exception as e:
                                    print(f"Error processing image: {e}")
                                    await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text("稍等片刻，也图图可能被麻花腾夹发不出来"))
                                await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text(title))
                            else:
                                print(group_id)
                                await bot.send_group_msg(group_id=group_id, message=MessageSegment.reply(message_id) + MessageSegment.text("未找到任何图片。"))
                        model.save_message('group', group_id, event.get_user_id(), 'bot发出->触发者:', "[CQ:plugin,eh预览]")
                data = load_json()
                data[key]["group_id"] = ''
                try:
                    data[key]["forward_id"] = respone['forward_id']
                except Exception as e:
                    pass
                save_json(data)
                if data[key]['mode'] == 4:
                    data = load_json()
                    del data[key]
                    save_json(data)


    if ('http' in message and '[CQ:json' in message) or ('http' in message and '[CQ:' not in message):
        url = extract_url(message)
        for i in e_keyword:
            if i.match(url):
                eurl = True
                if url in data:
                    isExist = True
                break
        if isExist :
            if data[url]['mode'] == 0:
                data = load_json()
                if str(event.group_id) in data[url]['group_id']:
                    data[url]['group_id'][str(event.group_id)].append(event.message_id)
                else:
                    data[url]['group_id'][str(event.group_id)] = []
                    data[url]['group_id'][str(event.group_id)].append(event.message_id)
                save_json(data)
                await bot.send(event, MessageSegment.reply(event.message_id) + MessageSegment.text("正在排队等待下载，下载完成后会自动发送，请稍等..."))
            elif data[url]['mode'] == 1:
                if str(event.group_id) in data[url]['group_id']:
                    data[url]['group_id'][str(event.group_id)].append(event.message_id)
                else:
                    data[url]['group_id'][str(event.group_id)] = []
                    data[url]['group_id'][str(event.group_id)].append(event.message_id)
                save_json(data)
                await bot.send(event, MessageSegment.reply(event.message_id) + MessageSegment.text("正在下载中，下载完成后会自动发送，请稍等..."))
            elif data[url]['mode'] == 2:
                if str(event.group_id) in data[url]['group_id']:
                    data[url]['group_id'][str(event.group_id)].append(event.message_id)
                else:
                    data[url]['group_id'][str(event.group_id)] = []
                    data[url]['group_id'][str(event.group_id)].append(event.message_id)
                save_json(data)
                await bot.send(event, MessageSegment.reply(event.message_id) + MessageSegment.text("正在等待发送，请稍后，请勿重复发送..."))
            elif data[url]['mode'] == 3:
                if 'forward_id' in data[url]:
                    try:
                        forward_json = {
                            "app": "com.tencent.multimsg",
                            "config": {
                                "autosize": 1,
                                "forward": 1,
                                "round": 1,
                                "type": "normal",
                                "width": 300
                            },
                            "desc": "[聊天记录]",
                            "extra": "{\"filename\":\"5b04f3e5-f9f0-438d-a84f-f80ca37f43dc\",\"tsum\":2}\n",
                            "meta": {
                                "detail": {
                                    "news": [
                                        {
                                            "text": f"达Y: {data[url]['title']}"
                                        },
                                        {
                                            "text": "达Y: [图片]"
                                        }
                                    ],
                                    "resid": data[url]['forward_id'],
                                    "source": "达Y的聊天记录",
                                    "summary": "查看？条转发消息",
                                    "uniseq": "5b04f3e5-f9f0-438d-a84f-f80ca37f43dc"
                                }
                            },
                            "prompt": "[聊天记录]",
                            "ver": "0.0.0.5",
                            "view": "contact"
                        }
                        forward_str = json.dumps(forward_json, ensure_ascii=False)
                        await bot.send_group_msg(group_id=event.group_id, message=MessageSegment.json(forward_str))
                    except Exception as e:
                        print(f"Error processing image: {e}")
                        await bot.send_group_msg(group_id=event.group_id, message=MessageSegment.reply(event.message_id) + MessageSegment.text("稍等片刻，也图图可能被麻花腾夹发不出来"))
                    await bot.send_group_msg(group_id=event.group_id, message=MessageSegment.reply(event.message_id) + MessageSegment.text(data[key]['title']))
                else:
                    file_path = os.path.abspath(image_dir + "\\" + data[url]['file_path'])
                    print(file_path)
                    title = data[url]['title']
                    forward_nodes = create_combine_message(file_path, title, data, url)
                    if forward_nodes:
                        try:
                            respone = await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=forward_nodes, timeout=600)
                        except Exception as e:
                            print(f"Error processing image: {e}")
                            await bot.send(event, MessageSegment.reply(event.message_id) + MessageSegment.text("被麻花腾夹了，图图发不出来"))
                        await bot.send(event, MessageSegment.reply(event.message_id) + MessageSegment.text(title))
                    else:
                        await bot.send(event, MessageSegment.reply(event.message_id) + MessageSegment.text("未找到任何图片。"))
                    data = load_json()
                    data[url]["forward_id"] = respone['forward_id']
                    save_json(data)
            model.save_message('private' if event.is_tome() else 'group', getattr(event, 'group_id', None), event.get_user_id(), 'bot发出->触发者:', "[CQ:plugin,eh预览]")
            return

        if eurl:
            data = load_json()
            data[url] = {
                "mode": 0,
                "file_path": str(int(round(time.time() * 1000))),
                "group_id": {
                    f"{event.group_id}": []
                },
                "title": ''
                }
            data[url]['group_id'][str(event.group_id)].append(event.message_id)
            save_json(data)
    isRun = False
    data = load_json()
    if data['mod']['mode'] == 0:
                isRun = True
                data['mod']['mode'] = 1
                save_json(data)
    if isRun:
                subprocess.run(['start', '/min',  'cmd', '/c', 'python', f'{config.src_dir}/downloader.py'], shell=True)


def extract_links(text):
    # 正则表达式匹配URL
    pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    # 查找所有匹配的URL
    links = re.findall(pattern, text)
    return links[0]

def extract_url(message: str) -> str:
    # 提取消息中的URL，忽略CQ码中的链接
    url = extract_links(message)
    if '[CQ:' in url:
        return None
    return url