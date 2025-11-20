import { redis } from "../../memory/redisClient";

export async function getEngagementReport() {
  const habitKeys = await redis.keys("user:*:habits");
  return {
    usersTrackingHabits: habitKeys.length,
    habitKeys,
  };
}

export async function getStageReport() {
  const keys = await redis.keys("user:*:roadmap");
  return {
    usersWithRoadmaps: keys.length,
    keys,
  };
}
