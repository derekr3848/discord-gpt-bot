import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { generateJobDescription, generateInterviewQuestions, generateSOP } from "../../../services/coaching/hiring";
import { MessageFlags } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("hiring")
  .setDescription("Get hiring, training, and staffing help")
  .addSubcommand(sub =>
    sub
      .setName("jd")
      .setDescription("Generate a job description")
      .addStringOption(opt =>
        opt.setName("role").setDescription("Role title").setRequired(true)
      )
  )
  .addSubcommand(sub =>
    sub
      .setName("interview")
      .setDescription("Generate interview questions")
      .addStringOption(opt =>
        opt.setName("role").setDescription("Role title").setRequired(true)
      )
  )
  .addSubcommand(sub =>
    sub
      .setName("sop")
      .setDescription("Generate SOP for a role")
      .addStringOption(opt =>
        opt.setName("role").setDescription("Role title").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const sub = interaction.options.getSubcommand();
  const role = interaction.options.getString("role", true);

  await interaction.reply({
    content: `⏳ Creating **${role}** hiring docs...`,
  flags: MessageFlags.Ephemeral
  });

  try {
    switch (sub) {
      case "jd": {
        const jd = await generateJobDescription(userId, role);
        return interaction.editReply({ content: `📄 **Job Description:**\n${jd}` });
      }

      case "interview": {
        const qs = await generateInterviewQuestions(userId, role);
        return interaction.editReply({ content: `🎤 **Interview Questions:**\n${qs}` });
      }

      case "sop": {
        const sop = await generateSOP(userId, role);
        return interaction.editReply({ content: `🛠 **SOP:**\n${sop}` });
      }
    }
  } catch (err) {
    console.error(err);
    return interaction.editReply({
      content: "❌ Failed to generate hiring materials."
    });
  }
}
