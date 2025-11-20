import { Events, Message } from 'discord.js';
import { startDiscordClient, client } from './discord/client';
import { handleInteraction } from './discord/interactions';
import { handleIntakeAnswer, completeIntakeFlow } from './discord/commands/user/start';
import { handleOfferAnswer, completeOfferWizard } from './discord/commands/user/offer';
import { log } from './services/logger';
import { memory } from './services/memory';
import { redis } from './services/redisClient';
import { coachingSystemPrompt } from './services/prompts';
import { chatCompletion } from './services/openaiClient';

async function main() {
  client.on(Events.InteractionCreate, async (interaction) => {
    if (!interaction.isChatInputCommand()) return;
    try {
      await handleInteraction(interaction);
    } catch (err) {
      log.error('Interaction error', err);
      if (interaction.deferred || interaction.replied) {
        await interaction.followUp({
          content: 'Something went wrong. Please try again.',
          ephemeral: true
        });
      } else {
        await interaction.reply({
          content: 'Something went wrong. Please try again.',
          ephemeral: true
        });
      }
    }
  });

  client.on(Events.MessageCreate, async (message: Message) => {
    // Ignore bot messages
    if (message.author.bot) return;

    // Only DM flows
    if (message.channel.type !== 1) return; // 1 = DMChannel in discord.js v14

    const userId = message.author.id;
    const content = message.content.trim();

    // Check intake flow
    const intakeStateRaw = await redis.get(`user:${userId}:intake_state`);
    if (intakeStateRaw) {
      const res = await handleIntakeAnswer(userId, content);
      if (!res) return;
      if (res.done) {
        await message.channel.send('Thanks! Let me analyze your answers and build your roadmap...');
        const { profile, roadmap, diagnosisText } = await completeIntakeFlow(
          userId,
          message.author.username
        );
        await memory.appendHistory(userId, 'assistant', diagnosisText);
        await message.channel.send(
          '**Diagnosis & Plan**\n\n' +
            diagnosisText.slice(0, 6000) +
            '\n\nYou can now use `/plan`, `/offer`, `/marketing`, etc.'
        );
      } else {
        await message.channel.send(`Next question:\n**${res.nextQuestion?.question}**`);
      }
      return;
    }

    // Check offer wizard flow
    const offerStateRaw = await redis.get(`user:${userId}:offer_state`);
    if (offerStateRaw) {
      const res = await handleOfferAnswer(userId, content);
      if (!res) return;
      if (res.done) {
        await message.channel.send('Great, let me synthesize your offer...');
        const { offer, raw } = await completeOfferWizard(userId);
        await memory.appendHistory(userId, 'assistant', raw);
        await message.channel.send(
          `**Offer built:** ${offer.offerName}\n\nPromise: ${offer.promise}\n\nUnique mechanism: ${offer.uniqueMechanism}`
        );
      } else {
        await message.channel.send(`Next question:\n**${res.nextQuestion?.question}**`);
      }
      return;
    }

    // General coaching DM: use memory-based personalization
    const [profile, roadmap, pushmode, offer, tone, faithMode] = await Promise.all([
      memory.getProfile(userId),
      memory.getRoadmap(userId),
      memory.getPushMode(userId),
      memory.getOffer(userId),
      redis.get('config:tone'),
      redis.get('config:faith_mode')
    ]);

    const system = coachingSystemPrompt({
      profile,
      roadmap,
      pushMode: pushmode,
      offer,
      globalTone: tone,
      globalFaithMode: (faithMode as any) || 'user'
    });

    await memory.appendHistory(userId, 'user', content);

    const reply = await chatCompletion(system, content, { maxTokens: 1200 });

    await memory.appendHistory(userId, 'assistant', reply);

    await message.channel.send(reply.slice(0, 2000));
  });

  await startDiscordClient();
}

main().catch((err) => {
  log.error('Fatal error', err);
  process.exit(1);
});

