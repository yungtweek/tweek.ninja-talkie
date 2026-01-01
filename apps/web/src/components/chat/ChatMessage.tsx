import { clsx } from 'clsx';
import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import rehypeSanitize from 'rehype-sanitize';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  ChatEdge,
  RagEventStatus,
  RagSearchSnapshot,
  RagSearchKey,
  RagStageKey,
  RagStagePayload,
  ToolCallsSnapshot,
  ToolEventStatus,
} from '@/features/chat/chat.types';
import { safeJsonParse } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { IconCheck, IconCopy, IconFileText, IconTool } from '@tabler/icons-react';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { Spinner } from '@/components/ui/spinner';
import { Badge } from '@/components/ui/badge';
import { ChevronDown } from 'lucide-react';

type CodeBlockProps = React.HTMLAttributes<HTMLElement> & {
  inline?: boolean;
  node?: unknown;
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

const CodeBlock = ({ className, children, node: _node, ...props }: CodeBlockProps) => {
  const match = /language-(\w+)/.exec(className ?? '');
  const raw =
    typeof children === 'string' || typeof children === 'number'
      ? String(children)
      : Array.isArray(children)
        ? children.join('')
        : '';
  const code = stripIndent(raw.replace(/\n$/, ''));
  return match ? (
    <pre className="overflow-x-auto rounded-xl p-0" style={{ paddingLeft: 0, paddingRight: 0 }}>
      <div className="border-b border-border bg-(--border-mid) px-4 py-1 opacity-70 text-muted-foreground">
        {match[1]}
      </div>
      <SyntaxHighlighter
        PreTag="div"
        style={vscDarkPlus}
        language={match[1]}
        customStyle={{ margin: 0, padding: '1.5rem 1.5rem' }}
      >
        {code}
      </SyntaxHighlighter>
    </pre>
  ) : (
    <code className={className} {...props}>
      {children}
    </code>
  );
};

export default function ChatMessage({ chat, showDots }: { chat: ChatEdge; showDots?: boolean }) {
  const { isCopied, copy } = useCopyToClipboard();

  const role = chat.node.role;
  const messageId = chat.node.id ?? chat.node.messageIndex;
  const wrapperClass =
    role === 'user'
      ? 'group ml-auto w-fit max-w-[80%] flex flex-col'
      : role === 'assistant'
        ? 'w-full max-w-[100%] mb-8'
        : role === 'system'
          ? 'w-full px-6 py-3'
          : '';
  const markdownClass =
    role === 'user'
      ? 'rounded-3xl bg-[var(--border)] px-5 py-2 prose-p:my-0'
      : role === 'assistant'
        ? '[&>:last-child]:mb-2 [&>:first-child]:mt-2'
        : '';
  const actionsClass =
    role === 'user' ? 'self-end opacity-0 transition-opacity group-hover:opacity-100' : '';

  const citations =
    safeJsonParse<{
      citations?: Array<{
        title?: string;
        snippet?: string;
        file_name?: string;
        source_id?: string;
        rerank_score?: number;
      }>;
    }>(chat.node.sourcesJson, { citations: [] }).citations ?? [];

  const ragSearch = useMemo(() => {
    const parsed = safeJsonParse<RagSearchSnapshot | Record<string, unknown>>(
      chat.node.ragSearchJson,
      {},
    );
    const normalized: RagSearchSnapshot = {
      wrapper: {},
      stages: {},
    };
    if (parsed && ('wrapper' in parsed || 'stages' in parsed)) {
      if (parsed.wrapper) {
        normalized.wrapper = { ...parsed.wrapper };
      }
      if (parsed.stages) {
        normalized.stages = { ...parsed.stages };
      }
    }

    if (chat.node.ragSearch) {
      if ('meta' in chat.node.ragSearch) {
        const { meta, payload } = chat.node.ragSearch;
        if (meta.scope === 'wrapper') {
          const target = normalized.wrapper?.searchCall ?? { inProgress: null, completed: null };
          if (meta.status === 'in_progress' && !target.inProgress) {
            target.inProgress = payload ?? null;
          }
          if (meta.status === 'completed' && !target.completed) {
            target.completed = payload ?? null;
          }
          normalized.wrapper = { ...(normalized.wrapper ?? {}), searchCall: target };
        } else {
          const target = normalized.stages?.[meta.key] ?? { inProgress: null, completed: null };
          if (meta.status === 'in_progress' && !target.inProgress) {
            target.inProgress = payload ?? null;
          }
          if (meta.status === 'completed' && !target.completed) {
            target.completed = payload ?? null;
          }
          normalized.stages = { ...(normalized.stages ?? {}), [meta.key]: target };
        }
      }
    }

    const hasStage =
      Boolean(
        normalized.wrapper?.searchCall?.inProgress || normalized.wrapper?.searchCall?.completed,
      ) ||
      Boolean(
        normalized.stages &&
          Object.values(normalized.stages).some(stage => stage?.inProgress || stage?.completed),
      );
    return hasStage ? normalized : null;
  }, [chat.node.ragSearch, chat.node.ragSearchJson]);

  const toolCalls = useMemo(() => {
    const parsed = safeJsonParse<ToolCallsSnapshot | Record<string, unknown>>(
      chat.node.toolCallsJson,
      {},
    );
    const normalized: ToolCallsSnapshot = {
      order: [],
      calls: {},
    };
    if (parsed && typeof parsed === 'object') {
      const order = (parsed as ToolCallsSnapshot).order;
      if (Array.isArray(order)) {
        normalized.order = [...order];
      }
      const calls = (parsed as ToolCallsSnapshot).calls;
      if (calls && typeof calls === 'object') {
        normalized.calls = { ...calls };
      }
    }

    const hasCalls = Boolean(normalized.order && normalized.order.length > 0);
    return hasCalls ? normalized : null;
  }, [chat.node.toolCallsJson]);

  const stageLabels: Record<RagSearchKey, string> = {
    searchCall: 'Search Call',
    retrieve: 'Retrieve',
    rerank: 'Rerank',
    mmr: 'MMR',
    compress: 'Compress',
  };
  const detailStageOrder: RagStageKey[] = ['retrieve', 'rerank', 'mmr', 'compress'];

  const ragStages = useMemo(() => {
    if (!ragSearch) return [];
    const entries: Array<{
      key: RagStageKey;
      label: string;
      status: RagEventStatus;
      payload: RagStagePayload | null;
    }> = [];
    for (const key of detailStageOrder) {
      const snapshot = ragSearch.stages?.[key];
      if (!snapshot?.completed) continue;
      entries.push({
        key,
        label: stageLabels[key],
        status: 'completed',
        payload: snapshot.completed ?? null,
      });
    }
    return entries;
  }, [ragSearch]);

  const toolCallEntries = useMemo(() => {
    if (!toolCalls) return [];
    const entries: Array<{
      callId: string;
      tool: string;
      status: ToolEventStatus;
      attempt?: number;
      tookMs?: number | null;
      argsPreview?: string | null;
      resultPreview?: string | null;
    }> = [];
    for (const callId of toolCalls.order ?? []) {
      const entry = toolCalls.calls?.[callId];
      if (!entry) continue;
      const status = entry.completed ? 'completed' : 'in_progress';
      const payload = entry.completed ?? entry.inProgress ?? {};
      entries.push({
        callId,
        tool: entry.tool ?? payload.tool ?? callId,
        status,
        attempt: entry.attempt ?? payload.attempt,
        tookMs: payload.tookMs ?? null,
        argsPreview: entry.inProgress?.argsPreview ?? entry.completed?.argsPreview ?? null,
        resultPreview: entry.completed?.resultPreview ?? null,
      });
    }
    return entries;
  }, [toolCalls]);

  const formatStageMetrics = (
    payload?: RagStagePayload | null,
    options?: { useSeconds?: boolean },
  ) => {
    if (!payload) return '';
    const useSeconds = options?.useSeconds ?? false;
    const parts: string[] = [];
    if (typeof payload.inputHits === 'number' && typeof payload.outputHits === 'number') {
      parts.push(`${payload.inputHits}->${payload.outputHits} hits`);
    } else if (typeof payload.outputHits === 'number') {
      parts.push(`${payload.outputHits} hits`);
    } else if (typeof payload.hits === 'number') {
      parts.push(`${payload.hits} hits`);
    }
    if (typeof payload.tookMs === 'number') {
      if (useSeconds) {
        parts.push(`${(payload.tookMs / 1000).toFixed(2)}s`);
      } else {
        parts.push(`${payload.tookMs}ms`);
      }
    }
    return parts.length ? parts.join(' · ') : '';
  };

  const summaryState = useMemo(() => {
    if (!ragSearch) return null;
    const searchCall = ragSearch.wrapper?.searchCall;
    if (searchCall?.completed) {
      return {
        key: 'searchCall' as RagSearchKey,
        status: 'completed' as RagEventStatus,
        payload: searchCall.completed ?? searchCall.inProgress ?? null,
      };
    }
    for (const key of detailStageOrder) {
      const snapshot = ragSearch.stages?.[key];
      if (snapshot?.inProgress && !snapshot?.completed) {
        return {
          key,
          status: 'in_progress' as RagEventStatus,
          payload: snapshot.inProgress ?? null,
        };
      }
    }
    if (searchCall?.inProgress) {
      return {
        key: 'searchCall' as RagSearchKey,
        status: 'in_progress' as RagEventStatus,
        payload: searchCall.inProgress ?? null,
      };
    }
    return null;
  }, [ragSearch]);

  const toolSummaryStatus = useMemo(() => {
    if (!toolCallEntries.length) return null;
    const hasInProgress = toolCallEntries.some(entry => entry.status === 'in_progress');
    return (hasInProgress ? 'in_progress' : 'completed') as ToolEventStatus;
  }, [toolCallEntries]);

  const summaryPayload = summaryState?.payload ?? null;
  const summaryStatus = summaryState?.status ?? null;
  const isRagSearchActive = summaryStatus === 'in_progress';
  const summaryMetrics = formatStageMetrics(summaryPayload, { useSeconds: true });
  const statusBadgeClass =
    summaryStatus === 'completed'
      ? 'text-[color:var(--ok-fg)] bg-[color:var(--ok-bg)] border-[color:var(--ok-bg)]'
      : '';
  const statusTextClass = summaryStatus === 'in_progress' ? 'animate-pulse' : '';
  const toolBadgeClass =
    toolSummaryStatus === 'completed'
      ? 'text-[color:var(--ok-fg)] bg-[color:var(--ok-bg)] border-[color:var(--ok-bg)]'
      : '';
  const toolStatusTextClass = toolSummaryStatus === 'in_progress' ? 'animate-pulse' : '';

  const groupedCitations = useMemo(() => {
    const groups = new Map<string, typeof citations>();
    for (const c of citations) {
      const key = c.file_name || c.title || 'Untitled source';
      const arr = groups.get(key) ?? [];
      arr.push(c);
      groups.set(key, arr);
    }

    // sort by rerank_score desc within each file (if present)
    for (const [k, arr] of groups.entries()) {
      arr.sort((a, b) => (b.rerank_score ?? -Infinity) - (a.rerank_score ?? -Infinity));
      groups.set(k, arr);
    }

    // stable ordering: files by top rerank_score desc
    const entries = Array.from(groups.entries()).map(([file, items]) => {
      const top = items.length ? (items[0].rerank_score ?? -Infinity) : -Infinity;
      return { file, items, top };
    });
    entries.sort((a, b) => b.top - a.top);
    return entries;
  }, [citations]);

  return (
    <>
      <div
        className={clsx(wrapperClass, 'prose')}
        role={chat.node.role}
        data-role={chat.node.role}
        data-message-id={messageId ?? undefined}
      >
        {summaryStatus && (
          <div className="mb-2 text-xs text-muted-foreground">
            <Collapsible defaultOpen={false} className="group/collapsible">
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center cursor-pointer gap-2 text-xs text-muted-foreground my-2"
                >
                  {summaryState?.key === 'searchCall' && summaryStatus === 'completed' ? (
                    <IconFileText className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Spinner />
                  )}
                  <span className="font-medium">RAG Search</span>
                  {summaryStatus ? (
                    <>
                      <span className="text-muted-foreground">·</span>
                      <Badge variant="outline" className={`font-medium ${statusBadgeClass}`}>
                        <span className={statusTextClass}>
                          {summaryState?.key && summaryState.key !== 'searchCall'
                            ? `${stageLabels[summaryState.key]} in progress`
                            : summaryStatus === 'completed'
                              ? 'completed'
                              : 'in progress'}
                        </span>
                      </Badge>
                      {summaryMetrics ? (
                        <span className="text-muted-foreground">· {summaryMetrics}</span>
                      ) : null}
                    </>
                  ) : null}
                  {ragStages.length > 0 ? (
                    <ChevronDown className="w-4 h-4 ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-180" />
                  ) : null}
                </button>
              </CollapsibleTrigger>
              {ragStages.length > 0 ? (
                <CollapsibleContent className="mt-2">
                  <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                    <div className="font-medium text-foreground/70">RAG Search</div>
                    <div className="mt-2 space-y-2">
                      {ragStages.map(stage => {
                        const statusLabel =
                          stage.status === 'completed' ? 'completed' : 'in progress';
                        const dotClass =
                          stage.status === 'completed'
                            ? 'bg-foreground/60'
                            : 'bg-muted-foreground/60';
                        const metrics = formatStageMetrics(stage.payload);
                        return (
                          <div key={stage.key} className="flex items-center gap-2">
                            <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
                            <span>
                              {stage.label} · {statusLabel}
                              {metrics ? ` · ${metrics}` : ''}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </CollapsibleContent>
              ) : null}
            </Collapsible>
          </div>
        )}
        {toolCallEntries.length > 0 && (
          <div className="mb-2 text-xs text-muted-foreground">
            <Collapsible defaultOpen={false} className="group/collapsible">
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center cursor-pointer gap-2 text-xs text-muted-foreground my-2"
                >
                  <IconTool className="w-4 h-4" />
                  <span className="font-medium">Tool calls</span>
                  {toolSummaryStatus ? (
                    <>
                      <span className="text-muted-foreground">·</span>
                      <Badge variant="outline" className={`font-medium ${toolBadgeClass}`}>
                        <span className={toolStatusTextClass}>
                          {toolSummaryStatus === 'in_progress' ? 'in progress' : 'completed'}
                        </span>
                      </Badge>
                    </>
                  ) : null}
                  <span className="text-muted-foreground">· {toolCallEntries.length}</span>
                  <ChevronDown className="w-4 h-4 ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-180" />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2">
                <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                  <div className="font-medium text-foreground/70">Tool calls</div>
                  <div className="mt-2 space-y-2">
                    {toolCallEntries.map(entry => {
                      const statusLabel =
                        entry.status === 'completed' ? 'completed' : 'in progress';
                      const dotClass =
                        entry.status === 'completed'
                          ? 'bg-foreground/60'
                          : 'bg-muted-foreground/60';
                      const metaParts = [
                        statusLabel,
                        entry.attempt ? `attempt ${entry.attempt}` : null,
                        typeof entry.tookMs === 'number' ? `${entry.tookMs}ms` : null,
                      ].filter(Boolean);
                      return (
                        <div key={entry.callId} className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
                            <span>
                              {entry.tool}
                              {metaParts.length ? ` · ${metaParts.join(' · ')}` : ''}
                            </span>
                          </div>
                          {entry.argsPreview ? (
                            <div className="rounded-md bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground">
                              args: {entry.argsPreview}
                            </div>
                          ) : null}
                          {entry.resultPreview ? (
                            <div className="rounded-md bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground">
                              result: {entry.resultPreview}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}
        {showDots && !isRagSearchActive && (
          <div className="mt-0 inline-flex gap-1">
            <span className="inline-block animate-bounce" style={{ animationDelay: '0ms' }}>
              .
            </span>
            <span className="inline-block animate-bounce" style={{ animationDelay: '200ms' }}>
              .
            </span>
            <span className="inline-block animate-bounce" style={{ animationDelay: '400ms' }}>
              .
            </span>
          </div>
        )}
        <div className={markdownClass}>
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
        </div>
        {chat.node.streamDone !== false && (
          <div
            className={clsx('flex items-center gap-2 text-xs text-muted-foreground', actionsClass)}
          >
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => {
                void copy(chat.node.content);
              }}
              aria-label={isCopied ? 'Copied' : 'Copy message'}
            >
              {isCopied ? <IconCheck /> : <IconCopy />}
            </Button>
            {citations.length > 0 && (
              <Popover>
                <PopoverTrigger asChild>
                  <Button type="button" variant="secondary" size="sm" className="text-xs">
                    <span>Sources</span>
                    <span>
                      {groupedCitations.length} file{groupedCitations.length === 1 ? '' : 's'} ·{' '}
                      {citations.length} passage{citations.length === 1 ? '' : 's'}
                    </span>
                  </Button>
                </PopoverTrigger>

                <PopoverContent align="start" className="w-xl max-w-[90vw] p-0">
                  <div className="border-b border-border px-4 py-3">
                    <div className="text-sm font-semibold">Sources</div>
                    <div className="text-xs text-muted-foreground">
                      {groupedCitations.length} file{groupedCitations.length === 1 ? '' : 's'} ·{' '}
                      {citations.length} passage{citations.length === 1 ? '' : 's'}
                    </div>
                  </div>

                  <div className="max-h-96 overflow-auto px-4 py-3">
                    <div className="space-y-3">
                      {groupedCitations.map(({ file, items }) => (
                        <div key={file}>
                          <div className="mb-2 flex items-center justify-between gap-3">
                            <div className="min-w-0 truncate text-sm font-semibold">{file}</div>
                            <div className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                              {items.length} passage{items.length === 1 ? '' : 's'}
                            </div>
                          </div>

                          <div className="space-y-3">
                            {items.map((c, i) => (
                              <div key={c.source_id ?? `${file}-${i}`} className="text-sm">
                                <div className="mb-1 flex items-center justify-between gap-3">
                                  <div className="min-w-0 truncate text-xs text-muted-foreground">
                                    {c.source_id ?? `#${i + 1}`}
                                  </div>
                                  {typeof c.rerank_score === 'number' && (
                                    <div className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                                      {c.rerank_score.toFixed(2)}
                                    </div>
                                  )}
                                </div>

                                {c.snippet ? (
                                  <div className="rounded-md bg-muted/40 p-2 text-sm text-muted-foreground">
                                    <div className="whitespace-pre-wrap line-clamp-6">
                                      {c.snippet}
                                    </div>
                                  </div>
                                ) : (
                                  <div className="text-xs text-muted-foreground">(no snippet)</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </PopoverContent>
              </Popover>
            )}
          </div>
        )}
      </div>
    </>
  );
}
