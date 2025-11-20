import { redis } from "../../memory/redisClient";

export async function setConfig(key: string, value: any) {
  await redis.json.set(`config:${key}`, "$", value);
  return true;
}

export async function getConfig(key: string) {
  return await redis.json.get(`config:${key}`);
}
