"""
Persistent storage for characters and homebrew classes, using SQLite.
"""
import json
import aiosqlite

DB_PATH = "dnd_bot.db"


def _parse_json(value, default):
    """Safely parses JSON strings into Python objects."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def parse_character_row(row: dict) -> dict:
    """Ensures JSON-encoded fields are consistently returned as Python data structures."""
    if not row:
        return None
    data = dict(row)
    data["skill_proficiencies"] = _parse_json(data.get("skill_proficiencies"), [])
    data["save_proficiencies"] = _parse_json(data.get("save_proficiencies"), [])
    data["known_spells"] = _parse_json(data.get("known_spells"), [])
    data["spell_slots_used"] = _parse_json(data.get("spell_slots_used"), {"standard": {}, "pact": 0})
    return data


def parse_custom_row(row: dict, list_fields: list) -> dict:
    """Ensures custom class/race JSON fields are consistently decoded."""
    if not row:
        return None
    data = dict(row)
    for field in list_fields:
        data[field] = _parse_json(data.get(field), [])
    return data


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                race TEXT NOT NULL,
                class_name TEXT NOT NULL,
                is_homebrew_class INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                str INTEGER NOT NULL,
                dex INTEGER NOT NULL,
                con INTEGER NOT NULL,
                intl INTEGER NOT NULL,
                wis INTEGER NOT NULL,
                cha INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                current_hp INTEGER NOT NULL,
                ac INTEGER NOT NULL,
                passive_perception INTEGER NOT NULL DEFAULT 10,
                skill_proficiencies TEXT NOT NULL DEFAULT '[]',
                save_proficiencies TEXT NOT NULL DEFAULT '[]',
                weapon TEXT NOT NULL DEFAULT 'Unarmed Strike',
                armor TEXT NOT NULL DEFAULT 'None',
                has_shield INTEGER NOT NULL DEFAULT 0,
                known_spells TEXT NOT NULL DEFAULT '[]',
                is_homebrew_race INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            )
        """)
        # Dynamic schema migrations for existing database files
        for column, definition in [
            ("weapon", "TEXT NOT NULL DEFAULT 'Unarmed Strike'"),
            ("armor", "TEXT NOT NULL DEFAULT 'None'"),
            ("has_shield", "INTEGER NOT NULL DEFAULT 0"),
            ("known_spells", "TEXT NOT NULL DEFAULT '[]'"),
            ("is_homebrew_race", "INTEGER NOT NULL DEFAULT 0"),
            ("passive_perception", "INTEGER NOT NULL DEFAULT 10"),
            ("caster_type", "TEXT"),
            ("spellcasting_ability", "TEXT"),
            ("spell_slots_used", "TEXT NOT NULL DEFAULT '{}'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE characters ADD COLUMN {column} {definition}")
            except Exception:
                pass  # Column already exists

        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                name TEXT NOT NULL,
                hit_die INTEGER NOT NULL,
                saves TEXT NOT NULL,
                skill_choices INTEGER NOT NULL,
                skill_list TEXT NOT NULL,
                is_caster INTEGER NOT NULL DEFAULT 0,
                caster_type TEXT,
                features TEXT NOT NULL DEFAULT '[]',
                UNIQUE(guild_id, name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                name TEXT NOT NULL,
                asi TEXT NOT NULL DEFAULT '[]',
                speed INTEGER NOT NULL DEFAULT 30,
                traits TEXT NOT NULL DEFAULT '[]',
                UNIQUE(guild_id, name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_spells (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                school TEXT NOT NULL DEFAULT 'Custom',
                damage_expr TEXT,
                damage_type TEXT,
                description TEXT NOT NULL DEFAULT '',
                range TEXT NOT NULL DEFAULT '',
                UNIQUE(user_id, guild_id, name)
            )
        """)
        await db.commit()


async def save_character(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO characters
            (user_id, guild_id, name, race, class_name, is_homebrew_class, level,
             str, dex, con, intl, wis, cha, max_hp, current_hp, ac, passive_perception,
             skill_proficiencies, save_proficiencies, weapon, armor, has_shield, known_spells,
             is_homebrew_race, notes, caster_type, spellcasting_ability, spell_slots_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["user_id"], data["guild_id"], data["name"], data["race"],
            data["class_name"], int(data.get("is_homebrew_class", False)), data.get("level", 1),
            data["str"], data["dex"], data["con"], data["intl"], data["wis"], data["cha"],
            data["max_hp"], data["max_hp"], data["ac"], data.get("passive_perception", 10),
            json.dumps(data.get("skill_proficiencies", [])),
            json.dumps(data.get("save_proficiencies", [])),
            data.get("weapon", "Unarmed Strike"), data.get("armor", "None"),
            int(data.get("has_shield", False)), json.dumps(data.get("known_spells", [])),
            int(data.get("is_homebrew_race", False)), data.get("notes", ""),
            data.get("caster_type"), data.get("spellcasting_ability"),
            json.dumps(data.get("spell_slots_used", {"standard": {}, "pact": 0}))
        ))
        await db.commit()
        return cursor.lastrowid


async def get_characters_for_user(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM characters WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        rows = await cursor.fetchall()
        return [parse_character_row(dict(r)) for r in rows]


async def get_character_by_name(user_id: int, guild_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM characters WHERE user_id = ? AND guild_id = ? AND LOWER(name) = LOWER(?)",
            (user_id, guild_id, name)
        )
        row = await cursor.fetchone()
        return parse_character_row(dict(row)) if row else None


async def update_hp(character_id: int, current_hp: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE characters SET current_hp = ? WHERE id = ?", (current_hp, character_id))
        await db.commit()


async def update_character_level_and_hp(character_id: int, new_level: int, new_max_hp: int, new_current_hp: int):
    """Updates a character's level, max HP, and current HP in SQLite."""
    async with aiosqlite.connect(DB_PATH) as db:  # Fixed hardcoded string to DB_PATH
        await db.execute(
            """
            UPDATE characters 
            SET level = ?, max_hp = ?, current_hp = ?
            WHERE id = ?
            """,
            (new_level, new_max_hp, new_current_hp, character_id)
        )
        await db.commit()


async def update_character(data: dict) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE characters SET
                name = ?, level = ?, str = ?, dex = ?, con = ?, intl = ?, wis = ?, cha = ?,
                max_hp = ?, current_hp = ?, ac = ?, passive_perception = ?, weapon = ?, armor = ?, has_shield = ?,
                known_spells = ?, skill_proficiencies = ?, save_proficiencies = ?,
                caster_type = ?, spellcasting_ability = ?, spell_slots_used = ?
            WHERE id = ? AND user_id = ?
        """, (
            data["name"], data["level"], data["str"], data["dex"], data["con"],
            data["intl"], data["wis"], data["cha"], data["max_hp"],
            min(data["current_hp"], data["max_hp"]), data["ac"], data.get("passive_perception", 10),
            data["weapon"], data["armor"], int(data["has_shield"]),
            json.dumps(data.get("known_spells", [])),
            json.dumps(data.get("skill_proficiencies", [])),
            json.dumps(data.get("save_proficiencies", [])),
            data.get("caster_type"), data.get("spellcasting_ability"),
            json.dumps(data.get("spell_slots_used", {"standard": {}, "pact": 0})),
            data["id"], data["user_id"]
        ))
        await db.commit()
        return cursor.rowcount > 0


async def delete_character(character_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM characters WHERE id = ? AND user_id = ?", (character_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def save_custom_class(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO custom_classes
            (guild_id, created_by, name, hit_die, saves, skill_choices, skill_list,
             is_caster, caster_type, features)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["guild_id"], data["created_by"], data["name"], data["hit_die"],
            json.dumps(data["saves"]), data["skill_choices"], json.dumps(data["skill_list"]),
            int(data.get("is_caster", False)), data.get("caster_type"),
            json.dumps(data.get("features", []))
        ))
        await db.commit()
        return cursor.lastrowid


async def get_custom_classes(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM custom_classes WHERE guild_id = ?", (guild_id,))
        rows = await cursor.fetchall()
        return [parse_custom_row(dict(r), ["saves", "skill_list", "features"]) for r in rows]


async def get_custom_class_by_name(guild_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM custom_classes WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, name)
        )
        row = await cursor.fetchone()
        return parse_custom_row(dict(row), ["saves", "skill_list", "features"]) if row else None


async def save_custom_race(data: dict) -> int:
    """Saves or updates a custom race in the database safely."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT OR REPLACE INTO custom_races (guild_id, created_by, name, asi, speed, traits)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get("guild_id", 0) or 0,
            data.get("created_by", 0) or 0,
            data.get("name", "Unnamed Race"),
            json.dumps(data.get("asi", [])),
            data.get("speed", 30),
            json.dumps(data.get("traits", []))
        ))
        await db.commit()
        return cursor.lastrowid


async def get_custom_races(guild_id: int):
    """Fetches custom races for this guild OR global server races (guild_id = 0)."""
    target_id = guild_id or 0
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM custom_races WHERE guild_id = ? OR guild_id = 0",
            (target_id,)
        )
        rows = await cursor.fetchall()
        return [parse_custom_row(dict(r), ["asi", "traits"]) for r in rows]


async def get_custom_race_by_name(guild_id: int, name: str):
    target_id = guild_id or 0
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM custom_races WHERE (guild_id = ? OR guild_id = 0) AND LOWER(name) = LOWER(?)",
            (target_id, name)
        )
        row = await cursor.fetchone()
        return parse_custom_row(dict(row), ["asi", "traits"]) if row else None


async def delete_custom_race(guild_id: int, race_name: str):
    """Deletes a custom race from the database for a specific guild (or global)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM custom_races WHERE (guild_id = ? OR guild_id = 0) AND LOWER(name) = LOWER(?)",
            (guild_id, race_name)
        )
        await db.commit()

# --- Custom spell operations ---

async def save_custom_spell(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT OR REPLACE INTO custom_spells
            (user_id, guild_id, name, level, school, damage_expr, damage_type, description, range)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["user_id"], data["guild_id"], data["name"],
            int(data.get("level", 0)), data.get("school", "Custom"),
            data.get("damage_expr"), data.get("damage_type"),
            data.get("description", ""), data.get("range", "")
        ))
        await db.commit()
        return cursor.lastrowid


async def get_custom_spell_by_name(user_id: int, guild_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM custom_spells WHERE user_id = ? AND guild_id = ? AND LOWER(name) = LOWER(?)",
            (user_id, guild_id, name)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_custom_spells_for_user(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM custom_spells WHERE user_id = ? AND guild_id = ? ORDER BY level, name COLLATE NOCASE",
            (user_id, guild_id)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_custom_spell(user_id: int, guild_id: int, name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM custom_spells WHERE user_id = ? AND guild_id = ? AND LOWER(name) = LOWER(?)",
            (user_id, guild_id, name)
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_spell_to_character(character_id: int, user_id: int, spell_name: str) -> bool:
    """Appends a spell name to a character's known_spells list (no dupes)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM characters WHERE id = ? AND user_id = ?",
            (character_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        char = parse_character_row(dict(row))

        known = char.get("known_spells", [])
        if any(s.lower() == spell_name.lower() for s in known):
            return False

        known.append(spell_name)
        await db.execute(
            "UPDATE characters SET known_spells = ? WHERE id = ? AND user_id = ?",
            (json.dumps(known), character_id, user_id)
        )
        await db.commit()
        return True        