import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

// FIXED PATH
import { memory } from "../../../memory";

// FIXED FUNCTION NAME
import { setUserStage } from "../../../services/coaching/roadmap";

// Keeping embed imports (tell me if you need the file)
import { successEmbed, errorEmbed, toReplyOptions } from "../../../utils/embeds";

export const data = new SlashCommandBuilder()
  .setName("plan")
  .setDescription("View or update your growth roadmap")
  .addSubcommand((sub) =>
    sub.setName("view").setDescription("Show your current roadmap stage and tasks")
  )
  .addSubcommand((sub) =>
    sub
      .setName("set_stage")
      .setDescription("Manually set your current stage")
      .addStringOption((opt) =>
        opt.setName("stage_id").setDescription("Stage ID (e.g. stage-1)").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const sub = interaction.options.getSubcommand();
  const userId = interaction.user.id;
  const roadmap = await memory.getRoadmap(userId);

  if (!roadmap) {
    return interaction.reply({
      embeds: [
        errorEmbed(
          "No roadmap yet",
          "I need to onboard you first. Run `/start` to begin intake."
        )
      ],
      ephemeral: true
    });
  }

  if (sub === "view") {
    const current = roadmap.stages.find((s: any) => s.id === roadmap.currentStageId);

    if (!current) {
      return interaction.reply({
        embeds: [errorEmbed("Error", "Current stage not found in roadmap.")],
        ephemeral: true
      });
    }

    const embed = successEmbed(`Current Stage: ${current.name}`, current.description, {
      fields: [
        { name: "Objectives", value: current.objectives?.join("\n") || "None" },
        { name: "Tasks", value: current.tasks?.join("\n") || "None" },
        { name: "Habits", value: current.habits?.join("\n") || "None" },
        { name: "KPIs", value: current.kpis?.join("\n") || "None" }
      ]
    });

    return interaction.reply({
      embeds: [embed],
      ephemeral: true
    });
  }

  if (sub === "set_stage") {
    const stageId = interaction.options.getString("stage_id", true);
    const updated = await setUserStage(userId, stageId);

    if (!updated) {
      return interaction.reply({
        embeds: [errorEmbed("Stage not found", `Stage ID \`${stageId}\` not found.`)],
        ephemeral: true
      });
    }

    return interaction.reply({
      embeds: [
        successEmbed(
          "Stage Updated",
          `You are now on stage: **${updated.current_stage ?? updated.currentStageId}**`
        )
      ],
      ephemeral: true
    });
  }
}
