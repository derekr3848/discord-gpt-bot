import os
import discord
from discord.ext import commands
from openai import OpenAI

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

client_openai = OpenAI(api_key=OPENAI_KEY)

# Memory: user_id → openai_thread_id
user_threads = {}
# Discord thread: user_id → discord_thread_channel_id
discord_threads = {}

@bot.event
async def on_ready():
    print(f"Bot ready — Logged in as {bot.user}")

############################################################
# COMMAND: !start — Creates user’s dedicated private thread
############################################################
@bot.command()
async def start(ctx):
    user = ctx.author

    # Prevent DM use
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("Use this command in a server channel.")
        return

    # Already has a thread
    if user.id in discord_threads:
        existing_thread_id = discord_threads[user.id]
        existing_thread = ctx.guild.get_channel(existing_thread_id)

        if existing_thread:
            await ctx.send(f"{user.mention} you already have an AI thread: {existing_thread.mention}")
            return

    #########################################
    # 1. CREATE DISCORD PRIVATE THREAD
    #########################################
    ai_thread = await ctx.channel.create_thread(
        name=f"{user.name}-ai-thread",
        type=discord.ChannelType.private_thread
    )

    discord_threads[user.id] = ai_thread.id
    await ai_thread.send(f"👋 {user.mention}, this is your **personal AI chat**.\nJust talk — no commands needed.")

    #########################################
    # 2. CREATE OPENAI MEMORY THREAD
    #########################################
    thread_obj = client_openai.beta.threads.create()
    user_threads[user.id] = thread_obj.id

    await ctx.send(f"Your personal AI thread is ready → {ai_thread.mention}")

###########################################################
# AUTO-REPLY: Inside user’s thread ONLY
###########################################################
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user = message.author

    # Only respond inside AI thread
    if user.id not in discord_threads:
        await bot.process_commands(message)
        return

    thread_id = discord_threads[user.id]

    # Not in user's thread → ignore
    if message.channel.id != thread_id:
        await bot.process_commands(message)
        return

    ###################################################
    # SEND USER MESSAGE TO THEIR OPENAI THREAD
    ###################################################
    openai_thread_id = user_threads[user.id]

    client_openai.beta.threads.messages.create(
        thread_id=openai_thread_id,
        role="user",
        content=message.content
    )

    # Run the assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=openai_thread_id,
        assistant_id=ASSISTANT_ID
    )

    # Get the assistant’s reply
    ai_reply = ""
    for msg in client_openai.beta.threads.messages.list(thread_id=openai_thread_id).data:
        if msg.role == "assistant":
            ai_reply = msg.content[0].text.value
            break

    ###################################################
    # SEND REPLY BACK TO DISCORD
    ###################################################
    if ai_reply:
        await message.channel.send(ai_reply)

bot.run(DISCORD_TOKEN)
