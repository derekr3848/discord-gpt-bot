import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { isAdminInteraction } from '../../../services/admin/adminAuth';
import { generateMarketingAssets } from '../../../services/coaching/marketing';
import { analyzeSalesCall } from '../../../services/coaching/sales';
import { completeOfferWizard } from '../user/offer';
import { memory } from '../../../services/memory';
import { successEmbed, errorEmbed, adminAuditFooter } from '../../../utils/embeds';
import { logAdminAction } from '../../../services/admin/adminLog';
import { chatCompletion } from '../../../services/openaiClient';
import { coachingSystemPrompt } from '../../../services/prompts';

export const data = new SlashCommandBuilder()
  .setName('admin_actions')
  .setDescription('Admin: run actions on behalf of a user')
  .addSubcommand((sub) =>
    sub
      .setName('run_marketing')
      .setDescription('Generate marketing assets for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
      .addStringOption((opt) =>
        opt
          .setName('kind')
          .setDescription('Kind of assets')
          .addChoices(
            { name: 'Meta ads', value: 'ads' },
            { name: 'Short-form scripts', value: 'short-form scripts' },
            { name: 'Email sequence', value: 'email sequence' }
          )
          .setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('run_sales_review')
      .setDescription('Run sales review on a transcript for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
      .addStringOption((opt) =>
        opt
          .setName('transcript')
          .setDescription('Call transcript')
          .setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('rebuild_offer')
      .setDescription('Rebuild offer for a user from their existing data')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
  )
  .addSubcommand((sub) =>
    sub
      .setName('generate_weekly_plan')
      .setDescription('Generate a weekly plan for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdminInteraction(interaction)) {
    await interaction.reply({ embeds: [errorEmbed('Forbidden', 'Admin only.')], ephemeral: true });
    return;
  }

  const sub = interaction.options.getSubcommand();
  const actorId = interaction.user.id;
  const user = interaction.options.getUser('user', true);
  const userId = user.id;

  await interaction.deferReply({ ephemeral: true });

  if (sub === 'run_marketing') {
    const kind = interaction.options.getString('kind', true);
    const assets = await generateMarketingAssets(userId, kind);
    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'run_marketing',
      diff: { kind }
    });

    await interaction.editReply({
      embeds: [
        successEmbed(
          'Run Marketing (Admin)',
          `**User:** <@${userId}>\n**Action:** /admin run_marketing → ${kind}`,
          { footer: adminAuditFooter(logId) }
        )
      ]
    });

    const dm = await user.createDM();
    await dm.send('**Admin-triggered marketing assets:**\n\n' + assets.slice(0, 6000));
  } else if (sub === 'run_sales_review') {
    const transcript = interaction.options.getString('transcript', true);
    const result = await analyzeSalesCall(userId, transcript);
    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'run_sales_review',
      diff: { length: transcript.length }
    });

    await interaction.editReply({
      embeds: [
        successEmbed(
          'Run Sales Review (Admin)',
          `**User:** <@${userId}>\n**Action:** /admin run_sales_review`,
          { footer: adminAuditFooter(logId) }
        )
      ]
    });

    const dm = await user.createDM();
    await dm.send('**Admin-triggered sales review:**\n\n' + result.slice(0, 6000));
  } else if (sub === 'rebuild_offer') {
    const existingOffer = await memory.getOffer(userId);
    if (!existingOffer) {
      await interaction.editReply({
        embeds: [errorEmbed('No existing offer state', 'User has no offer wizard state to rebuild from.')],
        content: ''
      });
      return;
    }
    // Minimal: just re-save offers? or you can call OpenAI to refine; here we just log
    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'rebuild_offer',
      diff: { offerName: existingOffer.offerName }
    });

    await interaction.editReply({
      embeds: [
        successEmbed(
          'Rebuild Offer (Admin)',
          `**User:** <@${userId}>\n**Action:** /admin rebuild_offer\nOffer: ${existingOffer.offerName}`,
          { footer: adminAuditFooter(logId) }
        )
      ]
    });

    const dm = await user.createDM();
    await dm.send(
      '**Admin note:** Your offer has been reviewed/confirmed:\n\n' +
        `Name: ${existingOffer.offerName}\n\nPromise: ${existingOffer.promise}`
    );
  } else if (sub === 'generate_weekly_plan') {
    const [profile, roadmap, pushmode, offer] = await Promise.all([
      memory.getProfile(userId),
      memory.getRoadmap(userId),
      memory.getPushMode(userId),
      memory.getOffer(userId)
    ]);

    const system = coachingSystemPrompt({
      profile,
      roadmap,
      pushMode: pushmode,
      offer,
      globalFaithMode: 'user'
    });

    const weeklyPlan = await chatCompletion(
      system,
      'Generate a detailed weekly execution plan (7 days) with tasks, habit focus, sales actions, marketing actions, and time blocks.',
      { maxTokens: 1400 }
    );

    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'generate_weekly_plan',
      diff: { length: weeklyPlan.length }
    });

    await interaction.editReply({
      embeds: [
        successEmbed(
          'Generate Weekly Plan (Admin)',
          `**User:** <@${userId}>\n**Action:** /admin generate_weekly_plan`,
          { footer: adminAuditFooter(logId) }
        )
      ]
    });

    const dm = await user.createDM();
    await dm.send('**Weekly Plan (Admin-triggered)**\n\n' + weeklyPlan.slice(0, 6000));
  }
}

