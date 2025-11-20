import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { isAdmin } from "../../../services/admin/adminAuth";
import { getUserMemory, setUserMemoryKey, deleteUserMemoryKey } from "../../../services/admin/adminMemoryService";

export const data = new SlashCommandBuilder()
  .setName("admin_memory")
  .setDescription("Inspect or modify user memory")
  .addSubcommand(sub =>
    sub.setName("get")
      .setDescription("Retrieve a memory key for a user")
      .addStringOption(o => o.setName("user_id").setDescription("Target user").setRequired(true))
      .addStringOption(o => o.setName("key").setDescription("Memory key").setRequired(true))
  )
  .addSubcommand(sub =>
    sub.setName("set")
      .setDescription("Set a memory key for a user")
      .addStringOption(o => o.setName("user_id").setDescription("Target user").setRequired(true))
      .addStringOption(o => o.setName("key").setDescription("Memory key").setRequired(true))
      .addStringOption(o => o.setName("value").setDescription("Value to set").setRequired(true))
  )
  .addSubcommand(sub =>
    sub.setName("delete")
      .setDescription("Delete a memory key for a user")
      .addStringOption(o => o.setName("user_id").setDescription("Target user").setRequired(true))
      .addStringOption(o => o.setName("key").setDescription("Memory key").setRequired(true))
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Not authorized.",
      ephemeral: true
    });
  }

  const sub = interaction.options.getSubcommand();
  const userId = interaction.options.getString("user_id", true);

  await interaction.reply({
    content: `⏳ Processing memory command \`${sub}\`...`,
    ephemeral: true
  });

  try {
    switch (sub) {
      case "get": {
        const key = interaction.options.getString("key", true);
        const value = await getUserMemory(userId, key);

        await interaction.editReply({
          content: `📦 **Memory for <@${userId}>**\n\`${key}\` → \`\`\`${JSON.stringify(value, null, 2)}\`\`\``
        });
        break;
      }

      case "set": {
        const key = interaction.options.getString("key", true);
        const value = interaction.options.getString("value", true);

        await setUserMemoryKey(userId, key, value);

        await interaction.editReply({
          content: `✅ **Updated memory key**\n${key} → \`${value}\``
        });
        break;
      }

      case "delete": {
        const key = interaction.options.getString("key", true);

        await deleteUserMemoryKey(userId, key);

        await interaction.editReply({
          content: `🗑 **Deleted memory key**\n${key}`
        });
        break;
      }

      default:
        await interaction.editReply({
          content: "❌ Unknown memory command."
        });
    }
  } catch (err) {
    console.error(err);
    await interaction.editReply({
      content: "❌ Error processing memory request."
    });
  }
}
