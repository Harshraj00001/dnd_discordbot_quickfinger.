"""
Character creation wizard, custom race builder, homebrew class builder,
and character finalization logic.
"""
import random
import discord
from discord import app_commands
from discord.ext import commands
from character_engine import RuleDatabase, StatCalculator, Modifier
from character_creation.constants import (
    ABILITIES,
    MIN_CUSTOM_SCORE,
    MAX_CUSTOM_SCORE,
    TWO_HANDED_WEAPONS,
)
from character_creation.custom_race import (
    AsiTemplateView,
    AbilitySelect,
    AbilitySelectView,
)

import databaseFolder.playerCharactersData as playerCharactersData
from data.reference import (
    RACES, CLASSES, SKILLS, ARMOR, STARTING_GEAR, DEFAULT_HOMEBREW_GEAR,
    ability_modifier
)
from utils.sheet import (
    build_sheet_embed,
    get_homebrew_features_for, get_homebrew_race_traits_for
)
from views.character_ui import (
    NameModal, RaceView, ClassView, LevelPickView, ScoreMethodView, DiceResultView,
    AssignArrayView, CustomScorePart1Modal, CustomScorePart2Modal, ModalTriggerView,
    SkillPickView, WeaponPickView, ArmorPickView, ShieldView,
    HomebrewInfoModal, HitDieView, SavesView, HomebrewFeaturesModal,
    RaceNameModal, RaceTraitsModal
)
from views.spell_ui import SpellsModal




def roll_ability_array():
    results = []
    for _ in range(6):
        dice = sorted(random.randint(1, 6) for _ in range(4))
        results.append(sum(dice[1:]))
    return sorted(results, reverse=True)


def parse_score(raw: str):
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    if value < MIN_CUSTOM_SCORE or value > MAX_CUSTOM_SCORE:
        return None
    return value

#---DELETE RACE COMMAND---
class DeleteRaceSelect(discord.ui.Select):
    def __init__(self, custom_races: list):
        options = [
            discord.SelectOption(
                label=race_name,
                description=f"Delete custom race '{race_name}'",
                emoji="🗑️"
            )
            for race_name in custom_races[:25]
        ]
        super().__init__(placeholder="Select a custom race to delete...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_race = self.values[0]

        try:
            # 1. Attempt database deletion first
            await playerCharactersData.delete_custom_race(interaction.guild_id, selected_race)

            # 2. Disable dropdown on success
            self.disabled = True

            # 3. Edit the original message ONCE to show success and apply disabled view
            await interaction.response.edit_message(
                content=f"✅ Custom race **{selected_race}** has been successfully deleted from this server!",
                view=self.view
            )

        except Exception as e:
            # 4. Respond with error if database operation fails
            await interaction.response.send_message(
                f"❌ Failed to delete **{selected_race}**: `{e}`",
                ephemeral=True
            )


class DeleteRaceView(discord.ui.View):
    def __init__(self, custom_races: list):
        super().__init__(timeout=60)
        self.add_item(DeleteRaceSelect(custom_races))

        




        

class CharacterCreation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="newcharacter", description="Create a new D&D character step by step")
    async def newcharacter(self, interaction: discord.Interaction):
        state = {"user_id": interaction.user.id, "guild_id": interaction.guild_id}

        async def name_submitted(inter, name):
            state["name"] = name
            custom_races = await playerCharactersData.get_custom_races(inter.guild_id)
            

            
            race_view = RaceView(race_chosen, custom_races)
            

            try:
                await inter.response.send_message(
                    f"Nice, **{name}**! Now pick a race:",
                    view=race_view,
                    ephemeral=True
                    )
                

            except Exception as e:
                print("[ERROR] RaceView response failed")
                print(type(e).__name__)
                print(e)

        async def race_chosen(inter: discord.Interaction, race: str):
            try:
                if race == "__new_custom_race__":
                    await inter.response.send_modal(RaceNameModal(
                        lambda i, n: self._start_custom_race_flow(i, n, resume_cb=race_chosen)
                    ))
                    return

                if race in RACES:
                    state["race"] = race
                    state["is_homebrew_race"] = False
                    state["race_blueprint"] = RACES[race]
                else:
                    state["race"] = race
                    state["is_homebrew_race"] = True
                    
                    # 1. Fetch custom race data from main database
                    custom_race_data = await playerCharactersData.get_custom_race_by_name(inter.guild_id, race)
                    
                    # 2. Fallback to RuleDatabase without `await` if missing in playersCharacterData.py
                    if not custom_race_data and 'RuleDatabase' in globals():
                        race_key = f"custom_{race.lower().replace(' ', '_')}"
                        custom_race_data = RuleDatabase.get_race(race_key) # SYNC call (no await)
                    
                    state["race_blueprint"] = custom_race_data

                # Fetch available classes
                custom_classes = await playerCharactersData.get_custom_classes(inter.guild_id)

                # Edit message to move to Class selection step
                await inter.response.edit_message(
                    content=f"Race chosen: **{race}**! Now pick a class:",
                    view=ClassView(class_chosen, custom_classes)
                )

            except Exception as e:
                print(f"[ERROR] Exception in race_chosen for race '{race}': {e}")
                import traceback
                traceback.print_exc()
                
                err_msg = f"❌ An error occurred while selecting **{race}**: `{e}`"
                if inter.response.is_done():
                    await inter.followup.send(err_msg, ephemeral=True)
                else:
                    await inter.response.send_message(err_msg, ephemeral=True)

        async def class_chosen(inter, class_name):
            if class_name == "__new_homebrew__":
                await inter.response.send_modal(HomebrewInfoModal(
                    lambda i, n: self._start_homebrew_flow(i, n, resume_after=state, resume_cb=class_chosen)
                ))
                return

            standard = CLASSES.get(class_name)
            if standard:
                state["class_name"] = class_name
                state["is_homebrew_class"] = False
                state["save_proficiencies"] = standard["saves"]
                state["skill_list"] = standard["skill_list"]
                state["skill_choices"] = standard["skill_choices"]
                state["gear_options"] = STARTING_GEAR.get(class_name, DEFAULT_HOMEBREW_GEAR)
                state["caster_type"] = standard["caster"]
                hit_die = standard["hit_die"]
            else:
                custom = await playerCharactersData.get_custom_class_by_name(inter.guild_id, class_name)
                state["class_name"] = custom["name"]
                state["is_homebrew_class"] = True
                state["save_proficiencies"] = custom["saves"]
                state["skill_list"] = custom["skill_list"]
                state["skill_choices"] = custom["skill_choices"]
                state["gear_options"] = DEFAULT_HOMEBREW_GEAR
                state["caster_type"] = None
                hit_die = custom["hit_die"]

            state["hit_die"] = hit_die
            state["scores"] = {}
            await inter.response.edit_message(
                content=f"Class: **{class_name}**. What level is this character?",
                view=LevelPickView(level_chosen)
            )

        async def level_chosen(inter, level):
            state["level"] = level
            await inter.response.edit_message(
                content=(f"Level **{level}**. How do you want to set ability scores?\n"
                         f"Roll dice for a random set, or type in your own numbers if you already "
                         f"have a character sheet made."),
                view=ScoreMethodView(method_chosen)
            )

        async def method_chosen(inter, method):
            if method == "custom":
                await inter.response.send_modal(CustomScorePart1Modal(custom_part1_submitted))
                return

            state["remaining_array"] = roll_ability_array()
            await inter.response.edit_message(
                content=(f"🎲 Rolled: `{state['remaining_array']}`\n"
                         f"Happy with these, or want to try again?"),
                view=DiceResultView(dice_confirmed, dice_reroll)
            )

        async def dice_reroll(inter, _method):
            state["remaining_array"] = roll_ability_array()
            await inter.response.edit_message(
                content=(f"🎲 Rerolled: `{state['remaining_array']}`\n"
                         f"Happy with these, or want to try again?"),
                view=DiceResultView(dice_confirmed, dice_reroll)
            )

        async def dice_confirmed(inter, _method):
            await inter.response.edit_message(
                content=(f"Scores to assign: `{state['remaining_array']}`\n"
                         f"Tap an ability, and its next score is `{state['remaining_array'][0]}`. "
                         f"Put your biggest number on what matters most for this class!"),
                view=AssignArrayView(score_assigned, ABILITIES)
            )

        async def score_assigned(inter, ability):
            value = state["remaining_array"].pop(0)
            state["scores"][ability] = value
            remaining_abilities = [a for a in ABILITIES if a not in state["scores"]]
            if remaining_abilities:
                await inter.response.edit_message(
                    content=(f"{ability} = **{value}**. Next score is `{state['remaining_array'][0]}` "
                             f"— pick another ability:"),
                    view=AssignArrayView(score_assigned, remaining_abilities)
                )
            else:
                await self._prompt_skills(inter, state, skills_chosen, use_edit=True)

        async def custom_part1_submitted(inter, values):
            parsed = {k: parse_score(v) for k, v in values.items()}
            if any(v is None for v in parsed.values()):
                async def reopen(reopen_inter):
                    await reopen_inter.response.send_modal(CustomScorePart1Modal(custom_part1_submitted))
                await inter.response.send_message(
                    f"⚠️ Ability scores need to be whole numbers between {MIN_CUSTOM_SCORE} and "
                    f"{MAX_CUSTOM_SCORE}. Let's try that again:",
                    view=ModalTriggerView(reopen, label="Try again"), ephemeral=True
                )
                return
            state["scores"].update(parsed)

            async def open_part2(part2_inter):
                await part2_inter.response.send_modal(CustomScorePart2Modal(custom_part2_submitted))

            await inter.response.send_message(
                f"STR **{parsed['STR']}**, DEX **{parsed['DEX']}**, CON **{parsed['CON']}** set. "
                f"Tap below to enter INT, WIS, and CHA:",
                view=ModalTriggerView(open_part2, label="Continue ➜ INT / WIS / CHA"), ephemeral=True
            )

        async def custom_part2_submitted(inter, values):
            parsed = {k: parse_score(v) for k, v in values.items()}
            if any(v is None for v in parsed.values()):
                async def reopen(reopen_inter):
                    await reopen_inter.response.send_modal(CustomScorePart2Modal(custom_part2_submitted))
                await inter.response.send_message(
                    f"⚠️ Ability scores need to be whole numbers between {MIN_CUSTOM_SCORE} and "
                    f"{MAX_CUSTOM_SCORE}. Let's try that again:",
                    view=ModalTriggerView(reopen, label="Try again"), ephemeral=True
                )
                return
            state["scores"].update(parsed)
            await self._prompt_skills(inter, state, skills_chosen, use_edit=False)

        async def skills_chosen(inter, skills):
            state["skill_proficiencies"] = list(skills)
            weapon_options = state["gear_options"]["weapons"]
            await inter.response.edit_message(
                content="Skills set! Now pick your starting weapon:",
                view=WeaponPickView(weapon_chosen, weapon_options)
            )

        async def weapon_chosen(inter, weapon):
            state["weapon"] = weapon
            armor_options = state["gear_options"]["armor"]
            await inter.response.edit_message(
                content=f"Weapon: **{weapon}**. Now pick your starting armor:",
                view=ArmorPickView(armor_chosen, armor_options)
            )

        async def armor_chosen(inter, armor):
            state["armor"] = armor
            two_handed = TWO_HANDED_WEAPONS
            if state["weapon"] in two_handed:
                state["has_shield"] = False
                await self._maybe_ask_spells(inter, state, use_edit=True)
            else:
                await inter.response.edit_message(
                    content=f"Armor: **{armor}**. Want to carry a shield too?",
                    view=ShieldView(shield_chosen)
                )

        async def shield_chosen(inter, wants_shield):
            state["has_shield"] = wants_shield
            await self._maybe_ask_spells(inter, state, use_edit=True)

        async def spells_submitted(inter, spells):
            state["known_spells"] = spells
            await self._finalize_character(inter, state)

        state["_spells_submitted_callback"] = spells_submitted
        await interaction.response.send_modal(NameModal(name_submitted))

    async def _prompt_skills(self, interaction, state, skills_chosen_callback, use_edit: bool):
        n = state["skill_choices"]
        content = f"Scores set! Now pick **{n}** skill{'s' if n != 1 else ''} your character is trained in:"
        view = SkillPickView(skills_chosen_callback, state["skill_list"], n)
        if use_edit:
            await interaction.response.edit_message(content=content, view=view)
        else:
            await interaction.response.send_message(content=content, view=view, ephemeral=True)

    async def _start_homebrew_flow(self, interaction, class_name, resume_after, resume_cb):
        state = {"guild_id": interaction.guild_id, "created_by": interaction.user.id, "name": class_name}

        async def hit_die_chosen(inter, hit_die):
            state["hit_die"] = hit_die
            await inter.response.edit_message(
                content=f"**{class_name}** uses a d{hit_die} hit die. Now pick 2 saving throw proficiencies:",
                view=SavesView(saves_chosen)
            )

        async def saves_chosen(inter, saves):
            state["saves"] = list(saves)
            state["skill_choices"] = 2
            state["skill_list"] = list(SKILLS.keys())
            state["is_caster"] = False
            await inter.response.send_modal(HomebrewFeaturesModal(features_submitted))

        async def features_submitted(inter, feature_lines):
            state["features"] = feature_lines
            await playerCharactersData.save_custom_class(state)
            feature_summary = f" with {len(feature_lines)} feature(s)" if feature_lines else " (no features written)"
            await inter.response.send_message(
                content=(f"✅ Homebrew class **{class_name}** created! (d{state['hit_die']} hit die, "
                         f"saves: {', '.join(state['saves'])}){feature_summary}.\n\nNow pick your class again "
                         f"from the list to continue building your character:"),
                view=ClassView(resume_cb, await playerCharactersData.get_custom_classes(interaction.guild_id)),
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Building homebrew class **{class_name}**. Pick a hit die:",
            view=HitDieView(hit_die_chosen), ephemeral=True
        )

    async def _start_custom_race_flow(self, interaction, race_name, resume_cb):
        state = {
            "guild_id": interaction.guild_id,
            "created_by": interaction.user.id,
            "name": race_name,
            "asi": {}
        }

        async def template_chosen(inter: discord.Interaction, template: str):
            # 1. Standard: +2 to one stat, +1 to another
            if template == "standard":
                async def primary_chosen(inter_p, selected):
                    primary_stat = selected[0]
                    state["asi"][primary_stat] = 2
                    remaining = [a for a in ABILITIES if a != primary_stat]

                    async def secondary_chosen(inter_s, selected_s):
                        secondary_stat = selected_s[0]
                        state["asi"][secondary_stat] = 1
                        await inter_s.response.send_modal(RaceTraitsModal(traits_submitted))

                    await inter_p.response.edit_message(
                        content=f"Primary (+2): **{primary_stat}**. Now pick 1 secondary ability to get **+1**:",
                        view=AbilitySelectView(secondary_chosen, options_list=remaining, min_values=1, max_values=1, placeholder="Select secondary ability (+1)...")
                    )

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+2 / +1). Pick 1 primary ability to get **+2**:",
                    view=AbilitySelectView(primary_chosen, options_list=ABILITIES, min_values=1, max_values=1, placeholder="Select primary ability (+2)...")
                )

            # 2. Triple: +1 to three different stats
            elif template == "triple":
                async def triple_chosen(inter_t, selected):
                    for stat in selected:
                        state["asi"][stat] = 1
                    await inter_t.response.send_modal(RaceTraitsModal(traits_submitted))

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+1 / +1 / +1). Pick 3 abilities to get **+1** each:",
                    view=AbilitySelectView(triple_chosen, options_list=ABILITIES, min_values=3, max_values=3, placeholder="Select 3 abilities...")
                )

            # 3. Dual Heavy: +2 to two stats (Mountain Dwarf)
            elif template == "dual_heavy":
                async def dual_chosen(inter_d, selected):
                    for stat in selected:
                        state["asi"][stat] = 2
                    await inter_d.response.send_modal(RaceTraitsModal(traits_submitted))

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+2 / +2). Pick 2 abilities to get **+2** each:",
                    view=AbilitySelectView(dual_chosen, options_list=ABILITIES, min_values=2, max_values=2, placeholder="Select 2 abilities...")
                )

            # 4. Half-Elf Style: +2 to one stat, +1 to two stats
            elif template == "half_elf":
                async def primary_chosen(inter_p, selected):
                    primary_stat = selected[0]
                    state["asi"][primary_stat] = 2
                    remaining = [a for a in ABILITIES if a != primary_stat]

                    async def secondaries_chosen(inter_s, selected_s):
                        for stat in selected_s:
                            state["asi"][stat] = 1
                        await inter_s.response.send_modal(RaceTraitsModal(traits_submitted))

                    await inter_p.response.edit_message(
                        content=f"Primary (+2): **{primary_stat}**. Pick 2 secondary abilities to get **+1** each:",
                        view=AbilitySelectView(secondaries_chosen, options_list=remaining, min_values=2, max_values=2, placeholder="Select 2 secondary abilities...")
                    )

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+2 / +1 / +1). Pick 1 primary ability to get **+2**:",
                    view=AbilitySelectView(primary_chosen, options_list=ABILITIES, min_values=1, max_values=1, placeholder="Select primary ability (+2)...")
                )

             # Single Light: +1 to one stat
            elif template == "single_light":
                async def single_light_chosen(inter_sl, selected):
                    stat = selected[0]
                    state["asi"][stat] = 1
                    await inter_sl.response.send_modal(RaceTraitsModal(traits_submitted))

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+1). Pick 1 ability to get **+1**:",
                    view=AbilitySelectView(single_light_chosen, options_list=ABILITIES, min_values=1, max_values=1, placeholder="Select 1 ability (+1)...")
                )   

             # Dual Light: +1 to two different stats
            elif template == "dual_light":
                async def dual_light_chosen(inter_dl, selected):
                    for stat in selected:
                        state["asi"][stat] = 1
                    await inter_dl.response.send_modal(RaceTraitsModal(traits_submitted))

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+1 / +1). Pick 2 abilities to get **+1** each:",
                    view=AbilitySelectView(dual_light_chosen, options_list=ABILITIES, min_values=2, max_values=2, placeholder="Select 2 abilities (+1 each)...")
                )

             # Tradeoff: +2 to one stat, +1 to another, -2 to a third
            elif template == "tradeoff":
                async def primary_chosen(inter_p, selected_p):
                    primary_stat = selected_p[0]
                    state["asi"][primary_stat] = 2
                    remaining_for_plus1 = [a for a in ABILITIES if a != primary_stat]

                    async def secondary_chosen(inter_s, selected_s):
                        secondary_stat = selected_s[0]
                        state["asi"][secondary_stat] = 1
                        remaining_for_minus2 = [a for a in remaining_for_plus1 if a != secondary_stat]

                        async def penalty_chosen(inter_pen, selected_pen):
                            penalty_stat = selected_pen[0]
                            state["asi"][penalty_stat] = -2
                            await inter_pen.response.send_modal(RaceTraitsModal(traits_submitted))

                        await inter_s.response.edit_message(
                            content=f"Primary (+2): **{primary_stat}**, Secondary (+1): **{secondary_stat}**. Pick 1 ability to get **-2**:",
                            view=AbilitySelectView(penalty_chosen, options_list=remaining_for_minus2, min_values=1, max_values=1, placeholder="Select penalty ability (-2)...")
                        )

                    await inter_p.response.edit_message(
                        content=f"Primary (+2): **{primary_stat}**. Pick 1 secondary ability to get **+1**:",
                        view=AbilitySelectView(secondary_chosen, options_list=remaining_for_plus1, min_values=1, max_values=1, placeholder="Select secondary ability (+1)...")
                    )

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+2 / +1 / -2). Pick 1 primary ability to get **+2**:",
                    view=AbilitySelectView(primary_chosen, options_list=ABILITIES, min_values=1, max_values=1, placeholder="Select primary ability (+2)...")
                )   

             # Single Heavy: +2 to one stat
            elif template == "single_heavy":
                async def single_heavy_chosen(inter_sh, selected):
                    stat = selected[0]
                    state["asi"][stat] = 2
                    await inter_sh.response.send_modal(RaceTraitsModal(traits_submitted))

                await inter.response.edit_message(
                    content=f"Building **{race_name}** (+2). Pick 1 ability to get **+2**:",
                    view=AbilitySelectView(single_heavy_chosen, options_list=ABILITIES, min_values=1, max_values=1, placeholder="Select 1 ability (+2)...")
                )      

            # 5. Custom / Human +1 All
            elif template == "custom":
                state["asi"] = {stat: 1 for stat in ABILITIES}
                await inter.response.send_modal(RaceTraitsModal(traits_submitted))

        async def traits_submitted(inter: discord.Interaction, trait_lines):
            

            # 1. Defer immediately so Discord knows the bot is working
            await inter.response.defer(ephemeral=True)
            

            state["traits"] = trait_lines
            

            await playerCharactersData.save_custom_race(state)
            

            summary_asi = ", ".join(f"{'+' if v > 0 else ''}{v} {k}" for k, v in state["asi"].items())
            

            trait_summary = f" with {len(trait_lines)} trait(s)" if trait_lines else " (no traits written)"
            

            # If triggered inside /newcharacter, prompt to resume character creation
            if resume_cb:
                content = (f"✅ Custom race **{race_name}** created! ({summary_asi}){trait_summary}.\n\n"
                           f"Now pick your race again from the list to continue building your character:")
                view = RaceView(resume_cb, await playerCharactersData.get_custom_races(interaction.guild_id))
                
            else:
                # Standalone command finished
                content = f"✅ Custom race **{race_name}** created! ({summary_asi}){trait_summary}."
                view = None
                

            # FIXED: Uses `content` and `view` dynamically
            

             
            if view is not None:
                await inter.followup.send(
                    content=content,
                    view=view,
                    ephemeral=True
                    )
            else:
                await inter.followup.send(
                    content=content,
                    ephemeral=True
                    )

        await interaction.response.send_message(
            f"Building custom race **{race_name}**. Choose an Ability Score Increase template:",
            view=AsiTemplateView(template_chosen),
            ephemeral=True
        )

    async def _maybe_ask_spells(self, interaction, state, use_edit: bool):
        if state.get("caster_type"):
            callback = state["_spells_submitted_callback"]
            await interaction.response.send_modal(SpellsModal(callback))
        else:
            await self._finalize_character(interaction, state, use_edit=use_edit)

    async def _finalize_character(self, interaction: discord.Interaction, state: dict, use_edit: bool = True):
        try:
            scores = state["scores"]
            level = state.get("level", 1)
            
            # 1. Resolve Race Blueprint or convert race dictionary to Modifiers
            race_bp = state.get("race_blueprint")
            race_modifiers = []
            
            if isinstance(race_bp, dict):
                # Handles both RACES dict and custom database race dicts safely
                srd_asi = race_bp.get("asi", {})
                if isinstance(srd_asi, dict):
                    race_modifiers = [
                        Modifier(source=state["race"], target="ability_score", stat=stat, value=val)
                        for stat, val in srd_asi.items()
                    ]
                elif isinstance(srd_asi, list):
                    race_modifiers = [
                        Modifier(source=state["race"], target="ability_score", stat=stat, value=1)
                        for stat in srd_asi
                    ]
            elif not race_bp and state["race"] in RACES:
                srd_asi = RACES[state["race"]].get("asi", {})
                race_modifiers = [
                    Modifier(source=state["race"], target="ability_score", stat=stat, value=val)
                    for stat, val in srd_asi.items()
                ]

            # 2. Run calculations through StatCalculator safely
            computed = StatCalculator.compute(
                base_scores=scores,
                race=race_bp if not isinstance(race_bp, dict) else None,
                applied_modifiers=race_modifiers,
                level=level,
                hit_die=state["hit_die"],
                class_skills=state.get("skill_proficiencies", [])
            )

            final_scores = computed.final_scores
            max_hp = computed.max_hp
            dex_mod = ability_modifier(final_scores["DEX"])

            # Safe armor lookup fallback
            armor_name = state.get("armor", "None")
            armor_data = ARMOR.get(armor_name, ARMOR.get("None", {"base_ac": 10, "dex_cap": None}))
            dex_cap = armor_data["dex_cap"]
            effective_dex_bonus = dex_mod if dex_cap is None else min(dex_mod, dex_cap)
            ac = armor_data["base_ac"] + effective_dex_bonus
            if state.get("has_shield"):
                ac += ARMOR.get("Shield", {}).get("ac_bonus", 2)

            character_data = {
                "user_id": state["user_id"],
                "guild_id": state["guild_id"],
                "name": state["name"],
                "race": state["race"],
                "class_name": state["class_name"],
                "is_homebrew_class": state["is_homebrew_class"],
                "level": level,
                "str": final_scores["STR"], "dex": final_scores["DEX"], "con": final_scores["CON"],
                "intl": final_scores["INT"], "wis": final_scores["WIS"], "cha": final_scores["CHA"],
                "max_hp": max_hp, "current_hp": max_hp, "ac": ac,
                "passive_perception": computed.passive_perception,
                "skill_proficiencies": state.get("skill_proficiencies", []),
                "save_proficiencies": state["save_proficiencies"],
                "weapon": state.get("weapon", "Unarmed Strike"),
                "armor": armor_name,
                "has_shield": state.get("has_shield", False),
                "known_spells": state.get("known_spells", []),
                "is_homebrew_race": state.get("is_homebrew_race", False),
                "spellcasting_ability": state.get("spellcasting_ability"),
                "spell_slots_used": {"standard": {}, "pact": 0},
            }
            char_id = await playerCharactersData.save_character(character_data)
            character_data["id"] = char_id

            embed = build_sheet_embed(
                character_data,
                await get_homebrew_features_for(character_data),
                await get_homebrew_race_traits_for(character_data)
            )
            if use_edit and not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=f"🎉 **{state['name']}** is ready to adventure!", view=None
                )
            else:
                await interaction.followup.send(content=f"🎉 **{state['name']}** is ready to adventure!")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"[ERROR] Exception in _finalize_character: {e}")
            import traceback
            traceback.print_exc()

            err_msg = f"❌ An error occurred while finalizing character: `{e}`"
            if interaction.response.is_done():
                await interaction.followup.send(err_msg, ephemeral=True)
            else:
                await interaction.response.send_message(err_msg, ephemeral=True)

    @app_commands.command(name="deleterace", description="Delete a custom race created for this server")
    async def deleterace(self, interaction: discord.Interaction):
        custom_races_raw = await playerCharactersData.get_custom_races(interaction.guild_id)

        if not custom_races_raw:
            await interaction.response.send_message(
                "❌ No custom races were found for this server.",
                ephemeral=True
            )
            return

        race_names = []
        for race in custom_races_raw:
            if isinstance(race, dict):
                race_names.append(race.get("name"))
            else:
                race_names.append(str(race))

        race_names = [r for r in race_names if r]

        if not race_names:
            await interaction.response.send_message(
                "❌ No valid custom races available to delete.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Select the custom race you want to delete below:",
            view=DeleteRaceView(race_names),
            ephemeral=True
        )        

    

    # ==========================================
    # ADD THE CREATERACE COMMAND HERE:
    # ==========================================

    @app_commands.command(name="createrace", description="Create a custom race for this server")
    async def createrace(self, interaction: discord.Interaction):
        

        async def race_name_submitted(inter: discord.Interaction, race_name: str):
            await self._start_custom_race_flow(inter, race_name, resume_cb=None)
            

        await interaction.response.send_modal(RaceNameModal(lambda inter, race_name: self._start_custom_race_flow(
                inter,
                race_name,
                resume_cb=None)))
        


async def setup(bot):
    await bot.add_cog(CharacterCreation(bot))