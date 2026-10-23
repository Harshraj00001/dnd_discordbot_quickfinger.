"""
Character sheet math, embed building, and stat recalculation helpers.
"""
import discord
import databaseFolder.playerCharactersData as playerCharactersData
from data.reference import (
    CLASSES, SKILLS, WEAPONS, ARMOR, RACE_TRAITS, CLASS_FEATURES_L1,
    
    SPELLCASTING_ABILITY, SPELLS, ability_modifier, proficiency_bonus
)
from character_engine import StatCalculator
from utils.spell_slots import format_slots_for_sheet

ABILITY_TO_FIELD = {"STR": "str", "DEX": "dex", "CON": "con", "INT": "intl", "WIS": "wis", "CHA": "cha"}
FIELD_TO_ABILITY = {v: k for k, v in ABILITY_TO_FIELD.items()}


def add_safe_field(embed: discord.Embed, name: str, lines: list, inline: bool = False):
    if not lines:
        return
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > 1000:
            if current_chunk.strip():
                embed.add_field(name=name, value=current_chunk.strip(), inline=inline)
                name = f"{name} (cont.)"
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk.strip():
        embed.add_field(name=name, value=current_chunk.strip(), inline=inline)


def _get_hit_die(character: dict, custom_class: dict = None) -> int:
    if character.get("is_homebrew_class"):
        return custom_class["hit_die"] if custom_class else 8
    return CLASSES.get(character["class_name"], {}).get("hit_die", 8)


async def recalculate_character_stats(character: dict) -> dict:
    """Recomputes derived stats (HP, AC, passive perception) using StatCalculator."""
    custom = None
    if character.get("is_homebrew_class"):
        custom = await playerCharactersData.get_custom_class_by_name(
            character["guild_id"], character["class_name"]
        )

    hit_die = _get_hit_die(character, custom)

    # Scores are already final at this point — feed them in as base scores.
    base_scores = {FIELD_TO_ABILITY[f]: character[f] for f in ABILITY_TO_FIELD.values()}

    computed = StatCalculator.compute(
        base_scores=base_scores,
        race=None,
        applied_modifiers=[],
        level=character["level"],
        hit_die=hit_die,
        class_skills=character.get("skill_proficiencies", []),
    )

    character["max_hp"] = computed.max_hp
    if character["current_hp"] > character["max_hp"]:
        character["current_hp"] = character["max_hp"]

    dex_mod = ability_modifier(character["dex"])
    armor_data = ARMOR.get(character.get("armor", "None"), ARMOR["None"])
    dex_cap = armor_data["dex_cap"]
    effective_dex_bonus = dex_mod if dex_cap is None else min(dex_mod, dex_cap)

    ac = armor_data["base_ac"] + effective_dex_bonus
    if character.get("has_shield"):
        ac += ARMOR["Shield"]["ac_bonus"]
    character["ac"] = ac
    character["passive_perception"] = computed.passive_perception

    return character


async def get_homebrew_features_for(character: dict):
    if not character.get("is_homebrew_class"):
        return None
    custom = await playerCharactersData.get_custom_class_by_name(character["guild_id"], character["class_name"])
    return custom.get("features", []) if custom else None


async def get_homebrew_race_traits_for(character: dict):
    if not character.get("is_homebrew_race"):
        return None
    custom = await playerCharactersData.get_custom_race_by_name(character["guild_id"], character["race"])
    return custom.get("traits", []) if custom else None


def format_ability_table(character: dict) -> str:
    order = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    cells = []
    for a in order:
        score = character[ABILITY_TO_FIELD[a]]
        mod = ability_modifier(score)
        sign = "+" if mod >= 0 else ""
        cells.append(f"{a} {score:>2} ({sign}{mod})")
    row1 = "  ".join(cells[0:3])
    row2 = "  ".join(cells[3:6])
    return f"```\n{row1}\n{row2}\n```"


def build_sheet_embed(character: dict, homebrew_features: list = None, homebrew_race_traits: list = None) -> discord.Embed:
    embed = discord.Embed(
        title=character["name"],
        description=f"Level {character['level']} {character['race']} {character['class_name']}",
        color=discord.Color.dark_gold()
    )
    embed.add_field(name="Ability Scores", value=format_ability_table(character), inline=False)

    combat_line = (
        f"HP: {character['current_hp']}/{character['max_hp']}   "
        f"AC: {character['ac']}   "
        f"Prof: +{proficiency_bonus(character['level'])}   "
        f"Passive Perc: {character.get('passive_perception', 10)}"
    )
    embed.add_field(name="Combat", value=f"```\n{combat_line}\n```", inline=False)

    weapon = character.get("weapon", "Unarmed Strike")
    weapon_stats = WEAPONS.get(weapon, WEAPONS["Unarmed Strike"])
    armor_label = character.get("armor", "None")
    if character.get("has_shield"):
        armor_label += " + Shield"
    gear_lines = f"Weapon: {weapon} ({weapon_stats['dice']} {weapon_stats['damage_type']})\nArmor:  {armor_label}"
    embed.add_field(name="Gear", value=f"```\n{gear_lines}\n```", inline=False)

    saves = character.get("save_proficiencies", [])
    prof_b = proficiency_bonus(character["level"])
    save_lines = []

    for stat, field in ABILITY_TO_FIELD.items():
        score = character[field]
        mod = ability_modifier(score)
        is_proficient = stat in saves
        total = mod + (prof_b if is_proficient else 0)
        sign = "+" if total >= 0 else ""
        marker = "✓ " if is_proficient else ""
        save_lines.append(f"{marker}**{stat}** ({sign}{total})")

    embed.add_field(
        name="Saving Throws",
        value=", ".join(save_lines),
        inline=False
    )

    skill_profs = character.get("skill_proficiencies", [])
    skill_lines = []
    for skill_name, governing_ability in SKILLS.items():
        score = character[ABILITY_TO_FIELD[governing_ability]]
        bonus = ability_modifier(score)
        is_proficient = skill_name in skill_profs
        if is_proficient:
            bonus += prof_b
        sign = "+" if bonus >= 0 else ""
        marker = "⭐ " if is_proficient else ""
        skill_lines.append(f"{marker}{skill_name} ({governing_ability}): {sign}{bonus}")

    add_safe_field(embed, "Skills", skill_lines, inline=False)

    if character.get("is_homebrew_race"):
        race_traits = homebrew_race_traits or ["This is a custom race with no traits written yet."]
    else:
        race_traits = RACE_TRAITS.get(character["race"], [])

    if character.get("is_homebrew_class"):
        class_features = homebrew_features or ["This is a homebrew class with no features written yet."]
    else:
        class_features = CLASS_FEATURES_L1.get(character["class_name"], [])

    feature_lines = [f"🏷️ {t}" for t in race_traits] + [f"⚔️ {f}" for f in class_features]
    add_safe_field(embed, "Features & Traits", feature_lines, inline=False)

    caster_type = None
    if character.get("is_homebrew_class"):
        caster_type = character.get("caster_type")
    else:
        caster_type = CLASSES.get(character["class_name"], {}).get("caster")

    if caster_type:
        if character.get("is_homebrew_class"):
            spell_ability = character.get("spellcasting_ability")
        else:
            spell_ability = SPELLCASTING_ABILITY.get(character["class_name"])

        spell_mod = ability_modifier(character[ABILITY_TO_FIELD[spell_ability]]) if spell_ability else 0
        spell_dc = 8 + prof_b + spell_mod
        spell_attack = prof_b + spell_mod
        level = character["level"]

        slots_text = format_slots_for_sheet(character)

        known_spells = character.get("known_spells", [])

        def label_spell(name):
            info = SPELLS.get(name)
            if not info:
                return name
            level_label = "Cantrip" if info["level"] == 0 else f"L{info['level']}"
            return f"{name} ({level_label} {info['school']})"

        spells_text = ", ".join(label_spell(s) for s in known_spells) if known_spells else "*(none entered)*"

        embed.add_field(
            name="Spellcasting",
            value=(f"Ability: **{spell_ability}** | Save DC: **{spell_dc}** | Attack: **+{spell_attack}**\n"
                   f"Slots: {slots_text}\nKnown: {spells_text}"),
            inline=False
        )

    return embed