import asyncio
import discord
from discord import app_commands
from discord.ext import commands

import databaseFolder.playerCharactersData as playerCharactersData
from data.helpers.race_helper import get_all_guild_races
from character_engine import RuleDatabase, RaceBlueprint, Modifier


class RulesetCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    rules_group = app_commands.Group(name="rules", description="Manage custom races and feats")


    class RaceListView(discord.ui.View):
        def __init__(self, standard_races, custom_races, section="standard"):
            super().__init__(timeout=300)
            self.standard_races = standard_races
            self.custom_races = custom_races
            self.section = section
            self.page = 0
            self.page_size = 8
            self.previous_button = discord.ui.Button(
                label="← Previous",
                style=discord.ButtonStyle.secondary,
                disabled=True
                )
            
            self.next_button = discord.ui.Button(
                label="Next →",
                style=discord.ButtonStyle.secondary
                )
            
            self.standard_button = discord.ui.Button(
                label="📖 Standard Races",
                style=discord.ButtonStyle.primary
                )
            
            self.custom_button = discord.ui.Button(
                label="🏠 Custom Races",
                style=discord.ButtonStyle.primary
                )
            self.previous_button.callback = self.previous_page
            self.next_button.callback = self.next_page
            self.standard_button.callback = self.show_standard
            self.custom_button.callback = self.show_custom
            
            self.add_item(self.standard_button)
            self.add_item(self.custom_button)
            self.add_item(self.previous_button)
            self.add_item(self.next_button)
            
            self.update_buttons()

        def get_current_races(self):
            if self.section == "standard":
                return self.standard_races
            return self.custom_races

        def get_total_pages(self):
            races = self.get_current_races()
            
            return max(
                1,
                (len(races) + self.page_size - 1) // self.page_size
                )

        def update_buttons(self):
            total_pages = self.get_total_pages()
            self.previous_button.disabled = self.page == 0
            self.next_button.disabled = self.page >= total_pages - 1

            self.standard_button.disabled = self.section == "standard"
            self.custom_button.disabled = self.section == "custom"

        def build_embed(self):
            races = self.get_current_races()
            
            total_pages = self.get_total_pages()
            start = self.page * self.page_size
            end = start + self.page_size
            page_races = races[start:end]
            
            if self.section == "standard":
                title = "📖 Standard Races"
            else:
                title = "🏠 Custom Races"
                
            embed = discord.Embed(
                title=title,
                description=(
                    "Available standard races."
                    if self.section == "standard"
                    else "Custom races created for this server."
                    ),
                    color=discord.Color.blue()
                    )

            if not page_races:
                embed.add_field(
                    name="No races",
                    value="There are no races in this section.",
                    inline=False
                    )
            else:
                for index, (race_name, race_data) in enumerate(
                    page_races,
                    start=start + 1
                ):
                    asi_raw = race_data.get("asi", [])
                    if isinstance(asi_raw, dict):
                        parts = [
                            f"{'+' if v >= 0 else ''}{v} {k}"
                            for k, v in asi_raw.items() if v
                        ]
                        asi_str = ", ".join(parts) if parts else "Standard SRD"
                    elif isinstance(asi_raw, list):
                        asi_str = ", ".join(f"+1 {a}" for a in asi_raw) if asi_raw else "Standard SRD"
                    else:
                        asi_str = "Standard SRD"

                    traits = race_data.get("traits", [])
                    traits_str = (
                         "\n".join(f"• {t}" for t in traits)
                         if traits
                         else "Standard SRD Traits"
                    )

                    tag = " (Homebrew)" if self.section == "custom" else ""

                    embed.add_field(
                        name=f"{index}. {race_name}{tag}",
                        value=(
                            f"**ASI:** {asi_str}\n"
                            f"**Speed:** {race_data.get('speed', 30)} ft.\n"
                            f"**Traits:**\n{traits_str}"
                            ),
                        inline=False
                    )

            embed.set_footer(
                text=f"Page {self.page + 1} of {total_pages}"
                )
            return embed

        async def previous_page(self, interaction: discord.Interaction):
            if self.page > 0:
                self.page -= 1

            self.update_buttons()

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
                )

        async def next_page(self, interaction: discord.Interaction):
            if self.page < self.get_total_pages() - 1:
                self.page += 1
            self.update_buttons()

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
                )

        async def show_standard(self, interaction: discord.Interaction):
            self.section = "standard"
            self.page = 0

            self.update_buttons()

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
                )

        async def show_custom(self, interaction: discord.Interaction):
            self.section = "custom"
            self.page = 0
            
            self.update_buttons()

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
                )

     

    @rules_group.command(
        name="list_races",
        description="List all races available in this server"
    )
    async def list_races(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id or 0

        races = await get_all_guild_races(guild_id)

        if not races:
            await interaction.followup.send(
                "No races found for this server.",
                ephemeral=True
            )
            return

        # Separate standard and custom races
        standard_races = []
        custom_races = []

        for race_name, race_data in races.items():
            if race_data.get("is_custom", False):
                custom_races.append((race_name, race_data))
            else:
                standard_races.append((race_name, race_data))

        view = RulesetCommands.RaceListView(
            standard_races,
            custom_races
        )

        await interaction.followup.send(
            embed=view.build_embed(),
            view=view,
            ephemeral=True
        )

    @rules_group.command(name="list_feats", description="List all available feats")
    async def list_feats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if asyncio.iscoroutinefunction(RuleDatabase.get_all_feats):
            feats = await RuleDatabase.get_all_feats()
        else:
            feats = RuleDatabase.get_all_feats()

        if not feats:
            await interaction.followup.send("No feats found.", ephemeral=True)
            return

        embed = discord.Embed(title="Available Feats", color=discord.Color.green())
        for feat in feats:
            name = getattr(feat, 'name', str(feat))
            desc = getattr(feat, 'description', 'No description') or "No description"
            embed.add_field(name=name, value=desc, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(RulesetCommands(bot))