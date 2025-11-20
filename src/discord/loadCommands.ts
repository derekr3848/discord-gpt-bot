import fs from "fs";
import path from "path";
import { Client } from "discord.js";

export function loadCommands(client: Client) {
  const commandsPath = path.join(__dirname, "commands");
  const commandFiles = getAllFiles(commandsPath);

  for (const file of commandFiles) {
    const command = require(file);

    if (!command.data || !command.execute) {
      console.warn(`[WARN] Skipping invalid command file: ${file}`);
      continue;
    }

    client.commands.set(command.data.name, command);
  }

  console.log(`[CMD] Loaded ${client.commands.size} commands`);
}

// Utility to recurse folders
function getAllFiles(dir: string, files?: string[]): string[] {
  files = files || [];
  for (const file of fs.readdirSync(dir)) {
    const full = path.join(dir, file);
    if (fs.statSync(full).isDirectory()) getAllFiles(full, files);
    else if (full.endsWith(".ts") || full.endsWith(".js")) files.push(full);
  }
  return files;
}
