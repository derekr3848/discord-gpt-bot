import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { isAdmin } from "../../../services/admin/adminAuth";
import { resetUserMemory, runMarketing, runSalesReview, rebuildOffer, generateWeeklyPlan } from "../../services/admin/adminActionsService";

export const data = new SlashCommandBuilder()
  .setName("admin_actions")
  .setDescription("Administrative actions for managing users")
  .addSubcommand(sub =>
    sub.setName("reset_user")
      .setDescription("Reset all stored memory for a user")
      .addStringOption(opt =>
        opt.setName("user_id").setDescription("Target user ID").setRequired(true)
      )
  )
  .addSubcommand(sub =>
    sub.setName("run_marketing")
      .setDescription("Generate marketing assets on behalf of the user")
      .addStringOption(opt =>
        opt.setName("user_id").setDescription("Target user ID").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 You do not have permission to perform admin actions.",
      ephemeral: true
    });
  }

  const userId = interaction.options.getString("user_id", true);
  const sub = interaction.options.getSubcommand();

  await interaction.reply({
    content: `⏳ Processing admin action \`${sub}\` for <@${userId}> ...`,
    ephemeral: true
  });

  try {
    switch (sub) {
      case "reset_user":
        await resetUserMemory(userId);
        await interaction.editReply({
          content: `✅ **User memory reset for <@${userId}>**`
        });
        break;

      case "run_marketing":
        const marketingOutput = await runMarketing(userId);
        await interaction.editReply({
          content: `📢 **Marketing assets generated and sent to user.**\n\nPreview:\n${marketingOutput}`
        });
        break;

      default:
        await interaction.editReply({
          content: "❌ Unknown admin action"
        });
    }
  } catch (err) {
    console.error(err);
    await interaction.editReply({
      content: "❌ Error executing admin action."
    });
  }
}
