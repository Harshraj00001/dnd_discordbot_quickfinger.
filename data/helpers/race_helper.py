# helpers/race_helper.py or inside reference.py
from data.reference import RACES
import databaseFolder.playerCharactersData as playerCharactersData

async def get_all_guild_races(guild_id: int) -> dict:
    """Returns a merged dictionary of standard SRD races + server custom races."""
    all_races = {}

    # 1. Add standard SRD races
    for race_name, data in RACES.items():
        all_races[race_name] = data

    # 2. Add dynamic custom races from DB
    custom_list = await playerCharactersData.get_custom_races(guild_id)
    for cr in custom_list:
        name = cr["name"] if isinstance(cr, dict) else cr.name
        all_races[name] = {
            "is_custom": True,
            "asi": cr.get("asi", []),
            "speed": cr.get("speed", 30),
            "traits": cr.get("traits", []),
            "created_by": cr.get("created_by")
        }

    return all_races