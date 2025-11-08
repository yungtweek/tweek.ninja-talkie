// components/ChatModeToggle.tsx
'use client';

import styles from './ChatModeToggle.module.scss';
import { clsx } from 'clsx';
import { useChatActions } from '@/features/chat/chat.store';

interface ChatToggleModuleProps {
  sessionId: string | null;
}

export default function ChatModeToggle({ sessionId }: ChatToggleModuleProps) {
  const { getRag, toggleRag } = useChatActions();
  const rag = getRag(sessionId);
  return (
    <div className={styles.container}>
      <div className={styles.segmented}>
        <button
          type="button"
          onClick={() => toggleRag(sessionId)}
          className={clsx(styles.segBtn, !rag && styles.active)}
        >
          GEN
        </button>
        <button
          type="button"
          onClick={() => toggleRag(sessionId)}
          className={clsx(styles.segBtn, rag && styles.active)}
        >
          RAG
        </button>
      </div>
      <span className={styles.hint}>
        {rag
          ? 'Answer with your documents and the model'
          : 'Answer with only the model’s knowledge'}
      </span>
    </div>
  );
}
