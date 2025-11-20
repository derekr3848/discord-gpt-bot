import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { addHabit, completeHabit, getUserHabits, getHabitStats } from "../../../services/coaching/habits";

export const data = new SlashCommandBuilder()
  .setName("habits")
  .setDescription("Track, list, or complete habits")
  .addSubcommand(sub =>
    sub
      .setName("list")
      .setDescription("Show all habits")
  )
  .addSubcommand(sub =>
    sub
      .setName("add")
      .setDescription("Add a new habit")
      .addStringOption(opt =>
        opt.setName("name").setDescription("Habit name").setRequired(true)
      )
  )
  .addSubcommand(sub =>
    sub
      .setName("complete")
      .setDescription("Mark a habit as done")
      .addStringOption(opt =>
        opt.setName("name").setDescription("Habit name").setRequired(true)
      )
  )
  .addSubcommand(sub =>
    sub
      .setName("stats")
      .setDescription("View habit streaks and stats")
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const sub = interaction.options.getSubcommand();

  await interaction.reply({
    content: `⏳ Processing **${sub}**...`,
    ephemeral: true
  });

  try {
    switch (sub) {
      case "list": {
        const habits = await getUserHabits(userId);

        return interaction.editReply({
          content:
            habits && Object.keys(habits).length > 0
              ? `📋 **Your Habits:**\n` +
                Object.keys(habits)
                  .map(h => `• ${h}`)
                  .join("\n")
              : "📭 You have no habits yet."
        });
      }

      case "add": {
        const name = interaction.options.getString("name", true);
        await addHabit(userId, name);

        return interaction.editReply({
          content: `➕ Added new habit: **${name}**`
        });
      }

      case "complete": {
        const name = interaction.options.getString("name", true);
        await completeHabit(userId, name);

        return interaction.editReply({
          content: `✔ Completed **${name}** for today!`
        });
      }

      case "stats": {
        const stats = await getHabitStats(userId);

        return interaction.editReply({
          content: `📈 **Habit Stats:**\n\`\`\`${JSON.stringify(stats, null, 2)}\`\`\``
        });
      }
    }
  } catch (err) {
    console.error(err);
    return interaction.editReply({
      content: "❌ Error handling habit command."
    });
  }
}
