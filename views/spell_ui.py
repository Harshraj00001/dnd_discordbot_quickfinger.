"""
Spell-related UI components: the known-spells entry modal (used during
character creation / editing) and the custom-spell definition modal.
"""
import re
import discord


class SpellsModal(discord.ui.Modal, title="What spells do you know?"):
    spells_text = discord.ui.TextInput(
        label="Spells (comma or one per line)",
        style=discord.TextStyle.paragraph,
        placeholder="Fire Bolt, Mage Armor, Magic Missile",
        max_length=500,
        required=False,
    )

    def __init__(self, on_submit_callback):
        super().__init__()
        self.on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.spells_text)
        spells = [s.strip() for s in re.split(r"[,\n]", raw) if s.strip()]
        await self.on_submit_callback(interaction, spells)


class CustomSpellModal(discord.ui.Modal, title="Create a custom spell"):
    def __init__(self, on_submit_callback, existing: dict = None):
        super().__init__()
        self.on_submit_callback = on_submit_callback
        e = existing or {}

        self.name_input = discord.ui.TextInput(
            label="Spell name",
            max_length=60,
            default=str(e.get("name", "")),
            placeholder="e.g. Hex",
        )
        self.level_input = discord.ui.TextInput(
            label="Level (0 for cantrip, 1-9 for leveled)",
            max_length=1,
            default=str(e.get("level", 0)),
        )
        self.damage_input = discord.ui.TextInput(
            label="Damage dice (e.g. 1d6+2, blank for utility)",
            max_length=60,
            required=False,
            default=str(e.get("damage_expr") or ""),
            placeholder="1d6",
        )
        self.damage_type_input = discord.ui.TextInput(
            label="Damage type (e.g. necrotic, fire)",
            max_length=30,
            required=False,
            default=str(e.get("damage_type") or ""),
            placeholder="necrotic",
        )
        self.details_input = discord.ui.TextInput(
            label="Range and description",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False,
            default=self._format_details(e),
            placeholder="Range: 90 ft\nBonus action; target takes +1d6 necrotic when hit.",
        )

        self.add_item(self.name_input)
        self.add_item(self.level_input)
        self.add_item(self.damage_input)
        self.add_item(self.damage_type_input)
        self.add_item(self.details_input)

    @staticmethod
    def _format_details(e: dict) -> str:
        rng = e.get("range", "") or ""
        desc = e.get("description", "") or ""
        if rng and desc:
            return f"Range: {rng}\n{desc}"
        if rng:
            return f"Range: {rng}"
        return desc

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(str(self.level_input).strip())
        except ValueError:
            level = -1
        if level < 0 or level > 9:
            await interaction.response.send_message(
                "⚠️ Level must be a whole number from 0 to 9.", ephemeral=True
            )
            return

        raw_details = str(self.details_input).strip()
        range_val = ""
        desc_val = raw_details
        if raw_details.lower().startswith("range:"):
            first_line, _, rest = raw_details.partition("\n")
            range_val = first_line.split(":", 1)[1].strip()
            desc_val = rest.strip()

        data = {
            "name": str(self.name_input).strip(),
            "level": level,
            "damage_expr": str(self.damage_input).strip() or None,
            "damage_type": str(self.damage_type_input).strip() or None,
            "range": range_val,
            "description": desc_val,
        }
        if not data["name"]:
            await interaction.response.send_message(
                "⚠️ The spell needs a name.", ephemeral=True
            )
            return
        await self.on_submit_callback(interaction, data)