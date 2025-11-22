import { redis } from "../../memory/redisClient";

export async function resetAllUserData(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  if (keys.length > 0) {
    await redis.del(...keys);
  }

  return { cleared: keys.length };
}

export async function updateUserProfileField(
  userId: string,
  key: string,
  value: any
) {
  const profileKey = `user:${userId}:profile`;
  const raw = await redis.get(profileKey);

  // Parse existing JSON or create empty
  const profile = raw ? JSON.parse(raw) : {};

  profile[key] = value;

  // Store back as JSON
  await redis.set(profileKey, JSON.stringify(profile));

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
  const raw = await redis.get(key);

  const roadmap = raw ? JSON.parse(raw) : {};

  roadmap.currentStageId = stage;
  roadmap.updatedAt = new Date().toISOString();

  await redis.set(key, JSON.stringify(roadmap));

  return roadmap;
}
