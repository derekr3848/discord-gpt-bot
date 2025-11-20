import {
  ChatInputCommandInteraction,
  SlashCommandBuilder
} from "discord.js";

import { isAdmin } from "../../../services/admin/adminAuth";
import { setGlobalConfig } from "../../../services/admin/adminConfigService";

export const data = new SlashCommandBuilder()
  .setName("admin_config")
  .setDescription("Modify system-wide configuration values")
  .addStringOption(opt =>
    opt.setName("key").setDescription("Config key").setRequired(true)
  )
  .addStringOption(opt =>
    opt.setName("value").setDescription("Config value (JSON/string)").setRequired(true)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Unauthorized.",
      ephemeral: true
    });
  }

  const key = interaction.options.getString("key", true);
  const valueRaw = interaction.options.getString("value", true);

  await interaction.reply({
    content: `⚙ Updating config \`${key}\`...`,
    ephemeral: true
  });

  try {
    // Try to parse JSON value; fallback to string
    let value: any;
    try {
      value = JSON.parse(valueRaw);
    } catch {
      value = valueRaw;
    }

    await setGlobalConfig(key, value);

    return interaction.editReply({
      content: `✅ Updated global config:\n\`${key}\` → \`${valueRaw}\``
    });
  } catch (err) {
    console.error(err);

    return interaction.editReply({
      content: "❌ Failed to update config."
    });
  }
}
