from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any

@dataclass
class Modifier:
    """Represents a numeric bonus (e.g., +1 to INT, +10 to speed)."""
    source: str          # e.g., "Variant Human", "Feat: Telepathic"
    target: str          # "ability_score", "skill", "hp", "speed"
    stat: Optional[str]  # "INT", "STR", "Perception", etc.
    value: int           # Numeric amount (+1, +2, etc.)

@dataclass
class RuleChoice:
    """Represents a choice a player must make during creation (flexible ASIs, skill picks, half-feats)."""
    type: str                         # "flexible_asi", "skill_choice", "half_feat"
    count: int = 1                    # Number of selections allowed
    bonus: int = 1                    # Value added per selection
    options: List[str] = field(default_factory=list)  # e.g., ["INT", "WIS", "CHA"] or ["any"]

@dataclass
class Trait:
    """Represents a racial trait or feat description block."""
    name: str
    description: str
    has_stat_bonus: bool = False

@dataclass
class RaceBlueprint:
    """Complete schema for a custom or default race."""
    race_id: str
    name: str
    guild_id: int
    created_by: int
    size: str = "Medium"
    speed: int = 30
    fixed_modifiers: List[Modifier] = field(default_factory=list)
    ability_score_rule: Optional[RuleChoice] = None
    skill_proficiency_rule: Optional[RuleChoice] = None
    traits: List[Trait] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RaceBlueprint":
        fixed_mods = [Modifier(**m) for m in data.get("fixed_modifiers", [])]
        traits = [Trait(**t) for t in data.get("traits", [])]
        
        asi_rule = RuleChoice(**data["ability_score_rule"]) if data.get("ability_score_rule") else None
        skill_rule = RuleChoice(**data["skill_proficiency_rule"]) if data.get("skill_proficiency_rule") else None

        return cls(
            race_id=data["race_id"],
            name=data["name"],
            guild_id=data["guild_id"],
            created_by=data["created_by"],
            size=data.get("size", "Medium"),
            speed=data.get("speed", 30),
            fixed_modifiers=fixed_mods,
            ability_score_rule=asi_rule,
            skill_proficiency_rule=skill_rule,
            traits=traits
        )

@dataclass
class FeatBlueprint:
    """Schema for feats and half-feats."""
    feat_id: str
    name: str
    description: str
    fixed_modifiers: List[Modifier] = field(default_factory=list)
    choice_rule: Optional[RuleChoice] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatBlueprint":
        fixed_mods = [Modifier(**m) for m in data.get("fixed_modifiers", [])]
        choice_rule = RuleChoice(**data["choice_rule"]) if data.get("choice_rule") else None

        return cls(
            feat_id=data["feat_id"],
            name=data["name"],
            description=data["description"],
            fixed_modifiers=fixed_mods,
            choice_rule=choice_rule
        )