import { memory } from '../memory';
import { PushModeState } from '../../utils/types';
import { nowISO } from '../../utils/time';

export async function setPushModeState(
  userId: string,
  enabled: boolean,
  level: 'normal' | 'strong' | 'extreme'
): Promise<PushModeState> {
  const state: PushModeState = {
    enabled,
    level,
    lastUpdated: nowISO()
  };
  await memory.setPushMode(userId, state);
  return state;
}

