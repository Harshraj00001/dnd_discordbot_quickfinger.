"""
Main entry point. Run with: python bot.py
"""
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord import app_commands
import traceback

import databaseFolder.playerCharactersData as playerCharactersData
from character_engine import RuleDatabase  # 1. Added import here

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        # Global sync (can take up to an hour to propagate everywhere across Discord)
        synced = await bot.tree.sync()
        print(f"Globally synced {len(synced)} slash command(s).")

        # Guild sync (instant update in every server the bot is currently in)
        for guild in bot.guilds:
            guild_synced = await bot.tree.sync(guild=guild)
            print(f"⚡ Instantly synced {len(guild_synced)} command(s) to server '{guild.name}'.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("\n=== APP COMMAND ERROR ===")
    print(f"Command: {interaction.command.name if interaction.command else 'Unknown'}")
    print(f"Error type: {type(error).__name__}")
    if isinstance(error, app_commands.CommandInvokeError):
        print(f"Original: {type(error.original).__name__}: {error.original}")
        traceback.print_exception(type(error.original), error.original, error.original.__traceback__)
    else:
        traceback.print_exception(type(error), error, error.__traceback__)
    print("=== END ===\n")

@bot.tree.command(name="ping", description="Check if the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! I'm alive and ready to roll some dice.")

@bot.command()
@commands.is_owner() # Only you can run this
async def sync(ctx):
    # Syncs commands instantly to the current server
    fmt = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ Synced {len(fmt)} command(s) to this server!")

async def main():
    await playerCharactersData.init_db()
    RuleDatabase.init_db()  # 2. Added DB initialization here
    print("✅ Rulesets database initialized.")

    await bot.load_extension("character_creation.creator")
    await bot.load_extension("cogs.character_management")
    await bot.load_extension("cogs.dice")
    await bot.load_extension("cogs.spells")
    await bot.load_extension("cogs.ruleset_commands")
    await bot.load_extension("cogs.rest")
    await bot.load_extension("cogs.custom_spells")

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("No DISCORD_BOT_TOKEN found. Set it as an environment variable.")
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())