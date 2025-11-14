import { clsx } from 'clsx';
import styles from '@/components/chat/ChatSession.module.scss';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import rehypeSanitize from 'rehype-sanitize';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import React from 'react';
import { ChatEdge } from '@/features/chat/chat.types';

export default function ChatMessage({ chat, showDots }: { chat: ChatEdge; showDots?: boolean }) {
  const CodeBlock = ({ className, children, node, ...props }: any) => {
    const match = /language-(\w+)/.exec(className || '');
    const raw = String(children).replace(/\n$/, '');
    const code = stripIndent(raw);
    return match ? (
      <pre className={styles.codeBlock}>
        <div className={styles.codeLabel}>{match[1]}</div>
        <SyntaxHighlighter
          PreTag="div"
          style={vscDarkPlus} // 🎨 theme based on isDark
          language={match[1]}
          customStyle={{ margin: 0, padding: '1.5rem 1.5rem' }}
          {...props}
        >
          {code}
        </SyntaxHighlighter>
      </pre>
    ) : (
      <code className={match} {...props}>
        {children}
      </code>
    );
  };

  function stripIndent(input: string) {
    const s = input.replace(/^\n/, '').replace(/\s+$/, '');
    const lines = s.split('\n');
    const indents = lines
      .filter(l => l.trim().length > 0)
      .map(l => l.match(/^(\s*)/)?.[1].length ?? 0);
    const min = indents.length ? Math.min(...indents) : 0;
    return lines.map(l => l.slice(min)).join('\n');
  }

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
        components={{
          br: () => <br />,
          pre({ children }) {
            return <>{children}</>; // 바깥 pre 제거
          },
          code(CodeProps) {
            return <CodeBlock {...CodeProps} />;
          },
        }}
      >
        {chat.node.content}
      </ReactMarkdown>
    </li>
  );
}
