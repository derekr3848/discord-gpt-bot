import {
  ChatInputCommandInteraction,
  SlashCommandBuilder
} from "discord.js";

import {
  addHabit,
  listHabits,
  completeHabit,
  habitStats
} from "../../../services/coaching/habits";

export const data = new SlashCommandBuilder()
  .setName("habits")
  .setDescription("Manage your execution habits")
  .addSubcommand((sub) =>
    sub
      .setName("add")
      .setDescription("Add a new habit")
      .addStringOption((opt) =>
        opt
          .setName("description")
          .setDescription("Describe the habit")
          .setRequired(true)
      )
      .addStringOption((opt) =>
        opt
          .setName("frequency")
          .setDescription("How often?")
          .addChoices(
            { name: "Daily", value: "daily" },
            { name: "Weekly", value: "weekly" },
            { name: "Custom", value: "custom" }
          )
          .setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub.setName("list").setDescription("Show all habits")
  )
  .addSubcommand((sub) =>
    sub
      .setName("complete")
      .setDescription("Mark a habit complete for today")
      .addStringOption((opt) =>
        opt.setName("id").setDescription("Habit ID").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub.setName("stats").setDescription("Show habit statistics")
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const sub = interaction.options.getSubcommand();

  await interaction.reply({
    content: "Processing...",
    ephemeral: true
  });

  try {
    if (sub === "add") {
      const description = interaction.options.getString("description", true);
      const frequency = interaction.options.getString("frequency", true) as
        | "daily"
        | "weekly"
        | "custom";

      const habit = await addHabit(userId, description, frequency);

      return interaction.editReply({
        content: `📝 Added new habit:\n\`${habit.description}\``
      });
    }

    if (sub === "list") {
      const habits = await listHabits(userId);
      if (!habits.habits.length) {
        return interaction.editReply({ content: "No habits yet." });
      }

      const formatted = habits.habits
        .map((h) => `• **${h.description}** → \`${h.id}\``)
        .join("\n");

      return interaction.editReply({
        content: `📋 **Your Habits:**\n${formatted}`
      });
    }

    if (sub === "complete") {
      const habitId = interaction.options.getString("id", true);
      await completeHabit(userId, habitId);

      return interaction.editReply({
        content: `🔥 Marked complete for today!`
      });
    }

    if (sub === "stats") {
      const stats = await habitStats(userId);

      if (Object.keys(stats).length === 0) {
        return interaction.editReply({
          content: "No habit stats yet."
        });
      }

      const formatted = Object.entries(stats)
        .map(([id, count]) => `• \`${id}\`: **${count} completions**`)
        .join("\n");

      return interaction.editReply({
        content: `📊 **Habit Stats:**\n${formatted}`
      });
    }
  } catch (error) {
    console.error(error);
    return interaction.editReply("❌ Error processing command.");
  }
}
