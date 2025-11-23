import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import {
  startOfferWizard,
  getOfferWizardState,
  updateOfferWizardState,
  getCurrentOfferQuestion,
  finalizeOffer
} from '../../../services/coaching/offer';
import { successEmbed, errorEmbed, toReplyOptions } from '../../../utils/embeds';

export const data = new SlashCommandBuilder()
  .setName('offer')
  .setDescription('Offer builder wizard')
  .addSubcommand((sub) => sub.setName('start').setDescription('Start the offer builder wizard'))
  .addSubcommand((sub) => sub.setName('status').setDescription('View current saved offer'));

export async function execute(interaction: ChatInputCommandInteraction) {
  const sub = interaction.options.getSubcommand();
  const userId = interaction.user.id;

  if (sub === 'start') {
    const state = await startOfferWizard(userId);
    const q = getCurrentOfferQuestion(state);
    await interaction.reply({ content: "Working on offer...",  flags: MessageFlags.Ephemeral
});

    const dm = await interaction.user.createDM();
    await dm.send('**Offer Builder Wizard**\n\nQ1: ' + q?.question);
  } else if (sub === 'status') {
    const { memory } = await import("../../../memory");
    const offer = await memory.getOffer(userId);
    if (!offer) {
      await interaction.reply(
        toReplyOptions(errorEmbed('No offer yet', 'Run `/offer start` to build one.'))
      );
      return;
    }
    const embed = successEmbed(
      offer.offerName,
      offer.promise,
      {
        fields: [
          { name: 'Avatar', value: offer.avatar },
          { name: 'Price', value: offer.pricePoint },
          { name: 'Unique mechanism', value: offer.uniqueMechanism },
          { name: 'Program structure', value: offer.programStructure.slice(0, 1024) },
          { name: 'Guarantees', value: offer.guarantees.slice(0, 1024) }
        ]
      }
    );
    await interaction.reply({ embeds: [embed],  flags: MessageFlags.Ephemeral });
  }
}

// DM answer handler will use these:
export async function handleOfferAnswer(userId: string, content: string) {
  const state = await getOfferWizardState(userId);
  if (!state) return null;
  const q = getCurrentOfferQuestion(state);
  if (!q) return null;

  const nextState = await updateOfferWizardState(userId, (s) => {
    s.answers[q.key] = content.trim();
    s.stepIndex = s.stepIndex + 1;
    return s;
  });

  const nextQ = getCurrentOfferQuestion(nextState);
  return { done: !nextQ, nextQuestion: nextQ };
}

export async function completeOfferWizard(userId: string) {
  return finalizeOffer(userId);
}

