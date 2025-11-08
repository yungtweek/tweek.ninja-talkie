'use client';
import React, { useRef, useState } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import { clsx } from 'clsx';
import styles from './ChatSession.module.scss';
import ChatModeToggle from '@/components/chat/ChatModeToggle';
import { useChatUI } from '@/providers/ChatProvider';
import { useSessionsState } from '@/features/chat/chat.sessions.store';
import { useChatSessionStream } from '@/features/chat/useChatSessionStream';
import { useChatState } from '@/features/chat/chat.store';

export default function ChatComposer() {
  const { selectedSessionId } = useSessionsState();
  const { submitAction, loading } = useChatSessionStream(selectedSessionId);
  const [userInput, setUserInput] = useState('');
  const formRef = useRef<HTMLFormElement | null>(null);
  const { setAwaitingFirstToken } = useChatUI();
  const { busy } = useChatState();

  const isComposing = useRef(false);

  const buttonDisabled = () => !userInput || busy || loading;

  return (
    <form
      ref={formRef}
      className={styles.form}
      action={submitAction}
      onSubmit={() => {
        setAwaitingFirstToken(true);
        setTimeout(() => setUserInput(''), 0);
      }}
    >
      <ChatModeToggle sessionId={selectedSessionId} />
      <div className={clsx(styles.wrap)}>
        <TextareaAutosize
          id="chat-input"
          name="text"
          value={userInput}
          rows={1}
          onChange={e => setUserInput(e.target.value)}
          placeholder="Ask me anything!"
          onCompositionStart={() => {
            isComposing.current = true;
          }}
          onCompositionEnd={e => {
            isComposing.current = false;
          }}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              if (isComposing.current) {
                return;
              }
              e.preventDefault();
              if (!buttonDisabled()) {
                formRef.current?.requestSubmit();
              }
            }
          }}
        />
        <button type="submit" disabled={buttonDisabled()} className={styles.button}>
          {busy ? 'Loading...' : 'SUBMIT'}
        </button>
      </div>
    </form>
  );
}
