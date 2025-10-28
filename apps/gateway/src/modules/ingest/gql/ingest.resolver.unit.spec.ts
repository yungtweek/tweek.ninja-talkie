// ingest.resolver.unit.spec.ts
import { IngestResolver } from './ingest.resolver';
import { PUB_SUB } from '@/common/constants';

describe('deleteFile (unit)', () => {
  it('returns ok when service enqueues', async () => {
    const ingestService = {
      getFileOwnerId: jest.fn().mockResolvedValue('u_1'),
      markDeleting: jest.fn().mockResolvedValue(undefined),
      enqueueDelete: jest.fn().mockResolvedValue('job_123'),
    } as any;

    const pubSub = { publish: jest.fn(), asyncIterator: jest.fn() } as any;

    const r = new IngestResolver(ingestService, pubSub);
    const out = await r.deleteFile('file_1', 'u_1'); // @Args/@CurrentUser 데코레이터는 런타임용이라 여기선 그냥 값 넘기면 됨

    expect(out).toEqual({ ok: true, fileId: 'file_1', message: 'job_123' });
    expect(ingestService.markDeleting).toHaveBeenCalledWith('file_1');
    expect(pubSub.publish).not.toHaveBeenCalled();
  });
});
