"""
Spell slot math and state for characters.

This is the ONLY module that knows how a character's caster composition maps
to spell slots. When multiclassing is added, `caster_profile()` is the single
function that changes; everything downstream keeps its shape.
"""
import json
from data.reference import (
    CLASSES, FULL_CASTER_SLOTS, HALF_CASTER_SLOTS, PACT_CASTER_SLOTS
)


# ---------------------------------------------------------------------------
# Caster composition
# ---------------------------------------------------------------------------

def caster_profile(character: dict) -> dict:
    """
    Returns how many levels this character has in each caster category.

    Single-class today:
        {"full": N, "half": 0, "pact": 0, "none": bool}

    Multiclass later: same shape, summed across all classes in the list.
    Only this function will need to change when multiclassing lands.
    """
    profile = {"full": 0, "half": 0, "pact": 0, "none": False}

    # Homebrew classes: caster_type is stored directly on the character.
    if character.get("is_homebrew_class"):
        caster_type = character.get("caster_type")
        if caster_type in ("full", "half", "pact"):
            profile[caster_type] = character["level"]
        else:
            profile["none"] = True
        return profile

    # Standard classes: look up the class table.
    class_data = CLASSES.get(character["class_name"], {})
    caster_type = class_data.get("caster")
    if caster_type in ("full", "half", "pact"):
        profile[caster_type] = character["level"]
    else:
        profile["none"] = True
    return profile


def is_caster(character: dict) -> bool:
    """True if the character has any spellcasting capability."""
    p = caster_profile(character)
    return bool(p["full"] or p["half"] or p["pact"])


def combined_caster_level(profile: dict) -> int:
    """
    Standard 5e multiclassing rule: full casters count fully, half casters
    count half (rounded down). Pact Magic is tracked separately.
    """
    return profile["full"] + (profile["half"] // 2)


# ---------------------------------------------------------------------------
# Max slots (derived, never stored)
# ---------------------------------------------------------------------------

def max_slots(character: dict) -> dict:
    """
    Returns the character's slot maximums.

    Shape:
        {
            "standard": {"1": 4, "2": 3, "3": 2},   # keys are str spell levels
            "pact": (count, slot_level) or None     # Warlock-style Pact Magic
        }

    "standard" is present for full/half casters (even if empty at level 1).
    "pact" is present only for pact casters.
    """
    profile = caster_profile(character)
    result = {"standard": {}, "pact": None}

    if profile["none"]:
        return result

    # Standard slot track (full + half combined).
    combined = combined_caster_level(profile)
    if combined > 0:
        table = FULL_CASTER_SLOTS
        slots_list = table.get(combined, [])
        for i, count in enumerate(slots_list, start=1):
            if count:
                result["standard"][str(i)] = count
    elif profile["half"] > 0:
        # Half caster below the multiclass threshold still uses its own table.
        table = HALF_CASTER_SLOTS
        slots_list = table.get(profile["half"], [])
        for i, count in enumerate(slots_list, start=1):
            if count:
                result["standard"][str(i)] = count

    # Pact slot track.
    if profile["pact"] > 0:
        count, slot_level = PACT_CASTER_SLOTS.get(profile["pact"], (0, 0))
        if count:
            result["pact"] = (count, slot_level)

    return result


# ---------------------------------------------------------------------------
# Used slots (stored on the character)
# ---------------------------------------------------------------------------

def used_slots(character: dict) -> dict:
    """
    Reads character["spell_slots_used"] and returns it as a clean dict.

    Shape:
        {
            "standard": {"1": 2, "2": 1},   # spent standard slots
            "pact": 1                        # spent pact slots (int, 0 or 1+)
        }
    """
    raw = character.get("spell_slots_used")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    standard = raw.get("standard") or {}
    if not isinstance(standard, dict):
        standard = {}
    # Ensure keys are strings, values are ints.
    standard = {str(k): int(v) for k, v in standard.items() if int(v) > 0}

    pact = int(raw.get("pact", 0) or 0)

    return {"standard": standard, "pact": pact}


def available_slots(character: dict) -> dict:
    """
    max - used, clamped to >= 0. Same shape as max_slots, with the used
    counts subtracted out.
    """
    mx = max_slots(character)
    us = used_slots(character)

    avail_standard = {}
    for lvl_str, max_count in mx["standard"].items():
        used = us["standard"].get(lvl_str, 0)
        remaining = max(0, max_count - used)
        if remaining > 0:
            avail_standard[lvl_str] = remaining

    avail_pact = None
    if mx["pact"] is not None:
        pact_max, pact_level = mx["pact"]
        remaining = max(0, pact_max - us["pact"])
        if remaining > 0:
            avail_pact = (remaining, pact_level)

    return {"standard": avail_standard, "pact": avail_pact}


# ---------------------------------------------------------------------------
# Casting
# ---------------------------------------------------------------------------

def max_available_slot_level(character: dict) -> int:
    """
    Returns the highest slot level this character can currently cast with.
    For pact casters, returns their pact slot level (if any remain).
    Returns 0 if no slots are available.
    """
    avail = available_slots(character)
    levels = [int(k) for k in avail["standard"].keys()]
    if avail["pact"] is not None:
        levels.append(avail["pact"][1])
    return max(levels) if levels else 0


def can_cast_at_level(character: dict, spell_level: int) -> bool:
    """True if the character has at least one slot at this spell level."""
    if spell_level == 0:
        return True  # Cantrips always available.
    avail = available_slots(character)
    if avail["standard"].get(str(spell_level), 0) > 0:
        return True
    if avail["pact"] is not None and avail["pact"][1] == spell_level:
        return True
    return False


def consume_slot(character: dict, spell_level: int) -> bool:
    """
    Increments the used count for this spell level. Mutates
    character["spell_slots_used"] in place. Returns True on success,
    False if no slot is available.
    """
    if spell_level == 0:
        return True  # Cantrips don't consume slots.

    us = used_slots(character)

    # Try standard first.
    mx = max_slots(character)
    if str(spell_level) in mx["standard"]:
        max_at_level = mx["standard"][str(spell_level)]
        current = us["standard"].get(str(spell_level), 0)
        if current < max_at_level:
            us["standard"][str(spell_level)] = current + 1
            character["spell_slots_used"] = us
            return True
        # Slot level exists but is exhausted — try pact as fallback.
        if mx["pact"] is not None:
            pact_max, pact_level = mx["pact"]
            if pact_level == spell_level and us["pact"] < pact_max:
                us["pact"] += 1
                character["spell_slots_used"] = us
                return True
        return False

    # Pact slot at this level.
    if mx["pact"] is not None:
        pact_max, pact_level = mx["pact"]
        if pact_level == spell_level and us["pact"] < pact_max:
            us["pact"] += 1
            character["spell_slots_used"] = us
            return True

    return False


# ---------------------------------------------------------------------------
# Resting
# ---------------------------------------------------------------------------

def reset_slots(character: dict, rest_type: str) -> None:
    """
    Mutates character["spell_slots_used"].

    rest_type == "long"  → clears everything.
    rest_type == "short" → clears pact slots only (Warlock Pact Magic).
    """
    us = used_slots(character)
    if rest_type == "long":
        character["spell_slots_used"] = {"standard": {}, "pact": 0}
    elif rest_type == "short":
        us["pact"] = 0
        character["spell_slots_used"] = us
    else:
        raise ValueError(f"Unknown rest type: {rest_type}")


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------

def format_slots_for_sheet(character: dict) -> str:
    """
    Returns a human-readable slots line, e.g.:
        "L1: 2/4  L2: 3/3  L3: 1/2"
        "Pact (L3): 1/2"
        "None yet"
    """
    mx = max_slots(character)
    us = used_slots(character)

    parts = []
    for lvl_str in sorted(mx["standard"].keys(), key=int):
        max_count = mx["standard"][lvl_str]
        used = us["standard"].get(lvl_str, 0)
        remaining = max(0, max_count - used)
        parts.append(f"L{lvl_str}: {remaining}/{max_count}")

    if mx["pact"] is not None:
        pact_max, pact_level = mx["pact"]
        pact_remaining = max(0, pact_max - us["pact"])
        parts.append(f"Pact (L{pact_level}): {pact_remaining}/{pact_max}")

    return "  ".join(parts) if parts else "None yet"