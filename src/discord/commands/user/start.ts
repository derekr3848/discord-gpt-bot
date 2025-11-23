import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import {
  startIntake,
  getIntakeState,
  INTAKE_QUESTIONS,
  updateIntakeState,
  finalizeIntake,
} from "../../../services/coaching/intake";
import { successEmbed, errorEmbed, toReplyOptions } from "../../../utils/embeds";
import { memory } from "../../../memory";

export const data = new SlashCommandBuilder()
  .setName("start")
  .setDescription("Begin onboarding intake and diagnosis");

export async function execute(interaction: ChatInputCommandInteraction) {
  console.log("🚀 /start triggered by", interaction.user.id);

  try {
    const userId = interaction.user.id;

    // Check existing profile
    const existingProfile = await memory.getProfile(userId);

    if (existingProfile) {
      return interaction.reply(
        toReplyOptions(
          successEmbed(
            "Onboarding already completed",
            "You already have a profile. Use `/plan`, `/offer`, `/marketing`, etc.\nIf you want to redo onboarding, run `/start` again."
          )
        )
      );
    }

    // Start new intake state
    const state = await startIntake(userId);
    const q = INTAKE_QUESTIONS[state.stepIndex];

    // Respond immediately to avoid Discord timeout
    await interaction.reply({
      embeds: [
        successEmbed(
          "Onboarding started",
          `I'll DM you a series of questions.\n\n**Q1:** ${q.question}`
        ),
      ],
      ephemeral: true,
    });

    // Send first question via DM
    const dm = await interaction.user.createDM();
    await dm.send(
      `Hey, I’m Ave Crux AI Coach.\n\nLet's begin.\n\n**Q1:** ${q.question}`
    );

  } catch (err) {
    console.error("❌ ERROR in /start:", err);

    if (!interaction.replied) {
      await interaction.reply({
        content: "❌ Failed to start onboarding.",
        ephemeral: true,
      });
    }
  }
}

/**
 * Handles DM responses during onboarding
 */
export async function handleIntakeAnswer(userId: string, content: string) {
  console.log("📩 Intake DM received:", userId, content);

  const state = await getIntakeState(userId);
  if (!state) return null;

  const idx = state.stepIndex;
  const q = INTAKE_QUESTIONS[idx];
  if (!q) return null;

  const nextState = await updateIntakeState(userId, (s) => {
    s.answers[q.key] = content.trim();
    s.stepIndex = s.stepIndex + 1;
    return s;
  });

  const nextQ = INTAKE_QUESTIONS[nextState.stepIndex];
  return { done: !nextQ, nextQuestion: nextQ };
}

export async function completeIntakeFlow(userId: string, username: string) {
  console.log("🏁 Finalizing intake for", userId);
  return finalizeIntake(userId, username);
}
