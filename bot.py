import os
import discord
from discord.ext import commands
from openai import OpenAI

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot is ready — Logged in as {bot.user}")

# ---------------------------
#     !ask COMMAND
# ---------------------------
@bot.command()
async def ask(ctx, *, query: str):
    """Ask the AI something using:  !ask <your question>"""

    await ctx.channel.trigger_typing()

    # Call OpenAI Responses API (works in November 2025)
    response = client_openai.responses.create(
        model="gpt-4.1-mini",
        input=query,
    )

    ai_reply = response.output_text

    await ctx.reply(ai_reply)

# ---------------------------
bot.run(DISCORD_TOKEN)
