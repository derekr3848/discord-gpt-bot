import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { generateMarketingAssets } from "../../../services/coaching/marketing";
import { successEmbed, errorEmbed } from "../../../utils/embeds";
import { memory } from "../../../memory/memory";

export const data = new SlashCommandBuilder()
  .setName("marketing")
  .setDescription("Generate marketing assets tailored to your offer")
  .addStringOption(opt =>
    opt
      .setName("kind")
      .setDescription("Type of assets")
      .addChoices(
        { name: "Meta ads", value: "ads" },
        { name: "Short-form scripts", value: "short-form" },
        { name: "Email sequence", value: "emails" },
        { name: "Social posts", value: "posts" }
      )
      .setRequired(true)
  )
  .addStringOption(opt =>
    opt
      .setName("extra")
      .setDescription("Any extra instructions (optional)")
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const profile = await memory.getProfile(userId);

  if (!profile) {
    return interaction.reply({
      content: "⚠ You must complete onboarding first. Run `/start`.",
      ephemeral: true
    });
  }

  const kind = interaction.options.getString("kind", true);
  const extra = interaction.options.getString("extra") ?? undefined;

  await interaction.reply({
    content: "⏳ Generating marketing assets...",
    ephemeral: true
  });

  try {
    const assets = await generateMarketingAssets(userId, kind, extra);

    const embed = successEmbed(
      "Marketing Assets Generated",
      "Here are your tailored assets:",
      {
        fields: [
          {
            name: "Output",
            value: "```markdown\n" + assets.slice(0, 3900) + "\n```"
          }
        ]
      }
    );

    return interaction.editReply({ embeds: [embed] });
  } catch (err) {
    console.error(err);
    return interaction.editReply({
      embeds: [errorEmbed("Error", "Failed to generate marketing assets.")]
    });
  }
}
