"""
技能檢定掃描功能
------------------------
跟劇本查詢、關鍵字回應都完全獨立，只負責一件事：
打 /成功技能 的時候，機器人會往回翻這個頻道的歷史訊息，找出骰子機器人
（目前針對「諧典」的 COC7 技能檢定格式）回覆的檢定結果，統計每位玩家
成功過哪些技能。

這個功能不會自己存任何資料，每次都是現場掃描頻道，所以機器人重啟、
重新部署都不會讓紀錄消失（資料本來就存在 Discord 的訊息裡）。

使用方式（在 bot.py 裡）：
    import skill_scan
    skill_scan.setup(tree)

前提：機器人在要掃描的頻道需要有「讀取訊息歷史」的權限。

解析的訊息長相（諧典的嵌入卡片）：
    [作者名稱]  ← 骰的人
    🎲 COC7 技能檢定 偵查
    技能值: 75 (困難: 37 / 極限: 15)
    擲骰: 58
    結果: ✅ 一般成功
"""

import re
from collections import Counter, defaultdict

import discord
from discord import app_commands

DEFAULT_SCAN = 1000
MAX_SCAN = 5000

# 技能名稱：「技能檢定」後面同一行的文字
SKILL_RE = re.compile(r"技能檢定[ \t]*([^\n]+)")


def _collect_embed_text(embed: discord.Embed) -> str:
    """
    把嵌入卡片裡所有文字串成一段，不管骰子機器人是把內容放在標題、描述，
    還是拆成好幾個欄位，後面都能用同一種方式解析。
    """
    parts = []
    if embed.title:
        parts.append(embed.title)
    if embed.description:
        parts.append(embed.description)
    for field in embed.fields:
        parts.append(f"{field.name}: {field.value}")
    if embed.footer and embed.footer.text:
        parts.append(embed.footer.text)
    return "\n".join(parts)


def _roller_name(message, embed: discord.Embed) -> str:
    """骰的人是誰：優先用嵌入卡片上方的作者名稱，沒有的話改看它回覆的是誰的指令"""
    if embed.author and embed.author.name:
        return embed.author.name

    reference = getattr(message, "reference", None)
    resolved = getattr(reference, "resolved", None) if reference else None
    author = getattr(resolved, "author", None)
    if author is not None:
        return author.display_name

    return "未知玩家"


def parse_check_message(message):
    """
    如果這則訊息是骰子機器人的技能檢定結果，回傳 (玩家, 技能, 是否成功)，
    不是的話回傳 None。
    「成功」包含一般成功、困難成功、極限成功、大成功；失敗和大失敗算失敗。
    """
    if not message.author.bot:
        return None

    for embed in message.embeds:
        text = _collect_embed_text(embed)

        skill_match = SKILL_RE.search(text)
        if not skill_match:
            continue

        result_line = next((line for line in text.splitlines() if "結果" in line), None)
        if result_line is None:
            continue

        after_label = result_line.split("結果", 1)[1]
        if "失敗" in after_label:
            success = False
        elif "成功" in after_label:
            success = True
        else:
            continue

        return _roller_name(message, embed), skill_match.group(1).strip(), success

    return None


async def scan_channel(channel, limit: int):
    """往回翻頻道最近 limit 則訊息，回傳 (所有檢定紀錄, 實際掃描的訊息數)"""
    checks = []
    scanned = 0
    async for message in channel.history(limit=limit):
        scanned += 1
        parsed = parse_check_message(message)
        if parsed:
            checks.append(parsed)
    return checks, scanned


def build_result_embed(checks: list, scanned: int, player_filter: str = "") -> discord.Embed:
    """把檢定紀錄整理成「每位玩家成功過的技能」卡片"""
    per_player = defaultdict(Counter)
    success_total = 0
    fail_total = 0

    for player, skill, success in checks:
        if player_filter and player_filter.lower() not in player.lower():
            continue
        if success:
            per_player[player][skill] += 1
            success_total += 1
        else:
            fail_total += 1

    embed = discord.Embed(title="🎲 成功技能紀錄", color=0x8B5CF6)

    if not per_player:
        embed.description = "在這段範圍裡沒有找到成功的技能檢定。"
    else:
        blocks = []
        for player in sorted(per_player):
            skills = sorted(per_player[player].items(), key=lambda item: (-item[1], item[0]))
            lines = [f"• {skill} ×{count}" for skill, count in skills]
            blocks.append(f"**{player}**\n" + "\n".join(lines))
        text = "\n\n".join(blocks)

        # Discord 卡片說明欄上限是 4096 字，留一點空間給提示文字
        if len(text) > 3900:
            text = text[:3900].rstrip() + "\n…（內容太長，後面已省略）"
        embed.description = text

    embed.set_footer(
        text=f"掃描最近 {scanned} 則訊息，找到 {success_total + fail_total} 筆技能檢定"
             f"（成功 {success_total} / 失敗 {fail_total}）"
    )
    return embed


def setup(tree: app_commands.CommandTree) -> None:
    """把 /成功技能 指令掛到機器人的指令樹上"""

    @tree.command(name="成功技能", description="掃描這個頻道的骰子紀錄，列出每位玩家成功過的技能")
    @app_commands.describe(
        數量=f"要往回掃描最近幾則訊息，預設 {DEFAULT_SCAN}，最多 {MAX_SCAN}",
        玩家="（選填）只看某位玩家，輸入名字的一部分就可以",
    )
    async def success_skills(
        interaction: discord.Interaction,
        數量: app_commands.Range[int, 50, MAX_SCAN] = DEFAULT_SCAN,
        玩家: str = "",
    ):
        channel = interaction.channel
        if channel is None or not hasattr(channel, "history"):
            await interaction.response.send_message("這個地方沒辦法掃描訊息喔！", ephemeral=True)
            return

        # 掃描幾千則訊息可能要幾秒鐘，先告訴 Discord「我在處理」，避免超過 3 秒回應時限
        await interaction.response.defer()

        try:
            checks, scanned = await scan_channel(channel, 數量)
        except discord.Forbidden:
            await interaction.followup.send(
                "我沒有權限讀取這個頻道的歷史訊息😢 請在伺服器設定裡，"
                "幫我的身分組（或這個頻道）打開「讀取訊息歷史」權限。"
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"讀取訊息時出了點問題：{e}")
            return

        await interaction.followup.send(embed=build_result_embed(checks, scanned, 玩家.strip()))

    print("✅ 成功技能掃描功能已啟用（/成功技能）")
