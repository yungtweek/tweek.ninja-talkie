import { ChatResolver } from './chat.resolver';

describe('ChatResolver.messages (unit)', () => {
  it('serializes citationsJson when present', async () => {
    const chatRepo = {
      listMessagesBySession: jest.fn().mockResolvedValue([
        {
          id: 'm1',
          role: 'assistant',
          content: 'hello',
          turn: 1,
          messageIndex: 2,
          sourcesJson: { foo: 'bar' },
          citationsJson: [{ sourceId: 'S1', fileName: 'doc.md' }],
          toolCallsJson: { order: ['call-1'] },
        },
      ]),
    } as any;

    const resolver = new ChatResolver(chatRepo);
    const res = await resolver.messages({ id: 's1' } as any, 50, undefined);

    expect(res.edges).toHaveLength(1);
    expect(res.edges[0].node.sourcesJson).toBe(JSON.stringify({ foo: 'bar' }));
    expect(res.edges[0].node.citationsJson).toBe(
      JSON.stringify([{ sourceId: 'S1', fileName: 'doc.md' }]),
    );
    expect(res.edges[0].node.toolCallsJson).toBe(JSON.stringify({ order: ['call-1'] }));
  });

  it('returns null citationsJson when missing', async () => {
    const chatRepo = {
      listMessagesBySession: jest.fn().mockResolvedValue([
        {
          id: 'm2',
          role: 'assistant',
          content: 'hi',
          turn: 1,
          messageIndex: 3,
          sourcesJson: null,
          citationsJson: null,
          toolCallsJson: null,
        },
      ]),
    } as any;

    const resolver = new ChatResolver(chatRepo);
    const res = await resolver.messages({ id: 's1' } as any, 50, undefined);

    expect(res.edges).toHaveLength(1);
    expect(res.edges[0].node.citationsJson).toBeNull();
    expect(res.edges[0].node.toolCallsJson).toBeNull();
  });
});
