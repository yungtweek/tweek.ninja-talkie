'use client';
import styles from './SessionList.module.scss';

import React, { useEffect, useState } from 'react';
import { clsx } from 'clsx';
import { usePathname, useRouter } from 'next/navigation';
import { chatSessionsStore, useSessionsActions } from '@/features/chat/chat.sessions.store';
import { useMutation, useQuery } from '@apollo/client/react';
import {
  ChatSessionListDocument,
  ChatSessionListQuery,
  ChatSessionListQueryVariables,
  DeleteSessionDocument,
  DeleteSessionMutation,
  DeleteSessionMutationVariables,
} from '@/gql/graphql';
import { useChatActions } from '@/features/chat/chat.store';
import Link from 'next/link';

export default function SessionList() {
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const { reset } = useChatActions();
  const { data } = useQuery<ChatSessionListQuery, ChatSessionListQueryVariables>(
    ChatSessionListDocument,
    {
      variables: { first: 50 },
      fetchPolicy: 'cache-and-network',
      notifyOnNetworkStatusChange: true,
    },
  );
  const [mutateDeleteSession] = useMutation<DeleteSessionMutation, DeleteSessionMutationVariables>(
    DeleteSessionDocument,
  );

  const { selectedSessionId, setSelectedSessionId } = useSessionsActions();
  const router = useRouter();
  const pathname = usePathname();

  const deleteSession = async (sessionId: string) => {
    try {
      await mutateDeleteSession({
        variables: { sessionId },
        optimisticResponse: {
          deleteChatSession: {
            __typename: 'DeleteChatSessionResult',
            ok: true,
            sessionId: 'optimistic',
            status: 'deleting',
          },
        },
        refetchQueries: [{ query: ChatSessionListDocument }],
        awaitRefetchQueries: true,
      });
    } catch (e) {
      console.error('delete session  mutation failed', e);
      alert('세션 삭제 요청에 실패했습니다.');
    }
  };

  useEffect(() => {
    setHoverId(null);
    setOpenId(null);
  }, [data?.chatSessionList.edges]);

  return (
    <div className={styles.list_wrapper}>
      <ul className={styles.list}>
        <li className={styles.list_item}>
          <Link
            href={'/chat'}
            onClick={() => {
              setSelectedSessionId(null);
            }}
            title={'New Chat'}
            className={pathname === '/chat' ? styles.selected : ''}
          >
            New Chat
          </Link>
        </li>
        <li className={styles.list_item}>
          <Link
            href={'/documents'}
            onClick={() => {
              setSelectedSessionId(null);
            }}
            title={'Documents'}
            className={pathname === '/documents' ? styles.selected : ''}
          >
            Documents
          </Link>
        </li>
      </ul>
      <h3>Chats 💬</h3>
      <ul className={clsx(styles.list, styles.session)}>
        {data?.chatSessionList.edges.map(edge => (
          <li
            key={edge.node.id}
            className={clsx(styles.list_item)}
            onMouseEnter={() => setHoverId(edge.node.id)}
            onMouseLeave={() => {
              setHoverId(null);
              setOpenId(null);
            }}
          >
            <Link
              href={`/chat/${edge.node.id}`}
              className={clsx([selectedSessionId === edge.node.id ? styles.selected : ''])}
              onClick={() => {
                if (selectedSessionId === edge.node.id) return;
                setSelectedSessionId(edge.node.id);
                chatSessionsStore.getState().setActiveSessionId(edge.node.id);
                // router.push(`/chat/${edge.node.id}`);
              }}
              title={edge.node.title?.replace(/^"|"$/g, '')}
            >
              {edge.node.title?.replace(/"/g, '') ?? (
                <>
                  <div className={styles.typingDots}>
                    <span>.</span>
                    <span>.</span>
                    <span>.</span>
                  </div>
                </>
              )}
            </Link>

            {hoverId === edge.node.id && (
              <button
                className={styles.moreBtn}
                onClick={() => {
                  setOpenId(edge.node.id);
                }}
              >
                ⋯
              </button>
            )}

            {openId === edge.node.id && (
              <div className={styles.moreMenu}>
                <button
                  className={styles.deleteBtn}
                  onClick={() => {
                    const wasCurrent = selectedSessionId === edge.node.id;
                    void deleteSession(edge.node.id);
                    if (wasCurrent) {
                      reset();
                      router.push('/');
                    }
                  }}
                >
                  Delete
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
