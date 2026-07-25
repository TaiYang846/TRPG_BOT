"""
關鍵字自動回應功能
------------------------
跟劇本查詢功能完全獨立，只負責一件事：
使用者傳的訊息裡如果「包含」某個關鍵字，機器人就自動回覆對應的內容。

資料存放在同目錄下的 keyword_replies.json，格式：
{
  "關鍵字1": "回覆內容1",
  "關鍵字2": "回覆內容2"
}

使用方式（在 bot.py 裡）：
    import keyword_replies
    keyword_replies.setup(client)

前提：機器人要能讀到訊息內容，需要在 Discord Developer Portal 開啟
「MESSAGE CONTENT INTENT」這個權限（Bot 分頁裡可以找到），
並且在建立 discord.Intents 時把 message_content 設成 True。
"""

import json
import os

import discord

KEYWORD_REPLIES_FILE = os.path.join(os.path.dirname(__file__), "keyword_replies.json")


def load_keyword_replies() -> dict:
    """讀取關鍵字對照表，檔案不存在或格式錯誤時回傳空字典，不會讓機器人崩潰"""
    if not os.path.exists(KEYWORD_REPLIES_FILE):
        print(f"⚠️ 找不到 {KEYWORD_REPLIES_FILE}，關鍵字自動回應功能會先跳過")
        return {}

    try:
        with open(KEYWORD_REPLIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"⚠️ 讀取 {KEYWORD_REPLIES_FILE} 失敗，關鍵字自動回應功能會先跳過：{e}")
        return {}


KEYWORD_REPLIES = load_keyword_replies()


def setup(client: discord.Client) -> None:
    """
    把「關鍵字自動回應」掛載到傳入的機器人（client）上。
    用 add_listener 而不是 @client.event，這樣就算 bot.py 之後也有自己的
    on_message，兩邊也不會互相覆蓋、可以同時運作。
    """

    async def on_message(message: discord.Message):
        # 不要回應機器人自己或其他機器人的訊息，不然可能會兩個機器人一直互相回覆
        if message.author.bot:
            return

        content = message.content
        for keyword, reply in KEYWORD_REPLIES.items():
            if keyword in content:
                await message.channel.send(reply)
                break  # 一則訊息只觸發第一個符合的關鍵字，避免洗版

    client.add_listener(on_message, "on_message")
    print(f"✅ 關鍵字自動回應已啟用，目前有 {len(KEYWORD_REPLIES)} 組關鍵字")
