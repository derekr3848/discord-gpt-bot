import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { isAdmin } from "../../../services/admin/adminAuth";
import { getEngagementReport, getStageReport, getStuckUsersReport } from "../../../services/admin/adminReportsService";

export const data = new SlashCommandBuilder()
  .setName("admin_reports")
  .setDescription("Generate analytical reports about users")
  .addSubcommand(sub => sub.setName("engagement").setDescription("Show user engagement report"))
  .addSubcommand(sub => sub.setName("stages").setDescription("Show stage distribution"))
  .addSubcommand(sub => sub.setName("stuck_users").setDescription("Show inactive or stalled users"));

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Unauthorized.",
      ephemeral: true
    });
  }

  const sub = interaction.options.getSubcommand();

  await interaction.reply({
    content: `⏳ Generating report: \`${sub}\`...`,
    ephemeral: true
  });

  try {
    switch (sub) {
      case "engagement":
        const engagement = await getEngagementReport();
        await interaction.editReply({ content: engagement });
        break;

      case "stages":
        const stages = await getStageReport();
        await interaction.editReply({ content: stages });
        break;

      case "stuck_users":
        const stuck = await getStuckUsersReport();
        await interaction.editReply({ content: stuck });
        break;

      default:
        await interaction.editReply({
          content: "❌ Unknown report type."
        });
    }
  } catch (err) {
    console.error(err);
    await interaction.editReply({
      content: "❌ Error generating report."
    });
  }
}
