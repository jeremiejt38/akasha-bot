"""Simple poll manager for Discord.

Admins can create polls with up to 4 options. Users vote by clicking a button.
Results are updated live in the embed.
"""
import logging
import discord
from discord import ui

logger = logging.getLogger(__name__)


class PollButton(ui.Button):
    def __init__(self, option: str, index: int, poll_view: "PollView"):
        super().__init__(label=option, style=discord.ButtonStyle.primary, custom_id=f"poll:{index}")
        self.option = option
        self.index = index
        self.poll_view = poll_view

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        previous = self.poll_view.votes.get(user_id)
        self.poll_view.votes[user_id] = self.index

        if previous == self.index:
            await interaction.response.send_message(
                "Tu as déjà voté pour cette option.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Vote enregistré : **{self.option}**", ephemeral=True
        )
        self.poll_view.update_embed()
        await interaction.message.edit(embed=self.poll_view.embed, view=self.poll_view)


class PollView(ui.View):
    def __init__(self, question: str, options: list[str], author_id: int, timeout: int = 86400):
        super().__init__(timeout=timeout)
        self.question = question
        self.options = options[:4]
        self.author_id = author_id
        self.votes: dict[int, int] = {}
        self.embed = self._build_embed()
        for idx, option in enumerate(self.options):
            self.add_item(PollButton(option, idx, self))

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 Sondage — {self.question}",
            description="Clique sur une option pour voter.",
            color=discord.Color.blurple(),
        )
        counts = [0] * len(self.options)
        for vote in self.votes.values():
            if 0 <= vote < len(self.options):
                counts[vote] += 1
        total = len(self.votes)
        for idx, option in enumerate(self.options):
            bar_width = 20
            bar = "█" * int(bar_width * (counts[idx] / total)) if total else ""
            embed.add_field(
                name=f"{idx + 1}. {option}",
                value=f"{bar} {counts[idx]} vote(s)",
                inline=False,
            )
        embed.set_footer(text=f"Total : {total} vote(s)")
        return embed

    def update_embed(self):
        self.embed = self._build_embed()
