"""
回到開頭功能
------------------------
打 /回到開頭 之後，機器人會找出這個頻道（或論壇貼文）的第一則訊息，
回覆一個按鈕，點下去就會直接跳到那則訊息。

為什麼是按鈕而不是「自動拉到開頭」：
Discord 的機器人沒有辦法控制使用者畫面的捲動位置，
能做到的是提供一個「跳轉連結」，點下去由 Discord 幫你跳過去。
回覆只有打指令的人看得到，不會洗版。

使用方式（在 bot.py 裡）：
    import jump_start
    jump_start.setup(tree)

前提：機器人在這個頻道需要有「讀取訊息歷史」的權限。
"""

import discord
from discord import app_commands


def setup(tree: app_commands.CommandTree) -> None:
    """把 /回到開頭 指令掛到機器人的指令樹上"""

    @tree.command(name="回到開頭", description="給你一個按鈕，點下去就會跳到這個頻道的第一則訊息")
    async def jump_to_start(interaction: discord.Interaction):
        channel = interaction.channel
        if channel is None or not hasattr(channel, "history"):
            await interaction.response.send_message("這個地方沒辦法找開頭喔！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        first_message = None
        try:
            # oldest_first=True 會從最舊的開始抓，只拿 1 則，所以頻道再長也很快
            async for message in channel.history(limit=1, oldest_first=True):
                first_message = message
        except discord.Forbidden:
            await interaction.followup.send(
                "我沒有權限讀取這個頻道的歷史訊息😢 請在伺服器設定裡，"
                "幫我的身分組（或這個頻道）打開「讀取訊息歷史」權限。",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"讀取訊息時出了點問題：{e}", ephemeral=True)
            return

        if first_message is None:
            await interaction.followup.send("這個頻道目前還沒有任何訊息喔！", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="跳到第一則訊息",
                style=discord.ButtonStyle.link,
                url=first_message.jump_url,
            )
        )
        await interaction.followup.send("點下面的按鈕就會跳到開頭囉👇", view=view, ephemeral=True)

    print("✅ 回到開頭功能已啟用（/回到開頭）")
