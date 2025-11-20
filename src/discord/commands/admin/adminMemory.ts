import {
  ChatInputCommandInteraction,
  SlashCommandBuilder
} from "discord.js";

import { isAdmin } from "../../../services/admin/adminAuth";
import {
  getUserMemory,
  setUserMemory,
  deleteUserMemory
} from "../../../services/admin/adminMemoryService";

export const data = new SlashCommandBuilder()
  .setName("admin_memory")
  .setDescription("Inspect or modify user memory")
  .addSubcommand((sub) =>
    sub
      .setName("get")
      .setDescription("Read a key from user memory")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("key").setDescription("Memory key").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("set")
      .setDescription("Write a value in user memory")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("key").setDescription("Memory key").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("value").setDescription("Value (JSON)").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("delete")
      .setDescription("Delete a key from memory")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("key").setDescription("Memory key").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Unauthorized.",
      ephemeral: true
    });
  }

  const sub = interaction.options.getSubcommand();
  const userId = interaction.options.getString("user", true);
  const key = interaction.options.getString("key", true);

  await interaction.reply({
    content: `⏳ Processing memory request...`,
    ephemeral: true
  });

  try {
    if (sub === "get") {
      const value = await getUserMemory(userId);
      return interaction.editReply({
        content: `📄 **Memory Dump for ${userId}**\n\`\`\`json\n${JSON.stringify(
          value,
          null,
          2
        )}\n\`\`\``
      });
    }

    if (sub === "set") {
      const valueRaw = interaction.options.getString("value", true);
      const parsed = JSON.parse(valueRaw);
      await setUserMemory(userId, key, parsed);

      return interaction.editReply({
        content: `✅ Updated memory key \`${key}\` for user **${userId}**`
      });
    }

    if (sub === "delete") {
      await deleteUserMemory(userId, key);

      return interaction.editReply({
        content: `🗑 Deleted memory key \`${key}\` for user **${userId}**`
      });
    }
  } catch (err) {
    console.error(err);
    return interaction.editReply({
      content: `❌ Memory operation failed.`
    });
  }
}
