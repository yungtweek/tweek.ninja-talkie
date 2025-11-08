import { clsx } from 'clsx';
import styles from '@/components/chat/ChatSession.module.scss';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import rehypeSanitize from 'rehype-sanitize';
import React from 'react';
import { ChatEdge } from '@/features/chat/chat.types';

export default function ChatMessage({ chat, showDots }: { chat: ChatEdge; showDots?: boolean }) {
  return (
    <li className={clsx(styles[chat.node.role], styles.article)} role={chat.node.role}>
      {showDots && (
        <div className={styles.typingDots}>
          <span>.</span>
          <span>.</span>
          <span>.</span>
        </div>
      )}
      <ReactMarkdown
        remarkPlugins={[remarkBreaks]}
        rehypePlugins={[rehypeSanitize]}
        components={{ br: () => <br /> }}
      >
        {chat.node.content}
      </ReactMarkdown>
    </li>
  );
}
