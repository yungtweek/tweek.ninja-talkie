// Apollo normalized cache helpers
import { Reference } from '@apollo/client';
import { StoreObject } from '@apollo/client/utilities';

// Apollo cache field shape for a relay-style connection (normalized refs)
type EdgeRef = { __ref: string };
type EdgeNode = { __typename?: string; node?: Reference };

export const isRef = (v: unknown): v is Reference =>
  typeof v === 'object' && v !== null && '__ref' in (v as any);
export const isStore = (v: unknown): v is StoreObject =>
  typeof v === 'object' && v !== null && !('__ref' in (v as any));
