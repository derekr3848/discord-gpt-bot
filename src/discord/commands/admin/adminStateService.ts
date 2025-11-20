import { redis } from "../../memory/redisClient";

export async function resetAllUserData(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  if (keys.length > 0) await redis.del(keys);
  return true;
}

export async function setUserStage(userId: string, stage: string) {
  await redis.json.set(`user:${userId}:roadmap`, "$.current_stage", stage);
  return true;
}

export async function toggleUserPushMode(userId: string, enabled: boolean) {
  await redis.json.set(`user:${userId}:pushmode`, "$", {
    enabled,
    updated: Date.now()
  });
  return true;
}

export async function updateUserProfileField(userId: string, field: string, value: any) {
  const key = `user:${userId}:profile`;
  const current = (await redis.json.get(key)) || {};
  current[field] = value;
  await redis.json.set(key, "$", current);
  return true;
}
