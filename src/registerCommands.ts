import { REST, Routes } from 'discord.js';
import { env } from './config/env';
import { commands } from './discord/interactions';

async function main() {
  const rest = new REST({ version: '10' }).setToken(env.DISCORD_BOT_TOKEN);

  const body = commands.map((cmd) => cmd.data.toJSON());

  if (!env.DISCORD_CLIENT_ID) {
    throw new Error('DISCORD_CLIENT_ID is required to register commands');
  }

  if (env.DISCORD_GUILD_ID) {
    await rest.put(
      Routes.applicationGuildCommands(env.DISCORD_CLIENT_ID, env.DISCORD_GUILD_ID),
      { body }
    );
    console.log('Registered guild commands');
  } else {
    await rest.put(Routes.applicationCommands(env.DISCORD_CLIENT_ID), { body });
    console.log('Registered global commands');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

