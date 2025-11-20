import { redis } from "../../memory/redisClient";

export async function setUserStage(userId: string, stage: string) {
  await redis.json.set(`user:${userId}:roadmap`, "$.currentStage", stage);
  return { ok: true, stage };
}
