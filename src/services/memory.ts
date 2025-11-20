import { redis } from "../memory/redisClient";
import {
  UserProfile,
  UserRoadmap,
  UserHabits,
  PushModeState,
  MindsetState,
  OfferModel
} from '../utils/types';

async function getJson<T>(key: string): Promise<T | null> {
  const raw = await redis.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function setJson(key: string, value: any): Promise<void> {
  await redis.set(key, JSON.stringify(value));
}

export const memory = {
  // user profile
  async getProfile(userId: string): Promise<UserProfile | null> {
    return getJson<UserProfile>(`user:${userId}:profile`);
  },
  async setProfile(userId: string, profile: UserProfile): Promise<void> {
    await setJson(`user:${userId}:profile`, profile);
  },

  // roadmap
  async getRoadmap(userId: string): Promise<UserRoadmap | null> {
    return getJson<UserRoadmap>(`user:${userId}:roadmap`);
  },
  async setRoadmap(userId: string, roadmap: UserRoadmap): Promise<void> {
    await setJson(`user:${userId}:roadmap`, roadmap);
  },

  // habits
  async getHabits(userId: string): Promise<UserHabits | null> {
    return getJson<UserHabits>(`user:${userId}:habits`);
  },
  async setHabits(userId: string, habits: UserHabits): Promise<void> {
    await setJson(`user:${userId}:habits`, habits);
  },
  async logHabitCompletion(userId: string, habitId: string, dateISO: string): Promise<void> {
    const key = `user:${userId}:habit_logs:${habitId}`;
    await redis.sadd(key, dateISO);
  },

  // push mode
  async getPushMode(userId: string): Promise<PushModeState | null> {
    return getJson<PushModeState>(`user:${userId}:pushmode`);
  },
  async setPushMode(userId: string, state: PushModeState): Promise<void> {
    await setJson(`user:${userId}:pushmode`, state);
  },

  // mindset
  async getMindset(userId: string): Promise<MindsetState | null> {
    return getJson<MindsetState>(`user:${userId}:mindset`);
  },
  async setMindset(userId: string, state: MindsetState): Promise<void> {
    await setJson(`user:${userId}:mindset`, state);
  },

  // offer
  async getOffer(userId: string): Promise<OfferModel | null> {
    return getJson<OfferModel>(`user:${userId}:offer`);
  },
  async setOffer(userId: string, offer: OfferModel): Promise<void> {
    await setJson(`user:${userId}:offer`, offer);
  },

  // history (very simple: append last N messages)
  async appendHistory(userId: string, role: 'user' | 'assistant', content: string) {
    const key = `user:${userId}:history`;
    const entry = { role, content, ts: new Date().toISOString() };
    await redis.lpush(key, JSON.stringify(entry));
    await redis.ltrim(key, 0, 50); // keep last 50
  },

  // generic (for admin)
  async getRaw(key: string): Promise<string | null> {
    return redis.get(key);
  },
  async setRaw(key: string, value: string): Promise<void> {
    await redis.set(key, value);
  },
  async del(key: string): Promise<void> {
    await redis.del(key);
  }
};
