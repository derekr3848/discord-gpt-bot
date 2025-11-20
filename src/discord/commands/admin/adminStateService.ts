import { redis } from "../../memory/redisClient";

function ensureObject(raw: any): Record<string, any> {
  if (typeof raw === "object" && raw !== null) return raw as Record<string, any>;
  return {};
}

export async function resetAllUserData(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  if (keys.length) await redis.del(keys);
  return { cleared: keys.length };
}

export async function updateUserProfileField(
  userId: string,
  key: string,
  value: any
) {
  const profileKey = `user:${userId}:profile`;
  const raw = await redis.json.get(profileKey);
  const profile = ensureObject(raw);

  profile[key] = value;

  await redis.json.set(profileKey, "$", profile);

  return profile;
}

export async function toggleUserPushMode(userId: string) {
  const key = `user:${userId}:pushmode`;
  const raw = await redis.get(key);

  const next = raw === "true" ? "false" : "true";
  await redis.set(key, next);

  return next === "true";
}

export async function setUserStage(userId: string, stage: string) {
  const key = `user:${userId}:roadmap`;
  const raw = await redis.json.get(key);
  const roadmap = ensureObject(raw);

  roadmap.current_stage = stage;
  roadmap.updatedAt = new Date().toISOString();

  await redis.json.set(key, "$", roadmap);

  return roadmap;
}
