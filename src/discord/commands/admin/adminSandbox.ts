import {
  ChatInputCommandInteraction,
  SlashCommandBuilder
} from "discord.js";

import { isAdmin } from "../../../services/admin/adminAuth";
import { simulateUserMessage } from "../../../services/admin/adminSandboxService";

export const data = new SlashCommandBuilder()
  .setName("admin_sandbox")
  .setDescription("Simulate responses without affecting memory")
  .addStringOption(opt =>
    opt.setName("user").setDescription("Target user ID").setRequired(true)
  )
  .addStringOption(opt =>
    opt.setName("message").setDescription("Message to simulate").setRequired(true)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Unauthorized.",
      ephemeral: true
    });
  }

  const userId = interaction.options.getString("user", true);
  const message = interaction.options.getString("message", true);

  await interaction.reply({
    content: `⏳ Simulating reply...`,
    ephemeral: true
  });

  const result = await simulateUserMessage(userId, message);

  return interaction.editReply({
    content: `🧪 **Simulation Result**\nUser: \`${userId}\`\nMessage: \`${message}\`\nResponse:\n${result.result}`
  });
}
