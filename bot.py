import os
import discord
from discord.ext import commands
from openai import OpenAI

# Load secrets from Railway (DO NOT hardcode)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Your Assistant ID (SAFE to put here)
ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

# Initialize OpenAI client
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------------------------------------------
# Create a *single reusable thread* for ALL conversations
# (If you want per-user memory, I can upgrade it later)
# -------------------------------------------------------------------

thread = client_openai.beta.threads.create()

# -------------------------------------------------------------------
# BOT EVENTS
# -------------------------------------------------------------------

@bot.event
async def on_ready():
    print(f"Bot is ready — Logged in as {bot.user}")

# -------------------------------------------------------------------
# /ask Command (User triggers AI reply)
# -------------------------------------------------------------------

@bot.command()
async def ask(ctx, *, message: str):
    """Ask your custom OpenAI assistant."""
    
    # Send user message to the assistant thread
    client_openai.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=message
    )

    # Run the assistant on that thread
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID
    )

    # Extract assistant's reply
    reply = ""
    for msg in client_openai.beta.threads.messages.list(thread_id=thread.id).data:
        if msg.role == "assistant":
            reply = msg.content[0].text.value
            break

    if reply:
        await ctx.send(reply)
    else:
        await ctx.send("No response received from the assistant.")

# -------------------------------------------------------------------

bot.run(DISCORD_BOT_TOKEN)
