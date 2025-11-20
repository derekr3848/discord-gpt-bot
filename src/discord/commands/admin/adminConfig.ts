import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { isAdmin } from "../../../services/admin/adminAuth";
import { setGlobalConfig } from "../../../services/admin/adminConfigService";

export const data = new SlashCommandBuilder()
  .setName("admin_config")
  .setDescription("Modify global coaching config values")
  .addSubcommand(sub =>
    sub.setName("set")
      .setDescription("Update a configuration value")
      .addStringOption(opt =>
        opt.setName("key").setDescription("Configuration key").setRequired(true)
      )
      .addStringOption(opt =>
        opt.setName("value").setDescription("New value").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 You do not have permission to modify config.",
      ephemeral: true
    });
  }

  const key = interaction.options.getString("key", true);
  const value = interaction.options.getString("value", true);

  await interaction.reply({
    content: `⚙️ Updating config \`${key}\` → \`${value}\`...`,
    ephemeral: true
  });

  try {
    await setGlobalConfig(key, value);

    await interaction.editReply({
      content: `✅ **Config updated successfully**\n\`${key}\` is now set to:\n\`${value}\``
    });
  } catch (err) {
    console.error(err);
    await interaction.editReply({
      content: "❌ Failed to update configuration."
    });
  }
}
