from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .models import RaceBlueprint, Modifier, Trait

@dataclass
class ComputedStats:
    """Holds all calculated character attributes after processing modifiers."""
    final_scores: Dict[str, int]
    ability_modifiers: Dict[str, int]
    speed: int
    max_hp: int
    passive_perception: int
    proficiency_bonus: int
    trained_skills: List[str]
    modifier_breakdown: Dict[str, List[str]]
    active_traits: List[Trait]

class StatCalculator:

    @staticmethod
    def get_ability_modifier(score: int) -> int:
        """Standard 5e modifier calculation: (Score - 10) // 2."""
        return (score - 10) // 2

    @staticmethod
    def get_proficiency_bonus(level: int) -> int:
        """Standard 5e proficiency scaling by level."""
        return 2 + ((level - 1) // 4)

    @classmethod
    def compute(
        cls,
        base_scores: Dict[str, int],
        race: Optional[RaceBlueprint] = None,
        applied_modifiers: Optional[List[Modifier]] = None,
        level: int = 1,
        hit_die: int = 8,
        class_skills: Optional[List[str]] = None,
        additional_skills: Optional[List[str]] = None
    ) -> ComputedStats:
        """
        Stacks base scores and modifiers to calculate final statistics.
        """
        final_scores = {stat: val for stat, val in base_scores.items()}
        breakdown = {stat: [f"Base: {val}"] for stat, val in base_scores.items()}
        
        all_modifiers: List[Modifier] = []
        
        # 1. Collect fixed racial modifiers
        if race and race.fixed_modifiers:
            all_modifiers.extend(race.fixed_modifiers)
        
        # 2. Collect dynamic user-selected modifiers (flexible ASIs, half-feats, etc.)
        if applied_modifiers:
            all_modifiers.extend(applied_modifiers)
            
        # 3. Apply ability score & utility modifiers
        hp_bonus_per_level = 0
        extra_speed = 0
        
        for mod in all_modifiers:
            if mod.target == "ability_score" and mod.stat in final_scores:
                final_scores[mod.stat] += mod.value
                sign = "+" if mod.value >= 0 else ""
                breakdown[mod.stat].append(f"{mod.source}: {sign}{mod.value}")
            elif mod.target == "hp_per_level":
                hp_bonus_per_level += mod.value
            elif mod.target == "speed":
                extra_speed += mod.value

        # 4. Compute ability modifiers
        modifiers = {
            stat: cls.get_ability_modifier(score) 
            for stat, score in final_scores.items()
        }

        # 5. Calculate Speed
        base_speed = race.speed if race else 30
        total_speed = base_speed + extra_speed

        # 6. Calculate Proficiency Bonus & Max HP
        prof_bonus = cls.get_proficiency_bonus(level)
        con_mod = modifiers.get("CON", 0)

        if level == 1:
            max_hp = hit_die + con_mod + hp_bonus_per_level
        else:
            avg_hit_die_increase = (hit_die // 2) + 1
            max_hp = (hit_die + con_mod + hp_bonus_per_level) + (
                (avg_hit_die_increase + con_mod + hp_bonus_per_level) * (level - 1)
            )
        max_hp = max(1, max_hp)

        # 7. Merge and deduplicate skills
        trained_skills = list(set((class_skills or []) + (additional_skills or [])))

        # 8. Compute Passive Perception
        wis_mod = modifiers.get("WIS", 0)
        passive_perc = 10 + wis_mod
        if "Perception" in trained_skills:
            passive_perc += prof_bonus

        # 9. Traits list
        traits = race.traits if race else []

        return ComputedStats(
            final_scores=final_scores,
            ability_modifiers=modifiers,
            speed=total_speed,
            max_hp=max_hp,
            passive_perception=passive_perc,
            proficiency_bonus=prof_bonus,
            trained_skills=trained_skills,
            modifier_breakdown=breakdown,
            active_traits=traits
        )