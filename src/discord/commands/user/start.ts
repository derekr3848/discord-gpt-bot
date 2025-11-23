import { ChatInputCommandInteraction, SlashCommandBuilder, MessageFlags } from "discord.js";
import {
  startIntake,
  getIntakeState,
  INTAKE_QUESTIONS,
  updateIntakeState,
  finalizeIntake
} from "../../../services/coaching/intake";
import { successEmbed, toReplyOptions } from "../../../utils/embeds";
import { memory } from "../../../memory";
import { MessageFlags } from "discord.js";


export const data = new SlashCommandBuilder()
  .setName("start")
  .setDescription("Begin onboarding intake and diagnosis");

export async function execute(interaction: ChatInputCommandInteraction) {
  console.log("🚀 /start triggered by", interaction.user.id);

  const userId = interaction.user.id;
  const existingProfile = await memory.getProfile(userId);

  if (existingProfile) {
    return interaction.reply({
      ...toReplyOptions(
        successEmbed(
          "Onboarding already completed",
          "You already have a profile. Use `/plan`, `/offer`, `/marketing`, etc."
        )
      ),
      flags: MessageFlags.Ephemeral
    });
  }

  const state = await startIntake(userId);
  const q = INTAKE_QUESTIONS[state.stepIndex];

  await interaction.reply({
    embeds: [
      successEmbed(
        "Onboarding started",
        `I'll ask onboarding questions here.\n\n**Q1:** ${q.question}`
      )
    ],
    flags: MessageFlags.Ephemeral
  });

  // Create thread publicly
  const thread = await interaction.channel?.threads.create({
    name: `intake-${interaction.user.username}`,
    autoArchiveDuration: 1440,
    reason: "User onboarding flow"
  });

  await thread.send(
    `Hey ${interaction.user.username}, let’s begin.\n\n**Q1:** ${q.question}`
  );
}
