import { memory } from "../../memory";

import { Habit, UserHabits } from '../../utils/types';
import { nowISO } from '../../utils/time';
import { v4 as uuid } from 'uuid';
import { redis } from '../../memory/redisClient';

export async function addHabit(
  userId: string,
  description: string,
  frequency: 'daily' | 'weekly' | 'custom' = 'daily'
): Promise<Habit> {


  const habitsState = (await memory.getHabits(userId)) || { userId, habits: [] };
  const habit: Habit = {
    id: uuid(),
    description,
    frequency,
    createdAt: nowISO(),
    updatedAt: nowISO()
  };
  habitsState.habits.push(habit);
  await memory.setHabits(userId, habitsState);
  return habit;
}

export async function getUserHabits(userId: string): Promise<UserHabits> {
  return (await memory.getHabits(userId)) || { userId, habits: [] };
}

export async function completeHabit(userId: string, habitId: string): Promise<void> {
  const date = nowISO().split('T')[0];
  await memory.logHabitCompletion(userId, habitId, date);
  const habitsState = await memory.getHabits(userId);
  if (habitsState) {
    const habit = habitsState.habits.find((h: Habit) => h.id === habitId);
    if (habit) {
      habit.updatedAt = nowISO();
      await memory.setHabits(userId, habitsState);
    }
  }
}

export async function getHabitStats(userId: string): Promise<Record<string, number>> {
  const habitsState = await memory.getHabits(userId);
  if (!habitsState) return {};
  const stats: Record<string, number> = {};

  for (const habit of habitsState.habits) {
    const key = `user:${userId}:habit_logs:${habit.id}`;
    const count = await redis.scard(key);
    stats[habit.id] = count;
  }

  return stats;
}
