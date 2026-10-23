import sqlite3
import json
import os
from typing import List, Optional
from .models import RaceBlueprint, FeatBlueprint, RuleChoice, Modifier

DB_PATH = os.path.join(os.path.dirname(__file__), "rulesets.db")

class RuleDatabase:
    
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def init_db(cls):
        """Initializes tables and seeds default 5e feats/races."""
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_races (
                    race_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feats (
                    feat_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.commit()
            
        cls._seed_default_feats()

    @classmethod
    def _seed_default_feats(cls):
        """Pre-loads common feats like Telepathic into rulesets.db if empty."""
        default_feats = [
            FeatBlueprint(
                feat_id="telepathic",
                name="Telepathic",
                description="Gain 60ft telepathy and +1 to a mental ability score.",
                choice_rule=RuleChoice(
                    type="half_feat",
                    count=1,
                    bonus=1,
                    options=["INT", "WIS", "CHA"]
                )
            ),
            FeatBlueprint(
                feat_id="tough",
                name="Tough",
                description="Your HP maximum increases by an amount equal to 2x your level.",
                fixed_modifiers=[
                    Modifier(source="Feat: Tough", target="hp_per_level", stat=None, value=2)
                ]
            )
        ]
        
        for feat in default_feats:
            if not cls.get_feat(feat.feat_id):
                cls.save_feat(feat)

    # --- Race Operations ---

    

    @classmethod
    def get_race(cls, race_id: str) -> Optional[RaceBlueprint]:
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM custom_races WHERE race_id = ?", (race_id,))
            row = cursor.fetchone()
            if row:
                return RaceBlueprint.from_dict(json.loads(row["data_json"]))
        return None

    

    # --- Feat Operations ---

    @classmethod
    def save_feat(cls, feat: FeatBlueprint):
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO feats (feat_id, name, data_json)
                VALUES (?, ?, ?)
            """, (feat.feat_id, feat.name, json.dumps(feat.to_dict())))
            conn.commit()

    @classmethod
    def get_feat(cls, feat_id: str) -> Optional[FeatBlueprint]:
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM feats WHERE feat_id = ?", (feat_id,))
            row = cursor.fetchone()
            if row:
                return FeatBlueprint.from_dict(json.loads(row["data_json"]))
        return None

    @classmethod
    def get_all_feats(cls) -> List[FeatBlueprint]:
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM feats")
            rows = cursor.fetchall()
            return [FeatBlueprint.from_dict(json.loads(r["data_json"])) for r in rows]