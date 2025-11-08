export type Role = 'user' | 'assistant' | 'system';

export interface ChatEdge {
  cursor?: string | null;
  node: ChatNode;
}

export interface ChatNode {
  id?: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  messageIndex?: number | null;
  turn?: number | null;
  sourcesJson?: string | null;
  jobId?: string | null;
}
