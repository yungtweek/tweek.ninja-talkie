'use client';
import { useParams } from 'next/navigation';
import { useEffect } from 'react';
import { chatSessionsStore } from '@/features/chat/chat.sessions.store';
import { useShallow } from 'zustand/react/shallow';
import MessagesPane from '@/components/chat/ChatMessagesPane';

export default function ChatPageWithSessionId() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const { selectedSessionId, setSelectedSessionId } = chatSessionsStore(
    useShallow(s => ({
      selectedSessionId: s.selectedSessionId,
      setSelectedSessionId: s.setSelectedSessionId,
    })),
  );

  useEffect(() => {
    if (typeof sessionId === 'string' && sessionId && sessionId !== selectedSessionId) {
      setSelectedSessionId(sessionId);
    }
  }, [sessionId, selectedSessionId, setSelectedSessionId]);

  return <MessagesPane />;
}
