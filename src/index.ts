import {
  Client,
  GatewayIntentBits,
  Collection,
  Events,
  Interaction
} from "discord.js";

import { REST, Routes } from "discord.js";
import { env } from "./config/env";
import { isAdmin } from "./services/admin/adminAuth";
import { loadCommands } from "./discord/loadCommands";

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

// Register commands with Discord
async function registerCommands(client: any) {
  const rest = new REST({ version: "10" }).setToken(env.DISCORD_BOT_TOKEN);

  console.log("📡 Registering slash commands...");

  const commands = client.commands.map((cmd: any) => cmd.data.toJSON());

  await rest.put(
    Routes.applicationGuildCommands(env.DISCORD_CLIENT_ID, env.DISCORD_GUILD_ID), 
    { body: commands }
  );

  console.log("⚡ Commands registered to guild:", env.DISCORD_GUILD_ID);
}


// Ready event
client.once(Events.ClientReady, async (c) => {
  console.log(`🤖 Logged in as ${c.user.tag}`);
  await registerCommands(client);
});

// Command router
client.on(Events.InteractionCreate, async (interaction: Interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const command = client.commands.get(interaction.commandName);
  if (!command) {
    return interaction.reply({
      content: "❌ Command not implemented.",
      ephemeral: true
    });
  }

  try {
    await command.execute(interaction);
  } catch (err) {
    console.error(err);

    if (!interaction.replied && !interaction.deferred) {
      await interaction.reply({
        content: "❌ Error running command.",
        ephemeral: true
      });
    } else {
      await interaction.editReply({
        content: "❌ Command failed."
      });
    }
  }
});

// Start bot
client.login(env.DISCORD_BOT_TOKEN);
