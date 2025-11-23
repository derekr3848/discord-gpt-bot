import {
  ChatInputCommandInteraction,
  SlashCommandBuilder,
  MessageFlags,
  TextChannel
} from "discord.js";

import {
  startIntake,
  getIntakeState,
  INTAKE_QUESTIONS,
  updateIntakeState,
  finalizeIntake
} from "../../../services/coaching/intake";

import { successEmbed, toReplyOptions } from "../../../utils/embeds";
import { memory } from "../../../memory";

export const data = new SlashCommandBuilder()
  .setName("start")
  .setDescription("Begin onboarding intake and diagnosis");

export async function execute(interaction: ChatInputCommandInteraction) {
  console.log("🚀 /start triggered by", interaction.user.id);

  const userId = interaction.user.id;

  // Must be used in a server channel
  if (!interaction.inGuild()) {
    return interaction.reply({
      content: "⚠ You must run this in a server channel, not DMs.",
      flags: MessageFlags.Ephemeral,
    });
  }

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

  // Start intake
  const state = await startIntake(userId);
  const q = INTAKE_QUESTIONS[state.stepIndex];

  // Acknowledge command
  await interaction.reply({
    embeds: [
      successEmbed(
        "Onboarding started",
        `I'll guide you through onboarding **here in a new thread.**\n\n**Q1:** ${q.question}`
      )
    ],
    flags: MessageFlags.Ephemeral
  });

  // 💡 Narrow channel type so threads exist
  const channel = interaction.channel as TextChannel;

  // Create a new thread
  const thread = await channel.threads.create({
    name: `intake-${interaction.user.username}`,
    autoArchiveDuration: 1440,
    reason: "User onboarding flow"
  });

  await thread.send(
    `Hey ${interaction.user.username}, let’s begin.\n\n**Q1:** ${q.question}`
  );
}


// =============================
// HANDLE FOLLOW-UP MESSAGES
// =============================
export async function handleIntakeAnswer(userId: string, content: string) {
  console.log("📩 Intake thread message:", userId, content);

  const state = await getIntakeState(userId);
  if (!state) return null;

  const idx = state.stepIndex;
  const q = INTAKE_QUESTIONS[idx];
  if (!q) return null;

  const nextState = await updateIntakeState(userId, (s) => {
    s.answers[q.key] = content.trim();
    s.stepIndex += 1;
    return s;
  });

  const nextQ = INTAKE_QUESTIONS[nextState.stepIndex];
  return { done: !nextQ, nextQuestion: nextQ };
}

export async function completeIntakeFlow(userId: string, username: string) {
  console.log("🏁 Finalizing intake for", userId);
  return finalizeIntake(userId, username);
}
