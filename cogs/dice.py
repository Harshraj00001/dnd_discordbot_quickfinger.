"""
Dice rolling commands: raw notation rolls and automated ability/skill/save checks.
"""
import re
import random
import discord
from discord import app_commands
from discord.ext import commands

import databaseFolder.playerCharactersData as playerCharactersData
from data.reference import ability_modifier, proficiency_bonus, SKILLS, WEAPONS
from utils.sheet import ABILITY_TO_FIELD
from views.character_ui import PickCharacterView

_TERM_PATTERN = re.compile(
    r"""
    (?P<dice_sign>[+-]?)\s*
    (?P<dice_count>\d*)d(?P<dice_faces>\d+)
    (?:(?P<keep_mode>kh|kl|dh|dl)(?P<keep_n>\d+))?
    |
    (?P<flat_sign>[+-]?)\s*(?P<flat_value>\d+)
    """,
    re.IGNORECASE | re.VERBOSE,
)

MAX_TOTAL_DICE = 100
MAX_DIE_FACES = 1000
MAX_TERMS = 20
MAX_FLAT = 1000


class DiceExprError(ValueError):
    """Raised when a dice expression can't be parsed or is out of bounds."""
    pass


def _tokenize(expr: str):
    """Splits '1d20 + 1d4 - 2' into signed terms."""
    s = re.sub(r"\s+", "", expr)
    if not s:
        raise DiceExprError("Empty expression.")

    terms = []
    current = ""
    sign = 1
    for i, ch in enumerate(s):
        if ch in "+-" and i > 0:
            if not current:
                raise DiceExprError(f"Unexpected '{ch}' in expression.")
            terms.append((sign, current))
            sign = 1 if ch == "+" else -1
            current = ""
        else:
            current += ch

    if not current:
        raise DiceExprError("Expression ends with an operator.")
    terms.append((sign, current))

    if len(terms) > MAX_TERMS:
        raise DiceExprError(f"Too many terms — keep it under {MAX_TERMS}.")
    return terms


def _roll_term(term: str, sign: int):
    """Rolls one term. Returns (signed_value, display_string)."""
    m = _TERM_PATTERN.fullmatch(term)
    if not m:
        raise DiceExprError(f"'{term}' isn't valid dice notation.")

    # Flat modifier.
    if m.group("flat_value") is not None:
        value = int(m.group("flat_value"))
        if value > MAX_FLAT:
            raise DiceExprError(f"Flat modifier too large (max {MAX_FLAT}).")
        return sign * value, f"{value}"

    # Dice.
    count = int(m.group("dice_count")) if m.group("dice_count") else 1
    faces = int(m.group("dice_faces"))
    keep_mode = m.group("keep_mode")
    keep_n = int(m.group("keep_n")) if m.group("keep_n") else None

    if count < 1:
        raise DiceExprError("Dice count must be at least 1.")
    if faces < 2:
        raise DiceExprError("Dice must have at least 2 faces.")
    if faces > MAX_DIE_FACES:
        raise DiceExprError(f"Die size too large (max d{MAX_DIE_FACES}).")

    rolls = [random.randint(1, faces) for _ in range(count)]

    if keep_mode:
        if keep_n is None or keep_n < 1:
            raise DiceExprError(f"'{keep_mode}' needs a positive count (e.g. kh3).")
        if keep_n > count:
            raise DiceExprError(f"Can't keep/drop {keep_n} from only {count} dice.")
        sorted_rolls = sorted(rolls)
        if keep_mode == "kh":
            kept = sorted_rolls[-keep_n:]
        elif keep_mode == "kl":
            kept = sorted_rolls[:keep_n]
        elif keep_mode == "dh":
            kept = sorted_rolls[:count - keep_n]
        elif keep_mode == "dl":
            kept = sorted_rolls[keep_n:]
        else:
            raise DiceExprError(f"Unknown keep/drop mode '{keep_mode}'.")
        value = sum(kept)
        display = f"{count}d{faces}{keep_mode}{keep_n} {rolls}→{kept}={value}"
        if sign < 0:
            display = f"-({display})"
        return sign * value, display

    value = sum(rolls)
    display = f"{count}d{faces} {rolls}={value}"
    if sign < 0:
        display = f"-({display})"
    return sign * value, display


def roll_expression(expr: str):
    """
    Rolls a full dice expression. Returns (total, breakdown_string).

    Supports:
        1d20
        1d20+5
        1d8+1d6+2
        2d20kh1        (advantage)
        2d20kl1        (disadvantage)
        4d6kh3         (ability score roll)
        1d20+1d4+1d8+5+1d4
    """
    terms = _tokenize(expr)

    total_dice = 0
    for _, term in terms:
        m = _TERM_PATTERN.fullmatch(term)
        if m and m.group("dice_faces") is not None:
            count = int(m.group("dice_count")) if m.group("dice_count") else 1
            total_dice += count
    if total_dice > MAX_TOTAL_DICE:
        raise DiceExprError(f"Too many dice total — keep it under {MAX_TOTAL_DICE}.")

    total = 0
    parts = []
    for sign, term in terms:
        value, display = _roll_term(term, sign)
        total += value
        parts.append(display)

    breakdown = " + ".join(parts).replace(" + -", " - ")
    return total, breakdown


class AbilitySelect(discord.ui.Select):
    def __init__(self, on_pick, mode: str, character: dict):
        options = [discord.SelectOption(label=a, value=a) for a in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]]
        super().__init__(placeholder=f"Choose ability for the {mode}...", options=options)
        self.on_pick = on_pick
        self.mode = mode
        self.character = character

    async def callback(self, interaction: discord.Interaction):
        await self.on_pick(interaction, self.character, self.values[0], self.mode)


class PickAbilityView(discord.ui.View):
    def __init__(self, on_pick, mode, character):
        super().__init__(timeout=60)
        self.add_item(AbilitySelect(on_pick, mode, character))


class CheckOptionSelect(discord.ui.Select):
    def __init__(self, on_pick, character):
        options = []
        for ability in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
            options.append(discord.SelectOption(label=f"{ability} (raw check)", value=f"RAW::{ability}"))
        for skill_name, governing_ability in SKILLS.items():
            options.append(discord.SelectOption(label=f"{skill_name} ({governing_ability})", value=f"SKILL::{skill_name}"))
        super().__init__(placeholder="Check what?", options=options[:25])
        self.on_pick = on_pick
        self.character = character

    async def callback(self, interaction: discord.Interaction):
        await self.on_pick(interaction, self.character, self.values[0])


class PickCheckView(discord.ui.View):
    def __init__(self, on_pick, character):
        super().__init__(timeout=60)
        self.add_item(CheckOptionSelect(on_pick, character))


class Dice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="roll", description="Roll dice using standard notation, e.g. 1d20+5")
    async def roll(self, interaction: discord.Interaction, dice: str):
        try:
            total, breakdown = roll_expression(dice)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🎲 **{interaction.user.display_name}** rolls `{dice}`: {breakdown} = **{total}**"
        )

    @app_commands.command(name="attack", description="Attack with your equipped weapon")
    @app_commands.describe(target_ac="Optional: the target's AC, to see if it's a hit")
    async def attack(self, interaction: discord.Interaction, target_ac: int = None):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter` first!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            weapon_name = character.get("weapon", "Unarmed Strike")
            weapon = WEAPONS.get(weapon_name, WEAPONS["Unarmed Strike"])
            ability_key = weapon["ability"]

            if ability_key == "finesse":
                mod = max(ability_modifier(character["str"]), ability_modifier(character["dex"]))
            else:
                mod = ability_modifier(character[ABILITY_TO_FIELD[ability_key]])

            attack_mod = mod + proficiency_bonus(character["level"])
            to_hit_total, to_hit_breakdown = roll_expression(f"1d20{'+' if attack_mod >= 0 else ''}{attack_mod}")

            hit_text = ""
            if target_ac is not None:
                hit_text = " ✅ **HIT**" if to_hit_total >= target_ac else " ❌ **MISS**"

            dmg_total, dmg_breakdown = roll_expression(f"{weapon['dice']}{'+' if mod >= 0 else ''}{mod}")

            content = (
                f"⚔️ **{character['name']}** attacks with **{weapon_name}**\n"
                f"To-hit: {to_hit_breakdown} = **{to_hit_total}**{hit_text}\n"
                f"Damage: {dmg_breakdown} = **{dmg_total}** {weapon['damage_type']}"
            )
            await inter.response.edit_message(content="✅ Rolled — see below!", view=None)
            await inter.followup.send(content=content)

        await interaction.response.send_message(
            "Which character is attacking?", view=PickCharacterView(characters, character_chosen), ephemeral=True
        )

    @app_commands.command(name="check", description="Roll an ability or skill check for one of your characters")
    async def check(self, interaction: discord.Interaction):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter` first!", ephemeral=True
            )
            return

        async def option_chosen(inter, character, value):
            kind, key = value.split("::", 1)
            skill_profs = character.get("skill_proficiencies", [])

            if kind == "RAW":
                ability = key
                label = f"{ability} check"
                modifier = ability_modifier(character[ABILITY_TO_FIELD[ability]])
            else:
                skill_name = key
                ability = SKILLS[skill_name]
                label = f"{skill_name} check"
                modifier = ability_modifier(character[ABILITY_TO_FIELD[ability]])
                if skill_name in skill_profs:
                    modifier += proficiency_bonus(character["level"])

            total, breakdown = roll_expression(f"1d20{'+' if modifier >= 0 else ''}{modifier}")
            content = f"🎲 **{character['name']}** rolls a **{label}**: {breakdown} = **{total}**"
            await inter.response.edit_message(content="✅ Rolled — see below!", view=None)
            await inter.followup.send(content=content)

        async def character_chosen(inter, character):
            await inter.response.edit_message(
                content=f"What is {character['name']} checking?",
                view=PickCheckView(option_chosen, character)
            )

        await interaction.response.send_message(
            "Which character?", view=PickCharacterView(characters, character_chosen), ephemeral=True
        )

    @app_commands.command(name="save", description="Roll a saving throw for one of your characters")
    async def save(self, interaction: discord.Interaction):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter` first!", ephemeral=True
            )
            return

        async def ability_chosen(inter, character, ability, mode):
            score = character[ABILITY_TO_FIELD[ability]]
            modifier = ability_modifier(score)
            proficient_saves = character.get("save_proficiencies", [])
            if ability in proficient_saves:
                modifier += proficiency_bonus(character["level"])
            total, breakdown = roll_expression(f"1d20{'+' if modifier >= 0 else ''}{modifier}")
            content = f"🛡️ **{character['name']}** rolls a **{ability}** save: {breakdown} = **{total}**"
            await inter.response.edit_message(content="✅ Rolled — see below!", view=None)
            await inter.followup.send(content=content)

        async def character_chosen(inter, character):
            await inter.response.edit_message(
                content=f"Which ability is {character['name']} saving with?",
                view=PickAbilityView(ability_chosen, "save", character)
            )

        await interaction.response.send_message(
            "Which character?", view=PickCharacterView(characters, character_chosen), ephemeral=True
        )

    @app_commands.command(name="initiative", description="Roll initiative (1d20 + DEX mod) for one of your characters")
    @app_commands.describe(bonus="Optional bonus to add (e.g. Alert feat's +5)")
    async def initiative(self, interaction: discord.Interaction, bonus: int = 0):
        characters = await playerCharactersData.get_characters_for_user(interaction.user.id, interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                "You don't have any characters yet — try `/newcharacter` first!", ephemeral=True
            )
            return

        async def character_chosen(inter, character):
            dex_mod = ability_modifier(character["dex"])
            total_mod = dex_mod + bonus

            total, breakdown = roll_expression(f"1d20{'+' if total_mod >= 0 else ''}{total_mod}")

            bonus_note = f" (DEX {dex_mod:+d}"
            if bonus:
                bonus_note += f", bonus {bonus:+d}"
            bonus_note += ")"

            content = f"⚡ **{character['name']}** rolls initiative: {breakdown} = **{total}**{bonus_note}"
            await inter.response.edit_message(content="✅ Rolled — see below!", view=None)
            await inter.followup.send(content=content)

        await interaction.response.send_message(
            "Which character is rolling initiative?",
            view=PickCharacterView(characters, character_chosen),
            ephemeral=True
        ) 


async def setup(bot):
    await bot.add_cog(Dice(bot))