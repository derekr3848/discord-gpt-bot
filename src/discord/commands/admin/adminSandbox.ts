import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { isAdmin } from "../../../services/admin/adminAuth";
import { simulateUserMessage } from "../../../services/admin/adminSandboxService";

export const data = new SlashCommandBuilder()
  .setName("admin_sandbox")
  .setDescription("Simulate bot responses without saving memory")
  .addStringOption(o =>
    o.setName("user_id").setDescription("User to simulate as").setRequired(true)
  )
  .addStringOption(o =>
    o.setName("message").setDescription("Message to simulate").setRequired(true)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Unauthorized.",
      ephemeral: true
    });
  }

  const userId = interaction.options.getString("user_id", true);
  const message = interaction.options.getString("message", true);

  await interaction.reply({
    content: `🧪 Simulating bot response as <@${userId}>...`,
    ephemeral: true
  });

  try {
    const result = await simulateUserMessage(userId, message);

    await interaction.editReply({
      content: `**Preview Response (No Memory Written):**\n\`\`\`${result}\`\`\``
    });
  } catch (err) {
    console.error(err);
    await interaction.editReply({
      content: "❌ Sandbox simulation failed."
    });
  }
}
