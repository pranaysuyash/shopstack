import { api } from './client';
import type { CommandRequest, CommandResponse } from './types';

export async function executeCommand(text: string): Promise<CommandResponse> {
  return api.post<CommandResponse>('/api/v1/command/execute', { text });
}
