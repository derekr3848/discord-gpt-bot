import { memory } from '../../memory';
import { UserRoadmap } from '../../utils/types';
import { nowISO } from '../../utils/time';

export async function setStage(userId: string, stageId: string): Promise<UserRoadmap | null> {
  const roadmap = await memory.getRoadmap(userId);
  if (!roadmap) return null;

  const exists = roadmap.stages.find((s: any) => s.id === stageId);
  if (!exists) return null;

  roadmap.currentStageId = stageId;

  roadmap.stages = roadmap.stages.map((s: any) =>
    s.id === stageId
      ? { ...s, status: "active" }
      : s.status === "active"
      ? { ...s, status: "completed" }
      : s
  );

  roadmap.lastUpdated = nowISO();
  await memory.setRoadmap(userId, roadmap);

  return roadmap;
}


export async function markTaskCompleted(
  userId: string,
  stageId: string,
  task: string
): Promise<UserRoadmap | null> {
  const roadmap = await memory.getRoadmap(userId);
  if (!roadmap) return null;
  const stage = roadmap.stages.find((s) => s.id === stageId);
  if (!stage) return null;
  // Minimal implementation: just remove task from list
  stage.tasks = stage.tasks.filter((t) => t !== task);
  roadmap.lastUpdated = nowISO();
  await memory.setRoadmap(userId, roadmap);
  return roadmap;
}

