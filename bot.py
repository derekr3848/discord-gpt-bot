import os
import discord
from discord.ext import commands
from openai import OpenAI

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot is ready — Logged in as {bot.user}")


@bot.command()
async def ai(ctx, *, message: str):
    """Ask the AI something"""
    await ctx.channel.trigger_typing()

    try:
        response = client_openai.responses.create(
            model="gpt-4o-mini",
            input=message
        )

        reply = response.output_text
        await ctx.reply(reply)

    except Exception as e:
        await ctx.reply(f"Error: {e}")
        print(e)


bot.run(DISCORD_BOT_TOKEN)
