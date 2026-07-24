"""
跑團伺服器劇本查詢機器人
------------------------
功能：
1. /劇本 [名稱]     -> 查詢指定劇本的詳細資訊
2. /劇本列表         -> 列出所有目前收錄的劇本名稱
3. /劇本資訊         -> 在劇本對應的頻道或論壇貼文內使用，自動判斷目前所在的
                     頻道對應哪個劇本，不用輸入名稱
4. /ho診斷          -> 在劇本對應的頻道或論壇貼文內使用，自動回覆這個劇本對應的 HO 診斷網址
5. /npc介紹         -> 在劇本對應的頻道或論壇貼文內使用，自動列出這個劇本的所有 NPC
6. /npc [名稱]      -> 查詢指定 NPC 的介紹，不限定要在哪篇貼文都能查
7. /抽劇本          -> 從所有收錄的劇本裡隨機抽一個出來
8. /人數 [人數]      -> 依照遊玩人數，列出支援該人數遊玩的劇本

注意：/劇本資訊、/ho診斷、/npc介紹 都需要你的頻道名稱（一般文字頻道、
語音頻道或論壇貼文標題都可以）跟 scenarios 資料夾裡的劇本檔名「相同」
或「包含」該名稱，機器人才找得到對應的劇本。

劇本資料存放方式：
每個劇本是 scenarios/ 資料夾底下的一個獨立 .json 檔案，
檔名（去掉 .json）就是劇本名稱，例如 scenarios/血染鐘樓.json。

使用前請先：
1. pip install -r requirements.txt
2. 把 .env.example 複製成 .env，填入你的機器人 Token
3. python bot.py
"""

import glob
import json
import os
import random

import discord
from discord import app_commands
from dotenv import load_dotenv

# 讀取 .env 檔案中的 Token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

SCENARIOS_DIR = "scenarios"


def load_scenarios():
    """
    掃描 scenarios 資料夾底下的每一個 .json 檔案，
    把「檔名（去掉 .json）」當作劇本名稱，內容當作劇本資料。
    例如：scenarios/血染鐘樓.json -> 劇本名稱就是「血染鐘樓」
    """
    scenarios = {}
    for filepath in glob.glob(os.path.join(SCENARIOS_DIR, "*.json")):
        scenario_name = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                scenarios[scenario_name] = json.load(f)
            except json.JSONDecodeError as e:
                # 單一檔案格式錯誤時，只會影響這一個劇本，不會讓整個機器人壞掉
                print(f"⚠️ 讀取 {filepath} 失敗，這個劇本會先跳過：{e}")
    return scenarios

SCENARIOS = load_scenarios()

# 設定機器人權限
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    # 同步斜線指令到 Discord（第一次啟動可能要等 1 分鐘左右才會顯示）
    await tree.sync()
    print(f"機器人已上線：{client.user}")


def format_player_count(data: dict) -> str:
    """把 players_min / players_max 組成好看的顯示文字，例如「3-5人」或「1人」"""
    p_min = data.get("players_min")
    p_max = data.get("players_max")
    if p_min is None or p_max is None:
        return ""
    return f"{p_min}人" if p_min == p_max else f"{p_min}-{p_max}人"


def build_scenario_embed(name: str, data: dict) -> discord.Embed:
    """把單一劇本資料組成漂亮的 Embed 訊息"""
    embed = discord.Embed(
        title=name,
        url=data.get("url") or None,
        description=data.get("slogan", ""),
        color=0x8B5CF6,
    )

    if data.get("author"):
        embed.add_field(name="✍️ 作者", value=data["author"], inline=True)

    player_count_text = format_player_count(data)
    if player_count_text:
        embed.add_field(name="🎲 遊玩人數", value=player_count_text, inline=True)

    if data.get("background"):
        embed.add_field(name="📖 背景", value=data["background"], inline=False)

    if data.get("summary"):
        embed.add_field(name="🌟 概要", value=data["summary"], inline=False)
  
    if data.get("public_ho"):
        embed.add_field(name="🎭 公開HO", value=data["public_ho"], inline=False)

    if data.get("warning") and data["warning"] != "無":
        embed.add_field(name="⚠️ 注意事項", value=data["warning"], inline=False)

    if data.get("other"):
        embed.add_field(name="📌 其他", value=data["other"], inline=False)

    if data.get("image"):
        embed.set_image(url=data["image"])

    return embed


def find_scenario_by_channel_name(channel_name: str):
    """
    用「目前所在頻道」的名稱比對劇本資料（不限論壇討論串，一般文字頻道也適用）。
    先找完全相同的名稱，找不到再找「頻道名稱裡有包含劇本名稱或別名」的情況，
    這樣就算頻道名稱多加了編號、emoji，或名稱是用別名（例如中文翻譯）
    寫的，也還是抓得到。
    """
    if channel_name in SCENARIOS:
        return channel_name, SCENARIOS[channel_name]

    for name, data in SCENARIOS.items():
        if name in channel_name:
            return name, data
        if any(alias in channel_name for alias in data.get("aliases", [])):
            return name, data

    return None, None


async def resolve_scenario_from_channel(interaction: discord.Interaction, hint: str = "") -> tuple:
    """
    從目前所在的頻道（一般文字頻道、語音頻道、論壇討論串都適用）
    找出對應的劇本。如果目前頻道是「某個頻道底下的討論串」（例如在一般
    文字頻道裡開的子討論串），而討論串本身的名稱比對不到劇本，會再往上
    用「父頻道的名稱」試一次（例如頻道叫「血染鐘樓」，底下開的討論串叫
    「場外」也能抓到）。
    如果頻道沒有名稱、或找不到對應劇本，會直接回覆錯誤訊息給使用者，
    並回傳 (None, None)；成功的話回傳 (劇本名稱, 劇本資料)。
    """
    channel = interaction.channel
    channel_name = getattr(channel, "name", None)

    if not channel_name:
        await interaction.response.send_message(
            f"這個指令要在有名稱的頻道（文字頻道、語音頻道或論壇貼文）裡面用喔！{hint}",
            ephemeral=True,
        )
        return None, None

    name, data = find_scenario_by_channel_name(channel_name)

    # 目前頻道名稱比對不到，且這是一個討論串的話，再試著用父頻道名稱比對一次
    if not data and isinstance(channel, discord.Thread) and channel.parent is not None:
        parent_name = getattr(channel.parent, "name", None)
        if parent_name:
            name, data = find_scenario_by_channel_name(parent_name)

    if not data:
        await interaction.response.send_message(
            f"找不到跟這個頻道名稱「{channel_name}」對應的劇本資料喔！"
            "請確認 scenarios 資料夾裡有沒有同名或標題包含該劇本名稱的檔案"
            "（如果你是在某個頻道底下的討論串裡打指令，也可以確認一下父頻道的名稱有沒有對上）。",
            ephemeral=True,
        )
        return None, None

    return name, data


def scenario_matches_keyword(name: str, data: dict, keyword: str) -> bool:
    """
    判斷一個劇本是否符合關鍵字：
    - 比對正式名稱（scenario_name 本身）
    - 也比對 aliases 欄位裡的每一個別名（可以放中文翻譯、簡稱等）
    """
    if keyword in name:
        return True
    return any(keyword in alias for alias in data.get("aliases", []))


def search_scenarios_by_keyword(keyword: str):
    """
    用關鍵字搜尋劇本名稱（含別名），不用打完整名稱也能找到：
    1. 先找正式名稱完全相同的
    2. 找不到的話，找「名稱或別名裡有包含關鍵字」的（可能會有多筆符合）
    回傳符合的 (名稱, 資料) 清單
    """
    if keyword in SCENARIOS:
        return [(keyword, SCENARIOS[keyword])]

    return [
        (name, data) for name, data in SCENARIOS.items()
        if scenario_matches_keyword(name, data, keyword)
    ]


@tree.command(name="劇本", description="查詢指定劇本的詳細資訊（可只打關鍵字）")
@app_commands.describe(名稱="想查詢的劇本名稱，可以只打部分關鍵字")
async def scenario_info(interaction: discord.Interaction, 名稱: str):
    matches = search_scenarios_by_keyword(名稱)

    if not matches:
        # 找不到時，順便提示有哪些劇本可以選
        available = "、".join(SCENARIOS.keys()) or "（目前還沒有收錄任何劇本）"
        await interaction.response.send_message(
            f"找不到包含「{名稱}」的劇本喔！目前收錄的劇本有：{available}",
            ephemeral=True,
        )
        return

    if len(matches) > 1:
        # 關鍵字比對到不只一個劇本時，列出來讓使用者確認要打更精確的名稱
        names = "、".join(name for name, _ in matches)
        await interaction.response.send_message(
            f"「{名稱}」符合好幾個劇本，麻煩打更精確一點的名稱喔！符合的有：{names}",
            ephemeral=True,
        )
        return

    matched_name, data = matches[0]
    await interaction.response.send_message(embed=build_scenario_embed(matched_name, data))


@scenario_info.autocomplete("名稱")
async def scenario_info_autocomplete(interaction: discord.Interaction, current: str):
    """打字的時候即時跳出符合關鍵字（含別名）的劇本名稱建議（最多顯示 25 筆，這是 Discord 的上限）"""
    current_lower = current.lower()
    choices = []
    for name, data in SCENARIOS.items():
        if scenario_matches_keyword(name.lower(), data, current_lower):
            # 如果是靠別名比對到的，顯示「正式名稱（別名）」讓使用者知道為什麼會跳出這筆
            matched_alias = next(
                (a for a in data.get("aliases", []) if current_lower in a.lower()),
                None,
            ) if current_lower not in name.lower() else None
            display = f"{name}（{matched_alias}）" if matched_alias else name
            choices.append(app_commands.Choice(name=display[:100], value=name))

    return choices[:25]


@tree.command(name="劇本資訊", description="在劇本對應的頻道或論壇貼文內使用，自動顯示對應的劇本資訊")
async def scenario_info_auto(interaction: discord.Interaction):
    name, data = await resolve_scenario_from_channel(
        interaction, hint="如果你是想指定名稱查詢，請改用 `/劇本 名稱`。"
    )
    if not data:
        return

    await interaction.response.send_message(embed=build_scenario_embed(name, data))


@tree.command(name="ho診斷", description="在劇本對應的頻道或論壇貼文內使用，回覆這個劇本對應的 HO 診斷網址")
async def ho_check(interaction: discord.Interaction):
    name, data = await resolve_scenario_from_channel(interaction)
    if not data:
        return

    ho_url = data.get("ho_url")
    if not ho_url:
        await interaction.response.send_message(
            f"「{name}」目前還沒有設定 HO 診斷網址喔！可以到 scenarios/{name}.json 補上 ho_url 欄位。",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(f"🔮 **{name}** 的 HO 診斷：\n{ho_url}")


def parse_npc_data(npc_value) -> dict:
    """
    統一處理 NPC 的資料格式，讓新舊寫法都能相容：
    - 舊格式：npc_value 直接是一個字串（純文字介紹，沒有圖片）
    - 新格式：npc_value 是 {"description": "...", "image": "https://..."}
    """
    if isinstance(npc_value, str):
        return {"description": npc_value, "image": None}
    return {
        "description": npc_value.get("description", ""),
        "image": npc_value.get("image") or None,
    }


def build_npc_embed(npc_name: str, npc_value, subtitle: str = "") -> discord.Embed:
    """把單一 NPC 組成一張獨立的 Embed 卡片，如果有設定 image 就會顯示圖片"""
    info = parse_npc_data(npc_value)
    title = f"{npc_name}" + (f"（{subtitle}）" if subtitle else "")
    embed = discord.Embed(title=title, description=info["description"], color=0x22C55E)
    if info["image"]:
        embed.set_image(url=info["image"])
    return embed


@tree.command(name="npc介紹", description="在劇本對應的頻道或論壇貼文內使用，列出這個劇本的所有 NPC")
async def npc_list_auto(interaction: discord.Interaction):
    name, data = await resolve_scenario_from_channel(interaction)
    if not data:
        return

    npcs = data.get("npcs")
    if not npcs:
        await interaction.response.send_message(
            f"「{name}」目前還沒有登錄任何 NPC 資料喔！可以到 scenarios/{name}.json 補上 npcs 欄位。",
            ephemeral=True,
        )
        return

    # 每個 NPC 各自一張卡片，一則訊息最多可以放 10 張卡片
    embeds = [build_npc_embed(npc_name, npc_value) for npc_name, npc_value in npcs.items()][:10]

    await interaction.response.send_message(
        content=f"**{name}** — NPC 介紹", embeds=embeds
    )


@tree.command(name="npc", description="查詢指定 NPC 的介紹，不限定要在哪篇貼文都能查")
@app_commands.describe(名稱="想查詢的 NPC 名稱")
async def npc_search(interaction: discord.Interaction, 名稱: str):
    # 跨所有劇本尋找同名或名稱包含輸入文字的 NPC
    matches = []
    for scenario_name, data in SCENARIOS.items():
        for npc_name, npc_value in data.get("npcs", {}).items():
            if 名稱 in npc_name:
                matches.append((scenario_name, npc_name, npc_value))

    if not matches:
        await interaction.response.send_message(
            f"找不到名稱包含「{名稱}」的 NPC 喔！", ephemeral=True
        )
        return

    embeds = [
        build_npc_embed(npc_name, npc_value, subtitle=f"出自：{scenario_name}")
        for scenario_name, npc_name, npc_value in matches
    ][:10]

    await interaction.response.send_message(embeds=embeds)


@tree.command(name="劇本列表", description="列出所有目前收錄的劇本")
async def scenario_list(interaction: discord.Interaction):
    if not SCENARIOS:
        await interaction.response.send_message("目前還沒有收錄任何劇本喔！")
        return

    lines = [f"• **{name}**（作者：{data.get('author', '未知')}）" for name, data in SCENARIOS.items()]
    await interaction.response.send_message("目前收錄的劇本：\n" + "\n".join(lines))


@tree.command(name="人數", description="依照遊玩人數列出符合的劇本")
@app_commands.describe(人數="想找的遊玩人數，例如打 4 會列出支援 4 人遊玩的劇本")
async def scenario_by_players(interaction: discord.Interaction, 人數: int):
    matches = [
        (name, data) for name, data in SCENARIOS.items()
        if data.get("players_min") is not None
        and data.get("players_max") is not None
        and data["players_min"] <= 人數 <= data["players_max"]
    ]

    if not matches:
        await interaction.response.send_message(
            f"目前沒有找到支援 {人數} 人遊玩的劇本喔！", ephemeral=True
        )
        return

    lines = [
        f"• **{name}**（{format_player_count(data)}，作者：{data.get('author', '未知')}）"
        for name, data in matches
    ]
    await interaction.response.send_message(
        f"支援 {人數} 人遊玩的劇本：\n" + "\n".join(lines)
    )


@tree.command(name="抽劇本", description="從所有收錄的劇本裡隨機抽一個")
async def scenario_random(interaction: discord.Interaction):
    if not SCENARIOS:
        await interaction.response.send_message("目前還沒有收錄任何劇本喔，沒辦法抽！")
        return

    name = random.choice(list(SCENARIOS.keys()))
    data = SCENARIOS[name]
    await interaction.response.send_message(
        content="🎲 隨機抽到的劇本是：", embed=build_scenario_embed(name, data)
    )


client.run(TOKEN)
