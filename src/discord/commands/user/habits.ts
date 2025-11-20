import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { addHabit, listHabits, completeHabit, habitStats } from '../../../services/coaching/habits';
import { successEmbed, errorEmbed, toReplyOptions } from '../../../utils/embeds';

export const data = new SlashCommandBuilder()
  .setName('habits')
  .setDescription('Manage your execution habits')
  .addSubcommand((sub) =>
    sub
      .setName('add')
      .setDescription('Add a new habit')
      .addStringOption((opt) =>
        opt.setName('description').setDescription('Habit description').setRequired(true)
      )
      .addStringOption((opt) =>
        opt
          .setName('frequency')
          .setDescription('Frequency')
          .addChoices(
            { name: 'Daily', value: 'daily' },
            { name: 'Weekly', value: 'weekly' },
            { name: 'Custom', value: 'custom' }
          )
          .setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub.setName('list').setDescription('List your current habits')
  )
  .addSubcommand((sub) =>
    sub
      .setName('complete')
      .setDescription('Mark a habit as completed for today')
      .addStringOption((opt) =>
        opt.setName('habit_id').setDescription('Habit ID').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub.setName('stats').setDescription('View your habit completion stats')
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const sub = interaction.options.getSubcommand();
  const userId = interaction.user.id;

  if (sub === 'add') {
    const description = interaction.options.getString('description', true);
    const frequency = interaction.options.getString('frequency', true) as
      | 'daily'
      | 'weekly'
      | 'custom';
    const habit = await addHabit(userId, description, frequency);
    await interaction.reply(
      toReplyOptions(
        successEmbed(
          'Habit added',
          `ID: \`${habit.id}\`\nDescription: **${habit.description}**\nFrequency: ${habit.frequency}`
        )
      )
    );
  } else if (sub === 'list') {
    const data = await listHabits(userId);
    if (data.habits.length === 0) {
      await interaction.reply(toReplyOptions(successEmbed('No habits yet', 'Add one with `/habits add`.')));
      return;
    }
    const fields = data.habits.map((h) => ({
      name: `${h.description} (${h.frequency})`,
      value: `ID: \`${h.id}\``
    }));
    await interaction.reply({
      embeds: [successEmbed('Your habits', 'Here are your current habits:', { fields })],
      ephemeral: true
    });
  } else if (sub === 'complete') {
    const habitId = interaction.options.getString('habit_id', true);
    await completeHabit(userId, habitId);
    await interaction.reply(
      toReplyOptions(successEmbed('Nice work', `Marked habit \`${habitId}\` as completed for today.`))
    );
  } else if (sub === 'stats') {
    const [habits, stats] = await Promise.all([listHabits(userId), habitStats(userId)]);
    if (habits.habits.length === 0) {
      await interaction.reply(toReplyOptions(successEmbed('No habits yet', 'Add one with `/habits add`.')));
      return;
    }
    const fields = habits.habits.map((h) => ({
      name: h.description,
      value: `ID: \`${h.id}\`\nCompletions: **${stats[h.id] || 0}**`
    }));
    await interaction.reply({
      embeds: [successEmbed('Habit stats', 'Completions per habit:', { fields })],
      ephemeral: true
    });
  }
}

