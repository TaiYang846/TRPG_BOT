"""
關鍵字自動回應功能
------------------------
跟劇本查詢功能完全獨立，只負責一件事：
使用者傳的訊息裡如果「包含」某個關鍵字，機器人就自動從對應的回覆清單裡
隨機挑一句回覆。

資料存放在同目錄下的 keyword_replies.json，格式：
{
  "關鍵字1": ["回覆內容1-A", "回覆內容1-B", "回覆內容1-C"],
  "關鍵字2": ["回覆內容2-A", "回覆內容2-B"]
}

如果只想要固定回覆一句（不用隨機），也可以直接寫成字串，效果一樣：
{
  "關鍵字3": "固定回覆內容3"
}

注意：JSON 格式裡「同一個 key 不能重複」，如果同一個關鍵字想要多種回覆，
不要複製貼上兩組同名的關鍵字（後面那組會直接蓋掉前面的），
而是把好幾句回覆放進同一個關鍵字的清單（陣列）裡，像上面的範例一樣。

使用方式（在 bot.py 裡）：
    import keyword_replies
    keyword_replies.setup(client)

前提：機器人要能讀到訊息內容，需要在 Discord Developer Portal 開啟
「MESSAGE CONTENT INTENT」這個權限（Bot 分頁裡可以找到），
並且在建立 discord.Intents 時把 message_content 設成 True。
"""

import json
import os
import random

import discord

KEYWORD_REPLIES_FILE = os.path.join(os.path.dirname(__file__), "keyword_replies.json")


def load_keyword_replies() -> dict:
    """
    讀取關鍵字對照表，檔案不存在或格式錯誤時回傳空字典，不會讓機器人崩潰。
    把每一組回覆都統一轉成清單（list），這樣不管使用者是寫單一字串
    還是寫好幾句的陣列，後面的程式碼都能用同一種方式處理。
    """
    if not os.path.exists(KEYWORD_REPLIES_FILE):
        print(f"⚠️ 找不到 {KEYWORD_REPLIES_FILE}，關鍵字自動回應功能會先跳過")
        return {}

    try:
        with open(KEYWORD_REPLIES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"⚠️ 讀取 {KEYWORD_REPLIES_FILE} 失敗，關鍵字自動回應功能會先跳過：{e}")
        return {}

    normalized = {}
    for keyword, replies in raw.items():
        if isinstance(replies, str):
            normalized[keyword] = [replies]
        elif isinstance(replies, list) and replies:
            normalized[keyword] = [str(r) for r in replies]
        else:
            print(f"⚠️ 關鍵字「{keyword}」的回覆格式看不懂，已略過這一組")
    return normalized


KEYWORD_REPLIES = load_keyword_replies()


def setup(client: discord.Client) -> None:
    """
    把「關鍵字自動回應」掛載到傳入的機器人（client）上。

    注意：discord.Client（我們用的這種比較單純的機器人類別）本身沒有
    add_listener 這個方法，那個是 discord.ext.commands.Bot 才有的東西。
    這裡改用 client.event(...)，這是 discord.Client 本身就支援、
    用來註冊事件處理函式的正確寫法（它會依照函式名稱 on_message
    自動綁定，不需要另外指定事件名稱字串）。
    """

    async def on_message(message: discord.Message):
        # 不要回應機器人自己或其他機器人的訊息，不然可能會兩個機器人一直互相回覆
        if message.author.bot:
            return

        content = message.content
        for keyword, replies in KEYWORD_REPLIES.items():
            if keyword in content:
                await message.channel.send(random.choice(replies))
                break  # 一則訊息只觸發第一個符合的關鍵字，避免洗版

    client.event(on_message)
    print(f"✅ 關鍵字自動回應已啟用，目前有 {len(KEYWORD_REPLIES)} 組關鍵字")
