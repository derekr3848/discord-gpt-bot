/*
import "dotenv/config";
import { REST, Routes } from "discord.js";
import { env } from "./config/env";
import fs from "fs";
import path from "path";

const commands: any[] = [];

const commandsPath = path.join(__dirname, "discord/commands");

function loadCommands() {
  const files = getAllFiles(commandsPath);
  for (const file of files) {
    const command = require(file);
    if (command.data) commands.push(command.data.toJSON());
  }
}

function getAllFiles(dir: string, files: string[] = []): string[] {
  for (const file of fs.readdirSync(dir)) {
    const full = path.join(dir, file);
    if (fs.statSync(full).isDirectory()) getAllFiles(full, files);
    else if (full.endsWith(".ts") || full.endsWith(".js")) files.push(full);
  }
  return files;
}

loadCommands();

console.log("📦 Loaded commands:", commands.map(c => c.name));

const rest = new REST({ version: "10" }).setToken(env.DISCORD_BOT_TOKEN);

(async () => {
  try {
    console.log(`📡 Registering ${commands.length} slash commands...`);

    await rest.put(
      Routes.applicationGuildCommands(env.DISCORD_CLIENT_ID!, env.DISCORD_GUILD_ID!),
      { body: commands }
    );

    console.log("⚡ Commands registered to DEV guild");
  } catch (err) {
    console.error("❌ Failed to register commands:", err);
  }
})();
*/
