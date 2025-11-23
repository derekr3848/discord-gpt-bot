import fs from "fs";
import path from "path";
import { Client } from "discord.js";

export function loadCommands(client: Client) {
  const commandsPath =
    process.env.NODE_ENV === "production"
      ? path.join(__dirname, "../discord/commands") // compiled .js location
      : path.join(__dirname, "commands"); // local dev

  const commandFiles = getAllFiles(commandsPath);

  for (const file of commandFiles) {
    const command = require(file);

    if (!command.data || !command.execute) {
      console.warn(`[WARN] Skipping invalid command file: ${file}`);
      continue;
    }

    client.commands.set(command.data.name, command);
  }

  console.log(`[CMD] Loaded ${client.commands.size} commands from ${commandsPath}`);
}

function getAllFiles(dir: string, files: string[] = []): string[] {
  if (!fs.existsSync(dir)) return files;

  for (const file of fs.readdirSync(dir)) {
    const full = path.join(dir, file);
    if (fs.statSync(full).isDirectory()) getAllFiles(full, files);
    else if (full.endsWith(".js") || full.endsWith(".ts")) files.push(full);
  }
  return files;
}
