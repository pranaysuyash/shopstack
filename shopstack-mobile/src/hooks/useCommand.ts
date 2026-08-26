import { useMutation, useQueryClient } from '@tanstack/react-query';
import { executeCommand } from '../api/command';
import type { CommandResponse } from '../api/types';

export function useCommand() {
  const qc = useQueryClient();
  return useMutation<CommandResponse, Error, string>({
    mutationFn: executeCommand,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory'] });
      qc.invalidateQueries({ queryKey: ['shopping'] });
      qc.invalidateQueries({ queryKey: ['today'] });
    },
  });
}
