import {
  Client,
  GatewayIntentBits,
  Collection,
  Events,
  Interaction,
  Message
} from "discord.js";

import { REST, Routes } from "discord.js";
import { env } from "./config/env";
import { loadCommands } from "./discord/loadCommands";
import { handleIntakeAnswer, completeIntakeFlow } from "./discord/commands/start";

console.log(`[BOOT] Starting Ave Crux AI Coach in ${env.NODE_ENV} mode...`);

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages
  ]
});

// Attach commands to client
client.commands = new Collection();
loadCommands(client);

// -----------------------------
// REGISTER SLASH COMMANDS (GLOBAL)
// -----------------------------
async function registerCommands(client: any) {
  const rest = new REST({ version: "10" }).setToken(env.DISCORD_BOT_TOKEN);

  const commands = client.commands.map((cmd: any) => cmd.data.toJSON());

  console.log("📡 Registering GLOBAL slash commands...");

  await rest.put(
    Routes.applicationCommands(env.DISCORD_CLIENT_ID), // GLOBAL
    { body: commands }
  );

  console.log("🌍 Global slash commands registered!");
}

// -----------------------------
// BOT READY
// -----------------------------
client.once(Events.ClientReady, async (c) => {
  console.log(`🤖 Logged in as ${c.user.tag}`);
  await registerCommands(client);
});

// -----------------------------
// HANDLE SLASH COMMANDS
// -----------------------------
client.on(Events.InteractionCreate, async (interaction: Interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const command = client.commands.get(interaction.commandName);
  if (!command) {
    return interaction.reply({
      content: "❌ Command not found.",
      ephemeral: true
    });
  }

  try {
    await command.execute(interaction);
  } catch (err) {
    console.error("❌ Command Execution Error:", err);

    if (!interaction.replied && !interaction.deferred) {
      await interaction.reply({
        content: "❌ Error executing command.",
        ephemeral: true
      });
    }
  }
});

// -----------------------------
// HANDLE DM INTAKE FLOW
// -----------------------------
client.on(Events.MessageCreate, async (msg: Message) => {
  if (msg.author.bot) return;
  if (msg.guild) return; // only respond to DMs

  const res = await handleIntakeAnswer(msg.author.id, msg.content);
  if (!res) return;

  if (res.done) {
    await msg.reply("🎉 Finalizing your onboarding...");
    await completeIntakeFlow(msg.author.id, msg.author.username);
    await msg.reply("✔ Onboarding complete!");
  } else {
    await msg.reply(`**Next question:** ${res.nextQuestion.question}`);
  }
});

// -----------------------------
// START BOT
// -----------------------------
client.login(env.DISCORD_BOT_TOKEN);
