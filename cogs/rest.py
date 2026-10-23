"""
Rest commands: long rest (all slots) and short rest (pact slots only).
"""
import discord
from discord import app_commands
from discord.ext import commands

import databaseFolder.playerCharactersData as playerCharactersData
from utils.sheet import build_sheet_embed, get_homebrew_features_for, get_homebrew_race_traits_for
from utils.spell_slots import is_caster, reset_slots, max_slots
from views.character_ui import PickCharacterView


class Rest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rest", description="Take a rest and recover resources")
    @app_commands.describe(rest_type="Long rest restores all spell slots; short rest restores Pact Magic slots")
    @app_commands.choices(rest_type=[
        app_commands.Choice(name="🌙 Long Rest", value="long"),
        app_commands.Choice(name="☕ Short Rest", value="short"),
    ])
    async def rest(self, interaction: discord.Interaction, rest_type: app_commands.Choice[str]):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            kind = rest_type.value

            if kind == "short":
                mx = max_slots(character)
                if mx["pact"] is None:
                    await inter.response.edit_message(
                        content=(f"**{character['name']}** doesn't regain spell slots on a short rest "
                                 f"(only Pact Magic users do). A long rest will restore everything."),
                        view=None
                    )
                    return

            reset_slots(character, kind)
            await playerCharactersData.update_character(character)

            label = "🌙 Long rest" if kind == "long" else "☕ Short rest"
            if kind == "long":
                detail = "All spell slots restored."
            else:
                detail = "Pact Magic slots restored."

            embed = build_sheet_embed(
                character,
                await get_homebrew_features_for(character),
                await get_homebrew_race_traits_for(character)
            )

            await inter.response.edit_message(
                content=f"{label} complete for **{character['name']}**. {detail}",
                view=None
            )
            await inter.followup.send(embed=embed)

        await interaction.response.send_message(
            "Which character is resting?",
            view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Rest(bot))