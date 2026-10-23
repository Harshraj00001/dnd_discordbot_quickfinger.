"""
Character sheet view, editing, HP damage/healing, listing, and deletion commands.
"""
import discord
from discord import app_commands
from discord.ext import commands

import databaseFolder.playerCharactersData as playerCharactersData
from data.reference import WEAPONS, ARMOR
from utils.sheet import (
    build_sheet_embed, recalculate_character_stats,
    get_homebrew_features_for, get_homebrew_race_traits_for
)

from character_creation.constants import MIN_CUSTOM_SCORE, MAX_CUSTOM_SCORE

from views.character_ui import (
    PickCharacterView, MultiPickCharacterView, ConfirmView, NameModal, LevelPickView,
    WeaponPickView, ArmorPickView, ShieldView, EditCategoryView,
    EditScorePart1Modal, EditScorePart2Modal, ModalTriggerView
)
from views.spell_ui import SpellsModal

from character_creation.constants import TWO_HANDED_WEAPONS


class CharacterManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sheet", description="View one of your characters' sheets")
    async def sheet(self, interaction: discord.Interaction, name: str = None):
        if name:
            character = await playerCharactersData.get_character_by_name(interaction.user.id, interaction.guild_id, name)
            if not character:
                await interaction.response.send_message(f"Couldn't find a character named '{name}'.", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=build_sheet_embed(
                    character,
                    await get_homebrew_features_for(character),
                    await get_homebrew_race_traits_for(character)
                )
            )
        else:
            characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
            if not characters:
                await interaction.response.send_message(
                    "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
                )
                return
            if len(characters) == 1:
                character = characters[0]
                await interaction.response.send_message(
                    embed=build_sheet_embed(
                        character,
                        await get_homebrew_features_for(character),
                        await get_homebrew_race_traits_for(character)
                    )
                )
            else:
                names = ", ".join(c["name"] for c in characters)
                await interaction.response.send_message(
                    f"You have multiple characters: {names}. Use `/sheet name:<name>` to pick one.",
                    ephemeral=True
                )

    @app_commands.command(name="editcharacter", description="Edit an existing character's details")
    async def editcharacter(self, interaction: discord.Interaction):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters to edit yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            async def category_chosen(inter_cat, category):
                if category == "name":
                    async def name_edited(inter_name, new_name):
                        character["name"] = new_name
                        await recalculate_and_save(inter_name, character)
                    await inter_cat.response.send_modal(NameModal(name_edited))

                elif category == "level":
                    async def level_edited(inter_lvl, new_level):
                        character["level"] = new_level
                        await recalculate_and_save(inter_lvl, character)
                    await inter_cat.response.edit_message(
                        content=f"Pick a new level for **{character['name']}**:",
                        view=LevelPickView(level_edited)
                    )

                elif category == "scores":
                    print("[SCORES] branch entered")

                    def _parse_score(raw):
                        try:
                            v = int(str(raw).strip())
                        except ValueError:
                            return None
                        if v < 1 or v > 30:
                            return None
                        return v

                    async def part1_submitted(inter_p1, values):
                        
                        parsed = {k: _parse_score(v) for k, v in values.items()}
                        if any(v is None for v in parsed.values()):
                            await inter_p1.response.send_message(
                                "⚠️ Ability scores must be whole numbers between 1 and 30. Let's try again.",
                                ephemeral=True
                            )
                            await inter_p1.followup.send(
                                "Click to reopen:",
                                view=ModalTriggerView(
                                    lambda i: i.response.send_modal(EditScorePart1Modal(character, part1_submitted)),
                                    label="Try again"
                                ),
                                ephemeral=True
                            )
                            return

                        temp_scores = dict(parsed)

                        async def part2_submitted(inter_p2, values2):
                            
                            parsed2 = {k: _parse_score(v) for k, v in values2.items()}
                            if any(v is None for v in parsed2.values()):
                                await inter_p2.response.send_message(
                                    "⚠️ Ability scores must be whole numbers between 1 and 30. Let's try again.",
                                    ephemeral=True
                                )
                                await inter_p2.followup.send(
                                    "Click to reopen:",
                                    view=ModalTriggerView(
                                        lambda i: i.response.send_modal(EditScorePart2Modal(character, part2_submitted)),
                                        label="Try again"
                                    ),
                                    ephemeral=True
                                )
                                return

                            all_scores = {**temp_scores, **parsed2}
                            character["str"]  = all_scores["STR"]
                            character["dex"]  = all_scores["DEX"]
                            character["con"]  = all_scores["CON"]
                            character["intl"] = all_scores["INT"]
                            character["wis"]  = all_scores["WIS"]
                            character["cha"]  = all_scores["CHA"]

                            await recalculate_and_save(inter_p2, character)

                        # KEY CHANGE: respond to part 1 with a message + button,
                        # not with another modal. The button opens part 2.
                        await inter_p1.response.edit_message(
                            content=(f"STR **{parsed['STR']}**, DEX **{parsed['DEX']}**, "
                                     f"CON **{parsed['CON']}** set. Tap below to edit INT, WIS, and CHA:"),
                            view=ModalTriggerView(
                                lambda i: i.response.send_modal(EditScorePart2Modal(character, part2_submitted)),
                                label="Continue ➜ INT / WIS / CHA"
                            )
                        )

                    await inter_cat.response.send_modal(
                        EditScorePart1Modal(character, part1_submitted)
                    )

                elif category == "weapon":
                    weapon_options = list(WEAPONS.keys())
                    async def weapon_edited(inter_wep, new_weapon):
                        character["weapon"] = new_weapon
                        two_handed = TWO_HANDED_WEAPONS
                        if new_weapon in two_handed:
                            character["has_shield"] = False
                        await recalculate_and_save(inter_wep, character)
                    await inter_cat.response.edit_message(
                        content=f"Pick a new weapon for **{character['name']}**:",
                        view=WeaponPickView(weapon_edited, weapon_options)
                    )

                elif category == "armor":
                    armor_options = [a for a in ARMOR.keys() if a != "Shield"]
                    async def armor_edited(inter_arm, new_armor):
                        character["armor"] = new_armor
                        two_handed = TWO_HANDED_WEAPONS

                        if character.get("weapon") in two_handed:
                            character["has_shield"] = False
                            await inter_arm.response.edit_message(
                                content=(f"Armor set to **{new_armor}**. "
                                         f"(No shield — **{character['weapon']}** requires two hands.)"),
                                view=None
                            )
                            await recalculate_and_save(inter_arm, character, already_responded=True)
                        else:
                            async def shield_edited(inter_shd, wants_shield):
                                character["has_shield"] = wants_shield
                                await recalculate_and_save(inter_shd, character)
                            await inter_arm.response.edit_message(
                                content=f"Armor set to **{new_armor}**. Want to carry a shield (+2 AC)?",
                                view=ShieldView(shield_edited)
                            )
                    await inter_cat.response.edit_message(
                        content=f"Pick new armor for **{character['name']}**:",
                        view=ArmorPickView(armor_edited, armor_options)
                    )

                elif category == "spells":
                    async def spells_edited(inter_spl, new_spells):
                        character["known_spells"] = new_spells
                        await recalculate_and_save(inter_spl, character)
                    await inter_cat.response.send_modal(SpellsModal(spells_edited))

            await inter.response.edit_message(
                content=f"Editing **{character['name']}**. What would you like to edit?",
                view=EditCategoryView(category_chosen)
            )

        async def recalculate_and_save(inter_save, char_obj, already_responded=False):
            char_obj = await recalculate_character_stats(char_obj)
            await playerCharactersData.update_character(char_obj)
            embed = build_sheet_embed(
                char_obj,
                await get_homebrew_features_for(char_obj),
                await get_homebrew_race_traits_for(char_obj)
            )
            if already_responded:
                await inter_save.followup.send(
                    content=f"✅ Updated **{char_obj['name']}**!", embed=embed
                )
            else:
                await inter_save.response.edit_message(
                    content=f"✅ Updated **{char_obj['name']}**!", view=None
                )
                await inter_save.followup.send(embed=embed)

        await interaction.response.send_message(
            "Which character would you like to edit?",
            view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        )

    @app_commands.command(name="damage", description="Apply damage to one of your characters")
    @app_commands.describe(amount="How much damage to apply")
    async def damage(self, interaction: discord.Interaction, amount: int):
        if amount < 0:
            await interaction.response.send_message(
                "Damage amount can't be negative — use `/heal` to restore HP instead.", ephemeral=True
            )
            return
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            old_hp = character["current_hp"]
            new_hp = max(0, old_hp - amount)
            await playerCharactersData.update_hp(character["id"], new_hp)
            status = " 💀 **Down!**" if new_hp == 0 else ""
            content = (f"💥 **{character['name']}** takes **{amount}** damage: "
                       f"{old_hp} → **{new_hp}**/{character['max_hp']} HP{status}")
            await inter.response.edit_message(content="✅ Applied — see below!", view=None)
            await inter.followup.send(content=content)

        await interaction.response.send_message(
            "Which character is taking damage?", view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        )

    @app_commands.command(name="heal", description="Heal one of your characters")
    @app_commands.describe(amount="How much HP to restore")
    async def heal(self, interaction: discord.Interaction, amount: int):
        if amount < 0:
            await interaction.response.send_message(
                "Healing amount can't be negative — use `/damage` to apply damage instead.", ephemeral=True
            )
            return
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            old_hp = character["current_hp"]
            new_hp = min(character["max_hp"], old_hp + amount)
            await playerCharactersData.update_hp(character["id"], new_hp)
            content = (f"💚 **{character['name']}** heals **{amount}** HP: "
                       f"{old_hp} → **{new_hp}**/{character['max_hp']} HP")
            await inter.response.edit_message(content="✅ Applied — see below!", view=None)
            await inter.followup.send(content=content)

        await interaction.response.send_message(
            "Which character is healing?", view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        )

    @app_commands.command(name="mycharacters", description="View a list of all your characters")
    async def mycharacters(self, interaction: discord.Interaction):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        lines = []
        for c in characters:
            race_tag = "🔧" if c.get("is_homebrew_race") else ""
            class_tag = "🔧" if c.get("is_homebrew_class") else ""
            lines.append(
                f"**{c['name']}** — Level {c['level']} {race_tag}{c['race']} {class_tag}{c['class_name']}\n"
                f"HP: {c['current_hp']}/{c['max_hp']}  |  AC: {c['ac']}"
            )

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Characters",
            description="\n\n".join(lines),
            color=discord.Color.dark_gold()
        )
        embed.set_footer(text="Use /sheet name:<name> to see full details for one of them.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="deletecharacter", description="Permanently delete one of your characters")
    async def deletecharacter(self, interaction: discord.Interaction):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            async def confirmed(inter2, yes):
                
                if yes:

                    deleted = await playerCharactersData.delete_character(character["id"], interaction.user.id)

                    content = (f"🗑️ **{character['name']}** has been permanently deleted." if deleted
                               else "Something went wrong — that character couldn't be deleted.")
                else:
                    content = f"Cancelled — **{character['name']}** was not deleted." 

                await inter2.response.edit_message(content=content, view=None)

                

            await inter.response.edit_message(
                content=(f"⚠️ Are you sure you want to permanently delete **{character['name']}**? "
                         f"This cannot be undone."),
                view=ConfirmView(confirmed, confirm_label="🗑️ Yes, delete permanently")
            )

        await interaction.response.send_message(
            "Which character do you want to delete?", view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        )

    @app_commands.command(name="deletecharacters", description="Permanently delete multiple characters at once")
    async def deletecharacters(self, interaction: discord.Interaction):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter`!", ephemeral=True
            )
            return

        async def characters_chosen(inter, selected):
            names = ", ".join(c["name"] for c in selected)

            async def confirmed(inter2, yes):
                

                if yes:
                    deleted_names = []
                    for c in selected:
                        if await playerCharactersData.delete_character(c["id"], interaction.user.id):
                            

                            deleted_names.append(c["name"])
                    content = (f"🗑️ Deleted: {', '.join(deleted_names)}" if deleted_names
                               else "Nothing was deleted — something went wrong.")
                else:
                    content = "Cancelled — no characters were deleted."

                   
                await inter2.response.edit_message(content=content, view=None)
                

            await inter.response.edit_message(
                content=(f"⚠️ Are you sure you want to permanently delete **{len(selected)}** "
                         f"character(s): {names}? This cannot be undone."),
                view=ConfirmView(confirmed, confirm_label="🗑️ Yes, delete them all")
            )

        await interaction.response.send_message(
            "Select one or more characters to delete:",
            view=MultiPickCharacterView(characters, characters_chosen), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(CharacterManagement(bot))