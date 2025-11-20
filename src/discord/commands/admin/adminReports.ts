import {
  ChatInputCommandInteraction,
  SlashCommandBuilder
} from "discord.js";

import { isAdmin } from "../../../services/admin/adminAuth";
import {
  getEngagementReport,
  getStageReport,
  getStuckUsersReport
} from "../../../services/admin/adminReportsService";

export const data = new SlashCommandBuilder()
  .setName("admin_reports")
  .setDescription("Generate analytical reports about users")
  .addSubcommand(sub =>
    sub.setName("engagement").setDescription("Show user engagement report")
  )
  .addSubcommand(sub =>
    sub.setName("stages").setDescription("Show stage distribution")
  )
  .addSubcommand(sub =>
    sub.setName("stuck_users").setDescription("Show inactive or stalled users")
  );

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
    if (sub === "engagement") {
      const engagement = await getEngagementReport();

      return interaction.editReply({
        content: `📊 **Engagement Report**\n• Users tracking habits: **${engagement.usersTrackingHabits}**`
      });
    }

    if (sub === "stages") {
      const stages = await getStageReport();

      return interaction.editReply({
        content: `📍 **Stage Report**\n• Users with roadmaps: **${stages.usersWithRoadmaps}**`
      });
    }

    if (sub === "stuck_users") {
      const stuck = await getStuckUsersReport();

      return interaction.editReply({
        content: `⚠ **Stuck Users**\n${Array.isArray(stuck) ? stuck.join("\n") : stuck}`
      });
    }

    return interaction.editReply({
      content: "❌ Unknown report type."
    });

  } catch (err) {
    console.error(err);
    return interaction.editReply({
      content: "❌ Error generating report."
    });
  }
}
