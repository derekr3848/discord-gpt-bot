// **src/memory/index.ts**
import { redis } from "./redisClient";

// ---------- RAW HELPERS ----------
export async function setRaw(key: string, value: string) {
  return redis.set(key, value);
}

export async function getRaw(key: string): Promise<string | null> {
  return redis.get(key);
}

export async function del(key: string) {
  return redis.del(key);
}

// ---------- PROFILE ----------
export async function getProfile(userId: string) {
  const raw = await getRaw(`user:${userId}:profile`);
  return raw ? JSON.parse(raw) : null;
}

export async function setProfile(userId: string, profile: any) {
  return setRaw(`user:${userId}:profile`, JSON.stringify(profile));
}

// ---------- ROADMAP ----------
export async function getRoadmap(userId: string) {
  const raw = await getRaw(`user:${userId}:roadmap`);
  return raw ? JSON.parse(raw) : null;
}

export async function setRoadmap(userId: string, roadmap: any) {
  return setRaw(`user:${userId}:roadmap`, JSON.stringify(roadmap));
}

// ---------- OFFER ----------
export async function getOffer(userId: string) {
  const raw = await getRaw(`user:${userId}:offer`);
  return raw ? JSON.parse(raw) : null;
}

export async function setOffer(userId: string, offer: any) {
  return setRaw(`user:${userId}:offer`, JSON.stringify(offer));
}

// ---------- HABITS ----------
export async function getHabits(userId: string) {
  const raw = await getRaw(`user:${userId}:habits`);
  return raw ? JSON.parse(raw) : null;
}

export async function setHabits(userId: string, habits: any) {
  return setRaw(`user:${userId}:habits`, JSON.stringify(habits));
}

export async function logHabitCompletion(userId: string, habitId: string, date: string) {
  return redis.sAdd(`user:${userId}:habit_logs:${habitId}`, date);
}

// ---------- MINDSET ----------
export async function getMindset(userId: string) {
  const raw = await getRaw(`user:${userId}:mindset`);
  return raw ? JSON.parse(raw) : null;
}

export async function setMindset(userId: string, data: any) {
  return setRaw(`user:${userId}:mindset`, JSON.stringify(data));
}

// ---------- PUSH MODE ----------
export async function getPushMode(userId: string) {
  const raw = await getRaw(`user:${userId}:push_mode`);
  return raw ? JSON.parse(raw) : null;
}

export async function setPushMode(userId: string, state: any) {
  return setRaw(`user:${userId}:push_mode`, JSON.stringify(state));
}

// ---------- EXPORT SINGLE OBJECT ----------
export const memory = {
  setRaw,
  getRaw,
  del,

  getProfile,
  setProfile,

  getRoadmap,
  setRoadmap,

  getOffer,
  setOffer,

  getHabits,
  setHabits,
  logHabitCompletion,

  getMindset,
  setMindset,

  getPushMode,
  setPushMode,
};
