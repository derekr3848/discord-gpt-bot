import {
  ChatInputCommandInteraction,
  SlashCommandBuilder
} from "discord.js";

import { isAdmin } from "../../../services/admin/adminAuth";

import {
  resetAllUserData,
  updateUserProfileField,
  toggleUserPushMode,
  setUserStage
} from "../../../services/admin/adminStateService";

export const data = new SlashCommandBuilder()
  .setName("admin_state")
  .setDescription("Control user lifecycle / stage state")
  .addSubcommand((sub) =>
    sub
      .setName("set_stage")
      .setDescription("Set a user's roadmap stage")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("stage").setDescription("Stage name").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("reset")
      .setDescription("Reset ALL user data")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("profile_set")
      .setDescription("Update a profile field")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("key").setDescription("Field name").setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName("value").setDescription("Field value").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("pushmode")
      .setDescription("Toggle push accountability mode")
      .addStringOption((opt) =>
        opt.setName("user").setDescription("Target user ID").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 Unauthorized.",
      ephemeral: true
    });
  }

  const sub = interaction.options.getSubcommand();
  const userId = interaction.options.getString("user", true);

  await interaction.reply({
    content: `⏳ Executing ${sub}...`,
    ephemeral: true
  });

  try {
    if (sub === "set_stage") {
      const stage = interaction.options.getString("stage", true);
      const result = await setUserStage(userId, stage);

      return interaction.editReply({
        content: `📍 Stage updated for **${userId}** → \`${stage}\``
      });
    }

    if (sub === "reset") {
      await resetAllUserData(userId);

      return interaction.editReply({
        content: `🗑 All data cleared for user **${userId}**.`
      });
    }

    if (sub === "profile_set") {
      const key = interaction.options.getString("key", true);
      const value = interaction.options.getString("value", true);

      await updateUserProfileField(userId, key, value);

      return interaction.editReply({
        content: `📝 Updated profile field \`${key}\` → \`${value}\``
      });
    }

    if (sub === "pushmode") {
      await toggleUserPushMode(userId);

      return interaction.editReply({
        content: `🔥 Toggled push mode for **${userId}**`
      });
    }
  } catch (err) {
    console.error(err);
    return interaction.editReply({
      content: "❌ Error updating state."
    });
  }
}
