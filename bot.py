import os
import discord
from discord.ext import commands
from openai import OpenAI

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")   # must match Railway variable
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("asst_Fc3yRPdXjHUBlXNswxQ4q1TM")  # your assistant ID

if OPENAI_KEY is None:
    raise ValueError("OPENAI_API_KEY is missing!")
if DISCORD_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN is missing!")
if ASSISTANT_ID is None:
    raise ValueError("ASSISTANT_ID is missing!")

# -----------------------------
# OPENAI CLIENT
# -----------------------------
client_openai = OpenAI(api_key=OPENAI_KEY)

# -----------------------------
# DISCORD BOT SETUP
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Stores:
# user_id : { "discord_thread": thread_id, "openai_thread": thread_id }
user_threads = {}

# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"🤖 Bot ready — logged in as {bot.user}")
    print("Loaded user memory:", len(user_threads))


# -----------------------------
# START COMMAND
# -----------------------------
@bot.command()
async def start(ctx):
    """Creates a private AI conversation thread for the user."""

    user_id = ctx.author.id

    # If user already has a thread
    if user_id in user_threads:
        await ctx.reply("You already have an AI chat thread!")
        return

    # Create Discord private thread
    thread = await ctx.channel.create_thread(
        name=f"{ctx.author.name}-ai-chat",
        type=discord.ChannelType.private_thread
    )

    # Create OpenAI assistant thread for this user
    ai_thread = client_openai.beta.threads.create()

    # Save memory
    user_threads[user_id] = {
        "discord_thread": thread.id,
        "openai_thread": ai_thread.id
    }

    await thread.send(
        f"👋 Hello {ctx.author.mention}! This is your personal AI chat. "
        "Ask me anything — no commands needed inside this thread."
    )


# -----------------------------
# MESSAGE HANDLER
# -----------------------------
@bot.event
async def on_message(message):
    """Handles user chat inside their private AI thread."""

    # Ignore bot messages
    if message.author.bot:
        return

    user_id = message.author.id

    # Check if message is in the user's assigned private thread
    if user_id in user_threads:
        thread_info = user_threads[user_id]

        if message.channel.id == thread_info["discord_thread"]:
            # User sent message inside their AI thread
            ai_thread_id = thread_info["openai_thread"]

            # Send user message to OpenAI
            client_openai.beta.threads.messages.create(
                thread_id=ai_thread_id,
                role="user",
                content=message.content
            )

            # Run the assistant
            run = client_openai.beta.threads.runs.create_and_poll(
                thread_id=ai_thread_id,
                assistant_id=ASSISTANT_ID
            )

            # Get assistant response
            messages = client_openai.beta.threads.messages.list(
                thread_id=ai_thread_id
            )
            reply = messages.data[0].content[0].text.value

            # Discord replies must be under 2000 characters
            if len(reply) > 1990:
                reply = reply[:1990] + "..."

            await message.channel.send(reply)

    # VERY IMPORTANT — lets commands still work
    await bot.process_commands(message)


# -----------------------------
# RUN THE BOT
# -----------------------------
bot.run(DISCORD_TOKEN)
