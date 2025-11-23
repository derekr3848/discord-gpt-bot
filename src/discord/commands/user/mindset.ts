import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { handleMindsetMessage, generateMindsetResponse } from "../../../services/coaching/mindset";
import { memory } from "../../../memory";
import { errorEmbed } from "../../../utils/embeds";
import { MessageFlags } from "discord.js";


export const data = new SlashCommandBuilder()
  .setName("mindset")
  .setDescription("Mindset & identity-level support")
  .addStringOption(opt =>
    opt.setName("issue").setDescription("What are you struggling with?").setRequired(true)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const profile = await memory.getProfile(userId);

  if (!profile) {
    return interaction.reply({
      content: "⚠ Please complete onboarding first using `/start`.",
  flags: MessageFlags.Ephemeral
    });
  }

  const issue = interaction.options.getString("issue", true);

  await interaction.reply({ content: "⏳ Processing...", ephemeral: true });

  // Process mindset logic
  await handleMindsetMessage(userId, issue);

  // Generate natural language response
  const response = await generateMindsetResponse(userId, issue);

  return interaction.editReply({
    content: response
  });
}
