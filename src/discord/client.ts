import { Client, GatewayIntentBits, Partials } from 'discord.js';
import { env } from '../config/env';
import { log } from '../services/logger';

export const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.MessageContent
  ],
  partials: [Partials.Channel]
});

client.once('ready', () => {
  log.info(`Logged in as ${client.user?.tag}`);
});

export async function startDiscordClient() {
  await client.login(env.DISCORD_BOT_TOKEN);
}

