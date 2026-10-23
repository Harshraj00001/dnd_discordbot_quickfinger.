import discord
from character_creation.constants import ABILITIES

#-------------------------- ASI TEMPLATE VIEW-------------------------

class AsiTemplateView(discord.ui.View):
    """View to select the Ability Score Increase template for a custom race."""
    def __init__(self, callback):
        super().__init__(timeout=60)
        self.callback = callback

    @discord.ui.button(label="+2 / +1 (Standard)", style=discord.ButtonStyle.primary, emoji="⚖️")
    async def option_standard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "standard")

    @discord.ui.button(label="+1 / +1 / +1 (Triton / Tasha's)", style=discord.ButtonStyle.secondary, emoji="🔱")
    async def option_triple(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "triple")

    @discord.ui.button(label="+2 / +1 / -2 (Tradeoff)", style=discord.ButtonStyle.secondary, emoji="⚖️")
    async def option_tradeoff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "tradeoff")   

    @discord.ui.button(label="+2 / +2 (Mountain Dwarf)", style=discord.ButtonStyle.secondary, emoji="⛏️")
    async def option_dual_heavy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "dual_heavy")

    @discord.ui.button(label="+2 / +1 / +1 (Half-Elf)", style=discord.ButtonStyle.secondary, emoji="🧝")
    async def option_half_elf(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "half_elf")

    @discord.ui.button(label="Custom / Human +1 All", style=discord.ButtonStyle.danger, emoji="✍️")
    async def option_custom(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "custom")

    @discord.ui.button(label="+1 / +1 (Dual Light)", style=discord.ButtonStyle.secondary, emoji="✌️")
    async def option_dual_light(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "dual_light")

    @discord.ui.button(label="+2 (Single Stat)", style=discord.ButtonStyle.secondary, emoji="🎯")
    async def option_single_heavy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "single_heavy")

    @discord.ui.button(label="+1 (Single Light)", style=discord.ButtonStyle.secondary, emoji="🌱")
    async def option_single_light(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback(interaction, "single_light") 

#---------------- ABILITY SELECT-----------------------------------------------
class AbilitySelect(discord.ui.Select):
    def __init__(self, callback, options_list: list, min_values: int = 1, max_values: int = 1, placeholder: str = "Select an ability..."):
        select_options = [
            discord.SelectOption(label=stat, value=stat)
            for stat in options_list
        ]
        super().__init__(
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=select_options
        )
        self.custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self.custom_callback(interaction, self.values)

#----------------------ABILITY SELECT VIEW-------------------------------------
class AbilitySelectView(discord.ui.View):
    def __init__(self, callback, options_list: list = ABILITIES, min_values: int = 1, max_values: int = 1, placeholder: str = "Select an ability..."):
        super().__init__(timeout=60)
        self.add_item(AbilitySelect(callback, options_list, min_values, max_values, placeholder))               