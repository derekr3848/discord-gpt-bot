import { 
  ChatInputCommandInteraction, 
  SlashCommandBuilder,
  ChannelType,
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
  .setDescription("Begin onboarding intake & create a private intake thread.");

/**
 * Slash command execution
 */
export async function execute(interaction: ChatInputCommandInteraction) {
  console.log("🚀 /start triggered by:", interaction.user.id);

  try {
    const userId = interaction.user.id;

    // Check if user already completed onboarding
    const existingProfile = await memory.getProfile(userId);
    if (existingProfile) {
      return interaction.reply(
        toReplyOptions(
          successEmbed(
            "Onboarding already completed",
            "You already have a profile. Use `/plan`, `/offer`, `/marketing`, etc."
          )
        )
      );
    }

    // Must run in a guild text channel
    if (!interaction.guild || interaction.channel?.type !== ChannelType.GuildText) {
      return interaction.reply({
        content: "❌ You must run this inside a server text channel.",
        ephemeral: true
      });
    }

    // Initialize onboarding
    const state = await startIntake(userId);
    const q = INTAKE_QUESTIONS[state.stepIndex];

    // Create thread in current channel
    const thread = await (interaction.channel as TextChannel).threads.create({
      name: `intake-${interaction.user.username}`,
      autoArchiveDuration: 1440,
      reason: "Onboarding intake started"
    });

    console.log(`📍 Created thread: ${thread.id}`);

    // Initial confirmation
    await interaction.reply({
      embeds: [
        successEmbed(
          "Onboarding started",
          `I created a private thread for your onboarding.\n\nHead there to begin!`
        )
      ],
      ephemeral: true
    });

    // Send first question in thread
    await thread.send(
      `👋 Hey <@${interaction.user.id}>! Let's begin your onboarding.\n\n**Q1:** ${q.question}\n\n*Type your answer below.*`
    );

  } catch (err) {
    console.error("❌ ERROR in /start:", err);

    if (!interaction.replied) {
      await interaction.reply({
        content: "❌ Failed to start onboarding.",
        ephemeral: true
      });
    }
  }
}

/**
 * Handle user replies INSIDE THREAD rather than DM
 */
export async function handleIntakeAnswer(userId: string, content: string) {
  console.log("📩 Intake thread message:", userId, content);

  const state = await getIntakeState(userId);
  if (!state) return null;

  const idx = state.stepIndex;
  const q = INTAKE_QUESTIONS[idx];
  if (!q) return null;

  // Save response
  const nextState = await updateIntakeState(userId, (s) => {
    s.answers[q.key] = content.trim();
    s.stepIndex++;
    return s;
  });

  const nextQ = INTAKE_QUESTIONS[nextState.stepIndex];
  return { done: !nextQ, nextQuestion: nextQ };
}

/**
 * Finalizing onboarding
 */
export async function completeIntakeFlow(userId: string, username: string) {
  console.log("🏁 Finalizing intake for", userId);
  return finalizeIntake(userId, username);
}
