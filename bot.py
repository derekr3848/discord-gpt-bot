import os
import discord
from discord.ext import commands
from openai import OpenAI

# -------------------------------
# ENV VARIABLES
# -------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# Your Assistant ID from platform.openai.com/assistants
ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"   # <-- PUT YOUR ASSISTANT ID HERE

# -------------------------------
# SETUP CLIENTS
# -------------------------------
client_openai = OpenAI(api_key=OPENAI_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# -------------------------------
# BOT READY EVENT
# -------------------------------
@bot.event
async def on_ready():
    print(f"Bot is ready — Logged in as {bot.user}")

# -------------------------------
# ASK COMMAND
# -------------------------------
@bot.command(name="ask")
async def ask(ctx, *, prompt: str):
    """Ask your OpenAI Assistant a question."""
    await ctx.channel.typing()

    try:
        # 1. Create a new assistant thread
        thread = client_openai.beta.threads.create()

        # 2. Add user message
        client_openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt
        )

        # 3. Run the assistant
        run = client_open_
