import os
import discord
from discord.ext import commands
from openai import OpenAI

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # REQUIRED for reading messages

bot = commands.Bot(command_prefix="!", intents=intents)


# ------------------------------
# Bot Ready
# ------------------------------
@bot.event
async def on_ready():
    print(f"Bot is ready — Logged in as {bot.user}")


# ------------------------------
# !ask command
# ------------------------------
@bot.command()
async def ask(ctx, *, prompt: str):
    """Ask the AI a question."""
    
    # Show typing indicator
    async with ctx.channel.typing():
        try:
            # Call OpenAI Responses API
            response = client_openai.responses.create(
                model="gpt-4.1-mini",
                input=prompt
            )

            answer = response.output_text

        except Exception as e:
            answer = f"Error: {e}"

    # Reply to the user
    await ctx.reply(answer)


# ------------------------------
# Run bot
# ------------------------------
bot.run(DISCORD_BOT_TOKEN)
