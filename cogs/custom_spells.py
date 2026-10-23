"""
Custom spell management: players define their own spells, then attach them
to specific characters. Mechanics live in the player's pool; membership
lives on each character's known_spells list.
"""
import discord
from discord import app_commands
from discord.ext import commands

import databaseFolder.playerCharactersData as playerCharactersData
from views.character_ui import PickCharacterView
from views.spell_ui import CustomSpellModal


class CustomSpells(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="createspell", description="Define a custom spell in your personal pool")
    async def createspell(self, interaction: discord.Interaction):
        async def submitted(inter, data):
            data["user_id"] = interaction.user.id
            data["guild_id"] = interaction.guild_id
            await playerCharactersData.save_custom_spell(data)

            lvl_label = "Cantrip" if data["level"] == 0 else f"Level {data['level']}"
            dmg = data["damage_expr"] or "no damage (utility)"
            type_note = f" {data['damage_type']}" if data["damage_type"] else ""
            range_note = f" | Range: {data['range']}" if data["range"] else ""

            await inter.response.send_message(
                f"✅ Custom spell **{data['name']}** saved ({lvl_label}, `{dmg}{type_note}`){range_note}.\n"
                f"Use `/addspell` to attach it to one of your characters.",
                ephemeral=True
            )

        await interaction.response.send_modal(CustomSpellModal(submitted))

    @app_commands.command(name="myspells", description="List your custom spells")
    async def myspells(self, interaction: discord.Interaction):
        spells = await playerCharactersData.get_custom_spells_for_user(
            interaction.user.id, interaction.guild_id
        )
        if not spells:
            await interaction.response.send_message(
                "You haven't created any custom spells yet — try `/createspell`.", ephemeral=True
            )
            return

        lines = []
        for s in spells:
            lvl_label = "Cantrip" if s["level"] == 0 else f"L{s['level']}"
            dmg = s["damage_expr"] or "utility"
            type_note = f" {s['damage_type']}" if s["damage_type"] else ""
            lines.append(f"**{s['name']}** ({lvl_label}) — `{dmg}{type_note}`")

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Custom Spells",
            description="\n".join(lines),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Use /addspell to give one to a character.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="deletespell", description="Remove a spell from your custom pool")
    @app_commands.describe(name="The spell's name")
    async def deletespell(self, interaction: discord.Interaction, name: str):
        deleted = await playerCharactersData.delete_custom_spell(
            interaction.user.id, interaction.guild_id, name
        )
        if deleted:
            await interaction.response.send_message(
                f"🗑️ Removed **{name}** from your custom spell pool.\n"
                f"*(Characters that still list it in known spells won't be able to cast it "
                f"until you `/addspell` a new version or `/removespell` it.)*",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Couldn't find a custom spell named **{name}** in your pool.", ephemeral=True
            )

    @app_commands.command(name="addspell", description="Teach a spell to one of your characters")
    @app_commands.describe(spell="The spell's name (custom or built-in)")
    async def addspell(self, interaction: discord.Interaction, spell: str):
        characters = await playerCharactersData.get_characters_for_user(
            interaction.user.id, interaction.guild_id
        )
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            added = await playerCharactersData.add_spell_to_character(
                character["id"], interaction.user.id, spell
            )
            if added:
                await inter.response.edit_message(
                    content=f"✅ **{character['name']}** now knows **{spell}**.", view=None
                )
            else:
                await inter.response.edit_message(
                    content=(f"Nothing changed — either **{character['name']}** already knows "
                             f"**{spell}**, or something went wrong."),
                    view=None
                )

        await interaction.response.send_message(
            f"Which character should learn **{spell}**?",
            view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(CustomSpells(bot))