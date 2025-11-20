import {
  Client,
  GatewayIntentBits,
  Collection,
  Events,
  Interaction
} from "discord.js";

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

// Ready event
client.once(Events.ClientReady, (c) => {
  console.log(`🤖 Logged in as ${c.user.tag}`);
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

    // Only reply if not already replied
    if (!interaction.replied && !interaction.deferred) {
      await interaction.reply({
        content: "❌ An error occurred while executing this command.",
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
