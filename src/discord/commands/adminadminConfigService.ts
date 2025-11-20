import { redis } from "../../memory/redisClient";

export async function setGlobalConfig(key: string, value: any) {
  await redis.set(`config:${key}`, JSON.stringify(value));
  return true;
}
