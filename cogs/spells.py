"""
Spellcasting mechanics: handles spell slot calculations, upcasting, and roll resolution.
"""
import re
import discord
from discord import app_commands
from discord.ext import commands

import databaseFolder.playerCharactersData as playerCharactersData
from data.reference import (
    SPELLS, SPELLCASTING_ABILITY, CLASSES,
    cantrip_dice_multiplier, ability_modifier, proficiency_bonus
)
from utils.sheet import ABILITY_TO_FIELD
from utils.spell_slots import (
    is_caster, max_slots, available_slots, can_cast_at_level,
    consume_slot, max_available_slot_level, format_slots_for_sheet
)
from views.character_ui import PickCharacterView
from cogs.dice import roll_expression


def get_known_spells(character):
    return character.get("known_spells", [])


def get_caster_type(character):
    """Returns the caster type for a character, supporting homebrew classes."""
    if character.get("is_homebrew_class"):
        return character.get("caster_type")
    return CLASSES.get(character["class_name"], {}).get("caster")


def get_spellcasting_ability(character):
    if character.get("is_homebrew_class"):
        return character.get("spellcasting_ability")
    return SPELLCASTING_ABILITY.get(character["class_name"])

def _derive_scaling_dice(damage_expr: str):
    """
    Given a base damage expression, infer the per-slot scaling die.
    Examples:
        "1d6"     → "1d6"
        "2d8"     → "1d8"
        "3d6+2"   → "1d6"
        "1d6+1d4" → None  (multi-term, can't infer reliably)
        "1d10"    → "1d10"
    """
    if not damage_expr:
        return None
    # Strip whitespace and take only the first term (before any + or -).
    first = re.split(r"[+-]", damage_expr.strip(), maxsplit=1)[0].strip()
    m = re.fullmatch(r"(\d*)d(\d+)", first, re.IGNORECASE)
    if not m:
        return None
    # Scaling die is always 1 die of the same face size.
    return f"1d{m.group(2)}"

def scale_dice_expr(base_expr: str, scaling_die_expr: str, extra_levels: int) -> str:
    base_count, faces = base_expr.lower().split("d")
    scale_count, scale_faces = scaling_die_expr.lower().split("d")
    total_count = int(base_count) + int(scale_count) * max(0, extra_levels)
    return f"{total_count}d{faces}"


def format_school_header(spell_name: str, data: dict) -> str:
    level_label = "Cantrip" if data["level"] == 0 else f"Level {data['level']}"
    return f"**{spell_name}** ({level_label} {data['school']})"


class SpellSelect(discord.ui.Select):
    def __init__(self, on_pick, spell_names):
        options = [discord.SelectOption(label=s) for s in spell_names[:25]]
        super().__init__(placeholder="Which spell?", options=options)
        self.on_pick = on_pick

    async def callback(self, interaction: discord.Interaction):
        await self.on_pick(interaction, self.values[0])


class SpellPickView(discord.ui.View):
    def __init__(self, on_pick, spell_names):
        super().__init__(timeout=60)
        self.add_item(SpellSelect(on_pick, spell_names))


class SlotLevelSelect(discord.ui.Select):
    def __init__(self, on_pick, min_level, max_level, available_by_level: dict):
        """available_by_level maps str(level) -> remaining count, for display."""
        options = []
        for n in range(min_level, max_level + 1):
            remaining = available_by_level.get(str(n))
            label = f"Level {n} slot"
            if remaining is not None:
                label += f" ({remaining} left)"
            options.append(discord.SelectOption(label=label, value=str(n)))
        super().__init__(placeholder="Cast using which slot level?", options=options)
        self.on_pick = on_pick

    async def callback(self, interaction: discord.Interaction):
        await self.on_pick(interaction, int(self.values[0]))


class SlotLevelView(discord.ui.View):
    def __init__(self, on_pick, min_level, max_level, available_by_level: dict):
        super().__init__(timeout=60)
        self.add_item(SlotLevelSelect(on_pick, min_level, max_level, available_by_level))


class Spells(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="cast", description="Cast one of your character's known spells")
    @app_commands.describe(target_ac="Optional: the target's AC, for attack-roll spells")
    async def cast(self, interaction: discord.Interaction, target_ac: int = None):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        casters = [c for c in characters if is_caster(c)]
        if not casters:
            await interaction.response.send_message(
                "None of your characters can cast spells yet — try `/newcharacter` with a caster class!",
                ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            spell_names = get_known_spells(character)
            if not spell_names:
                await inter.response.edit_message(
                    content=f"**{character['name']}** doesn't know any spells yet.", view=None
                )
                return

            async def spell_chosen(inter2, spell_name):
                await self._resolve_spell_pick(inter2, character, spell_name, target_ac)

            await inter.response.edit_message(
                content=f"Which spell is **{character['name']}** casting?",
                view=SpellPickView(spell_chosen, spell_names)
            )

        await interaction.response.send_message(
            "Which character is casting?", view=PickCharacterView(casters, character_chosen), ephemeral=True
        )

    async def _lookup_spell(self, interaction: discord.Interaction, spell_name: str):
        """
        Resolves a spell by name. Custom spells take precedence over built-in
        ones for the player who created them. Returns a dict in the same shape
        as SPELLS entries, or None if the spell has no mechanics.
        """
        custom = await playerCharactersData.get_custom_spell_by_name(
            interaction.user.id, interaction.guild_id, spell_name
        )
        if custom:
            entry = {
                "level": custom["level"],
                "school": custom["school"] or "Custom",
                "damage_type": custom["damage_type"] or "",
            }
            if custom.get("damage_expr"):
                entry["cast_type"] = "damage_only"
                entry["damage_dice_base"] = custom["damage_expr"]
                # Derive scaling from base dice when possible.
                # 2d6 → +1d6 per slot; 1d8+1d6 → no reliable scaling.
                scaling = _derive_scaling_dice(custom["damage_expr"])
                if scaling:
                    entry["scaling_dice"] = scaling
            else:
                entry["cast_type"] = "utility"
                entry["description"] = (
                    (f"Range: {custom['range']}\n" if custom.get("range") else "")
                    + (custom.get("description") or "No mechanics — see description.")
                )
            return entry

        return SPELLS.get(spell_name)
    
        

    async def _resolve_spell_pick(self, interaction, character, spell_name, target_ac):
        data = await self._lookup_spell(interaction, spell_name)
        spell_ability = get_spellcasting_ability(character)
        mod = ability_modifier(character[ABILITY_TO_FIELD[spell_ability]]) if spell_ability else 0
        prof = proficiency_bonus(character["level"])
        save_dc = 8 + prof + mod
        attack_bonus = prof + mod

        if not data:
            await interaction.response.edit_message(
                content=(f"I don't have built-in mechanics for **{spell_name}** yet.\n"
                         f"{character['name']}'s spell save DC is **{save_dc}**, spell attack is "
                         f"**+{attack_bonus}** — use `/roll` to roll damage manually."),
                view=None
            )
            return

        level = data["level"]
        if level == 0:
            await self._cast_and_reveal(interaction, character, spell_name, data, mod, save_dc, attack_bonus,
                                         slot_level=0, target_ac=target_ac)
            return

        # Check available slots.
        avail = available_slots(character)
        caster_type = get_caster_type(character)

        # Determine which slot levels are legal for this spell.
        min_level = level
        avail_standard = avail["standard"]
        legal_levels = [int(k) for k in avail_standard.keys() if int(k) >= min_level]

        if caster_type == "pact" and avail["pact"] is not None:
            pact_remaining, pact_level = avail["pact"]
            if pact_level >= min_level and pact_level not in legal_levels:
                legal_levels.append(pact_level)

        if not legal_levels:
            # Either no slots at all, or none high enough.
            if not avail["standard"] and avail["pact"] is None:
                await interaction.response.edit_message(
                    content=(f"**{character['name']}** has no spell slots remaining. "
                             f"Take a rest with `/rest`."),
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content=(f"**{character['name']}** doesn't have a high enough slot for "
                             f"{spell_name} (needs level {level}). Slots: "
                             f"{format_slots_for_sheet(character)}"),
                    view=None
                )
            return

        max_slot = max(legal_levels)

        # Pact casters skip the prompt — their slot level is fixed.
        if caster_type == "pact":
            if not can_cast_at_level(character, max_slot):
                await interaction.response.edit_message(
                    content=f"**{character['name']}** has no Pact slots remaining. Take a short rest.",
                    view=None
                )
                return
            await self._cast_and_reveal(interaction, character, spell_name, data, mod, save_dc, attack_bonus,
                                         slot_level=max_slot, target_ac=target_ac)
            return

        async def slot_chosen(inter, slot_level):
            await self._cast_and_reveal(inter, character, spell_name, data, mod, save_dc, attack_bonus,
                                         slot_level=slot_level, target_ac=target_ac)

        # Build a dict of remaining counts for the dropdown labels.
        remaining_by_level = {}
        for lvl_str, remaining in avail_standard.items():
            if int(lvl_str) >= min_level:
                remaining_by_level[lvl_str] = remaining

        await interaction.response.edit_message(
            content=f"Cast **{spell_name}** using which slot level?",
            view=SlotLevelView(slot_chosen, min_level, max_slot, remaining_by_level)
        )

    async def _cast_and_reveal(self, interaction, character, spell_name, data, mod, save_dc, attack_bonus,
                                slot_level, target_ac):
        # Consume the slot BEFORE rolling, so a crash mid-roll still debits it.
        if slot_level > 0:
            if not consume_slot(character, slot_level):
                await interaction.response.edit_message(
                    content=f"**{character['name']}** has no level {slot_level} slots remaining.",
                    view=None
                )
                return
            await playerCharactersData.update_character(character)

        cast_type = data["cast_type"]
        header = format_school_header(spell_name, data)
        slot_note = ""
        if slot_level:
            slot_note = f" using a level {slot_level} slot"
        lines = [f"✨ **{character['name']}** casts {header}{slot_note}"]

        if cast_type in ("attack", "save"):
            base = data["damage_dice_base"]
            if data["level"] == 0:
                count, faces = base.lower().split("d")
                total_count = int(count) * cantrip_dice_multiplier(character["level"])
                dmg_expr = f"{total_count}d{faces}"
            else:
                dmg_expr = scale_dice_expr(base, data["scaling_dice"], slot_level - data["level"])
            dmg_total, dmg_breakdown = roll_expression(dmg_expr)

            if cast_type == "attack":
                to_hit_total, to_hit_breakdown = roll_expression(
                    f"1d20{'+' if attack_bonus >= 0 else ''}{attack_bonus}"
                )
                hit_text = ""
                if target_ac is not None:
                    hit_text = " ✅ **HIT**" if to_hit_total >= target_ac else " ❌ **MISS**"
                lines.append(f"To-hit: {to_hit_breakdown} = **{to_hit_total}**{hit_text}")
                lines.append(f"Damage: {dmg_breakdown} = **{dmg_total}** {data['damage_type']}")
            else:
                save_note = "half damage on a successful save" if data["half_on_save"] else "no damage on a successful save"
                lines.append(f"Target saves vs **{data['save_ability']} DC {save_dc}** ({save_note})")
                lines.append(f"Damage: {dmg_breakdown} = **{dmg_total}** {data['damage_type']}")

        elif cast_type == "damage_only":
            base = data["damage_dice_base"]
            if data["level"] == 0:
                # Cantrip scaling by character level.
                count, faces = base.lower().split("d")
                total_count = int(count) * cantrip_dice_multiplier(character["level"])
                dmg_expr = f"{total_count}d{faces}"
            else:
                # Leveled spell: upcast if a higher slot was used and we have scaling.
                extra_levels = slot_level - data["level"]
                scaling = data.get("scaling_dice")
                if scaling and extra_levels > 0:
                    dmg_expr = scale_dice_expr(base, scaling, extra_levels)
                else:
                    dmg_expr = base
            dmg_total, dmg_breakdown = roll_expression(dmg_expr)
            type_note = f" {data['damage_type']}" if data.get("damage_type") else ""
            lines.append(f"Damage: {dmg_breakdown} = **{dmg_total}**{type_note}")
            
                
        elif cast_type == "auto":
            extra_darts = data.get("extra_dart_per_slot", 0) * max(0, slot_level - data["level"])
            darts = data["darts_base"] + extra_darts
            die_count, die_faces = data["die_per_dart"].lower().split("d")
            total_dice = int(die_count) * darts
            flat = data["flat_per_dart"] * darts
            dmg_total, dmg_breakdown = roll_expression(f"{total_dice}d{die_faces}+{flat}")
            lines.append(f"{darts} dart(s) auto-hit, no roll needed")
            lines.append(f"Damage: {dmg_breakdown} = **{dmg_total}** {data['damage_type']}")

        elif cast_type == "heal":
            heal_expr = scale_dice_expr(data["heal_dice_base"], data["scaling_dice"], slot_level - data["level"])
            if data.get("add_ability_mod"):
                heal_expr += f"{'+' if mod >= 0 else ''}{mod}"
            heal_total, heal_breakdown = roll_expression(heal_expr)
            lines.append(f"Healing: {heal_breakdown} = **{heal_total}** HP restored")

        elif cast_type == "utility":
            lines.append(data.get("description", "No damage to roll — this is a utility spell."))

        # Append updated slot state so the caster sees what's left.
        if slot_level > 0:
            lines.append(f"*Slots remaining — {format_slots_for_sheet(character)}*")

        content = "\n".join(lines)
        await interaction.response.edit_message(content="✅ Cast — see below!", view=None)
        await interaction.followup.send(content=content)


async def setup(bot):
    await bot.add_cog(Spells(bot))