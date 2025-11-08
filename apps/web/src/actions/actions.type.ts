export type ActionState<T, M extends Record<string, unknown> = Record<string, unknown>> =
  | { success: true; data: T; error: null; meta?: M }
  | { success: false; data: null; error: { message: string; code?: string }; meta?: M };

export const ok = <T, M extends Record<string, unknown> = Record<string, unknown>>(
  data: T,
  meta?: M,
): ActionState<T, M> => ({ success: true, data, error: null, meta });

export const fail = <T = never, M extends Record<string, unknown> = Record<string, unknown>>(
  message: string,
  options?: { code?: string; meta?: M },
): ActionState<T, M> => ({
  success: false,
  data: null,
  error: { message, code: options?.code },
  meta: options?.meta,
});

export const isSuccess = <T, M extends Record<string, unknown>>(
  s: ActionState<T, M>,
): s is { success: true; data: T; error: null; meta?: M } => s.success;
