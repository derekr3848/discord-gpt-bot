import { Collection, CommandInteraction } from 'discord.js';
import * as startCmd from './commands/user/start';
import * as planCmd from './commands/user/plan';
import * as habitsCmd from './commands/user/habits';
import * as pushmodeCmd from './commands/user/pushmode';
import * as offerCmd from './commands/user/offer';
import * as marketingCmd from './commands/user/marketing';
import * as salesCmd from './commands/user/salesReview';
import * as hiringCmd from './commands/user/hiring';
import * as mindsetCmd from './commands/user/mindset';

import * as adminStateCmd from './commands/admin/adminState';
import * as adminActionsCmd from './commands/admin/adminActions';
import * as adminReportsCmd from './commands/admin/adminReports';
import * as adminMemoryCmd from './commands/admin/adminMemory';
import * as adminConfigCmd from './commands/admin/adminConfig';
import * as adminSandboxCmd from './commands/admin/adminSandbox';

export interface SlashCommand {
  data: any;
  execute: (interaction: any) => Promise<void>;
}

export const commands = new Collection<string, SlashCommand>();

[
  startCmd,
  planCmd,
  habitsCmd,
  pushmodeCmd,
  offerCmd,
  marketingCmd,
  salesCmd,
  hiringCmd,
  mindsetCmd,
  adminStateCmd,
  adminActionsCmd,
  adminReportsCmd,
  adminMemoryCmd,
  adminConfigCmd,
  adminSandboxCmd
].forEach((cmd: any) => {
  commands.set(cmd.data.name, cmd);
});

export async function handleInteraction(interaction: CommandInteraction) {
  const command = commands.get(interaction.commandName);
  if (!command) return;
  await command.execute(interaction);
}

