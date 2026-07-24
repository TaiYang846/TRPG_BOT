"""
跑團伺服器劇本查詢機器人
------------------------
功能：
1. /劇本 [名稱]     -> 查詢指定劇本的詳細資訊
2. /劇本列表         -> 列出所有目前收錄的劇本名稱
3. /劇本資訊         -> 在論壇貼文（討論串）內使用，自動判斷目前所在的討論串
                     對應哪個劇本，不用輸入名稱
4. /HO診斷          -> 在論壇貼文內使用，自動回覆這個劇本對應的 HO 診斷網址
5. /NPC介紹         -> 在論壇貼文內使用，自動列出這個劇本的所有 NPC
6. /NPC [名稱]      -> 查詢指定 NPC 的介紹，不限定要在哪篇貼文都能查

注意：/劇本資訊、/HO診斷、/NPC介紹 都需要你的論壇貼文標題跟
scenarios.json 裡的劇本名稱「相同」或「包含」該名稱，機器人才找得到
對應的劇本。

使用前請先：
1. pip install -r requirements.txt
2. 把 .env.example 複製成 .env，填入你的機器人 Token
3. python bot.py
"""

import json
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

# 讀取 .env 檔案中的 Token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 讀取劇本資料
def load_scenarios():
    with open("scenarios.json", "r", encoding="utf-8") as f:
        return json.load(f)

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


def build_scenario_embed(name: str, data: dict) -> discord.Embed:
    """把單一劇本資料組成漂亮的 Embed 訊息"""
    embed = discord.Embed(title=name, description=data["summary"], color=0x8B5CF6)
    embed.add_field(name="系統", value=data["system"], inline=True)
    embed.add_field(name="人數", value=data["players"], inline=True)
    embed.add_field(name="時長", value=data["duration"], inline=True)
    if data.get("warning") and data["warning"] != "無":
        embed.add_field(name="⚠️ 注意事項", value=data["warning"], inline=False)
    return embed


def find_scenario_by_thread_name(thread_name: str):
    """
    用討論串（論壇貼文）標題比對劇本資料。
    先找完全相同的名稱，找不到再找「標題裡有包含劇本名稱」的情況，
    這樣就算貼文標題多加了編號、emoji 也還是抓得到。
    """
    if thread_name in SCENARIOS:
        return thread_name, SCENARIOS[thread_name]

    for name, data in SCENARIOS.items():
        if name in thread_name:
            return name, data

    return None, None


async def resolve_scenario_from_thread(interaction: discord.Interaction, hint: str = "") -> tuple:
    """
    從目前所在的論壇貼文（討論串）找出對應的劇本。
    如果不在討論串裡、或找不到對應劇本，會直接回覆錯誤訊息給使用者，
    並回傳 (None, None)；成功的話回傳 (劇本名稱, 劇本資料)。
    """
    channel = interaction.channel

    if not isinstance(channel, discord.Thread):
        await interaction.response.send_message(
            f"這個指令要在論壇貼文（討論串）裡面用喔！{hint}",
            ephemeral=True,
        )
        return None, None

    name, data = find_scenario_by_thread_name(channel.name)

    if not data:
        await interaction.response.send_message(
            f"找不到跟這篇貼文標題「{channel.name}」對應的劇本資料喔！"
            "請確認 scenarios.json 裡有沒有同名或標題包含該劇本名稱的資料。",
            ephemeral=True,
        )
        return None, None

    return name, data


@tree.command(name="劇本", description="查詢指定劇本的詳細資訊")
@app_commands.describe(名稱="想查詢的劇本名稱")
async def scenario_info(interaction: discord.Interaction, 名稱: str):
    data = SCENARIOS.get(名稱)

    if not data:
        # 找不到時，順便提示有哪些劇本可以選
        available = "、".join(SCENARIOS.keys())
        await interaction.response.send_message(
            f"找不到「{名稱}」這個劇本喔！目前收錄的劇本有：{available}",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(embed=build_scenario_embed(名稱, data))


@tree.command(name="劇本資訊", description="在論壇貼文內使用，自動顯示這篇貼文對應的劇本資訊")
async def scenario_info_auto(interaction: discord.Interaction):
    name, data = await resolve_scenario_from_thread(
        interaction, hint="如果你是想指定名稱查詢，請改用 `/劇本 名稱`。"
    )
    if not data:
        return

    await interaction.response.send_message(embed=build_scenario_embed(name, data))


@tree.command(name="HO診斷", description="在論壇貼文內使用，回覆這個劇本對應的 HO 診斷網址")
async def ho_check(interaction: discord.Interaction):
    name, data = await resolve_scenario_from_thread(interaction)
    if not data:
        return

    ho_url = data.get("ho_url")
    if not ho_url:
        await interaction.response.send_message(
            f"「{name}」目前還沒有設定 HO 診斷網址喔！可以到 scenarios.json 補上 ho_url 欄位。",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(f"🔮 **{name}** 的 HO 診斷：\n{ho_url}")


@tree.command(name="NPC介紹", description="在論壇貼文內使用，列出這個劇本的所有 NPC")
async def npc_list_auto(interaction: discord.Interaction):
    name, data = await resolve_scenario_from_thread(interaction)
    if not data:
        return

    npcs = data.get("npcs")
    if not npcs:
        await interaction.response.send_message(
            f"「{name}」目前還沒有登錄任何 NPC 資料喔！可以到 scenarios.json 補上 npcs 欄位。",
            ephemeral=True,
        )
        return

    embed = discord.Embed(title=f"{name} — NPC 介紹", color=0x22C55E)
    for npc_name, description in npcs.items():
        embed.add_field(name=npc_name, value=description, inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="NPC", description="查詢指定 NPC 的介紹，不限定要在哪篇貼文都能查")
@app_commands.describe(名稱="想查詢的 NPC 名稱")
async def npc_search(interaction: discord.Interaction, 名稱: str):
    # 跨所有劇本尋找同名或名稱包含輸入文字的 NPC
    matches = []
    for scenario_name, data in SCENARIOS.items():
        for npc_name, description in data.get("npcs", {}).items():
            if 名稱 in npc_name:
                matches.append((scenario_name, npc_name, description))

    if not matches:
        await interaction.response.send_message(
            f"找不到名稱包含「{名稱}」的 NPC 喔！", ephemeral=True
        )
        return

    embed = discord.Embed(title=f"NPC 查詢：{名稱}", color=0x22C55E)
    for scenario_name, npc_name, description in matches:
        embed.add_field(name=f"{npc_name}（出自：{scenario_name}）", value=description, inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="劇本列表", description="列出所有目前收錄的劇本")
async def scenario_list(interaction: discord.Interaction):
    if not SCENARIOS:
        await interaction.response.send_message("目前還沒有收錄任何劇本喔！")
        return

    lines = [f"• **{name}**（{data['system']}）" for name, data in SCENARIOS.items()]
    await interaction.response.send_message("目前收錄的劇本：\n" + "\n".join(lines))


client.run(TOKEN)
