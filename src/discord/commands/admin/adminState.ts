import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";
import { isAdmin } from "../../../services/admin/adminAuth";
import {
  resetAllUserData,
  setUserStage,
  updateUserProfileField,
  toggleUserPushMode
} from "../../../services/admin/adminStateService";

export const data = new SlashCommandBuilder()
  .setName("admin_state")
  .setDescription("Control and modify user state directly")

  // Reset ALL user data
  .addSubcommand(sub =>
    sub
      .setName("reset")
      .setDescription("Reset all memory and roadmap for a user")
      .addStringOption(o =>
        o.setName("user_id").setDescription("Target user ID").setRequired(true)
      )
  )

  // Direct stage setting
  .addSubcommand(sub =>
    sub
      .setName("set_stage")
      .setDescription("Override user roadmap stage")
      .addStringOption(o =>
        o.setName("user_id").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption(o =>
        o.setName("stage").setDescription("Stage to set").setRequired(true)
      )
  )

  // Push mode override
  .addSubcommand(sub =>
    sub
      .setName("toggle_pushmode")
      .setDescription("Force enable or disable push mode for a user")
      .addStringOption(o =>
        o.setName("user_id").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption(o =>
        o
          .setName("state")
          .setDescription("on | off")
          .addChoices(
            { name: "on", value: "on" },
            { name: "off", value: "off" }
          )
          .setRequired(true)
      )
  )

  // Edit profile field
  .addSubcommand(sub =>
    sub
      .setName("update_profile")
      .setDescription("Edit a user's profile field")
      .addStringOption(o =>
        o.setName("user_id").setDescription("Target user ID").setRequired(true)
      )
      .addStringOption(o =>
        o.setName("field").setDescription("Profile field to update").setRequired(true)
      )
      .addStringOption(o =>
        o.setName("value").setDescription("New value").setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdmin(interaction)) {
    return interaction.reply({
      content: "🚫 You do not have admin privileges.",
      ephemeral: true
    });
  }

  const sub = interaction.options.getSubcommand();
  const userId = interaction.options.getString("user_id", true);

  await interaction.reply({
    content: `⏳ Executing **${sub}** for <@${userId}>...`,
    ephemeral: true
  });

  try {
    switch (sub) {
      case "reset": {
        await resetAllUserData(userId);

        await interaction.editReply({
          content: `🧹 **All data reset for <@${userId}>**\nRoadmap, habits, memory cleared.`
        });
        break;
      }

      case "set_stage": {
        const stage = interaction.options.getString("stage", true);
        await setUserStage(userId, stage);

        await interaction.editReply({
          content: `📍 **Stage updated**\n<@${userId}> is now in stage **${stage}**`
        });
        break;
      }

      case "toggle_pushmode": {
        const state = interaction.options.getString("state", true);
        const enabled = state === "on";

        await toggleUserPushMode(userId, enabled);

        await interaction.editReply({
          content: `🔥 **Push mode ${enabled ? "enabled" : "disabled"}** for <@${userId}>`
        });
        break;
      }

      case "update_profile": {
        const field = interaction.options.getString("field", true);
        const value = interaction.options.getString("value", true);

        await updateUserProfileField(userId, field, value);

        await interaction.editReply({
          content: `📝 **Profile updated**\n\`${field}\` → \`${value}\``
        });
        break;
      }

      default:
        await interaction.editReply({
          content: "❌ Unknown admin state command."
        });
    }
  } catch (err) {
    console.error(err);
    await interaction.editReply({
      content: "❌ Failed to execute admin command."
    });
  }
}
