import { redis } from "../../memory/redisClient";

export async function resetAllUserData(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);

  if (keys.length > 0) {
    await redis.del(keys);
  }

  return { cleared: keys.length };
}

export async function updateUserProfileField(
  userId: string,
  key: string,
  value: any
) {
  const profileKey = `user:${userId}:profile`;
  const profile = (await redis.json.get(profileKey)) || {};

  profile[key] = value;

  await redis.json.set(profileKey, "$", profile);

  return profile;
}

export async function toggleUserPushMode(userId: string) {
  const key = `user:${userId}:pushmode`;
  const current = (await redis.get(key)) === "true";

  await redis.set(key, (!current).toString());

  return !current;
}

export async function setUserStage(userId: string, stage: string) {
  const key = `user:${userId}:roadmap`;
  const roadmap = (await redis.json.get(key)) || {};

  roadmap.current_stage = stage;
  roadmap.updatedAt = new Date().toISOString();

  await redis.json.set(key, "$", roadmap);

  return roadmap;
}
