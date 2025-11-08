'use client';
import { useSessionsActions } from '@/features/chat/chat.sessions.store';
import { useEffect } from 'react';
import { chatSessionsStore } from '@/features/chat/chat.sessions.store';
import MessagesPane from '@/components/chat/ChatMessagesPane';

export default function ChatPage() {
  const { setSelectedSessionId, setActiveSessionId } = useSessionsActions();
  const selected = chatSessionsStore.getState().selectedSessionId; // 가드용

  useEffect(() => {
    if (selected !== null) setSelectedSessionId(null); // UI 선택만 해제
    setActiveSessionId(null); // 새 전송 → 새 세션 생성 유도
  }, [selected, setSelectedSessionId, setActiveSessionId]);

  return <MessagesPane />;
}
