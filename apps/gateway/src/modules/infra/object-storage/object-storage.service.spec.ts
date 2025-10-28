// object-storage.service.spec.ts
import {
  S3Client,
  PutObjectCommand,
  HeadObjectCommand,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { ObjectStorageService } from './object-storage.service';

jest.mock('@aws-sdk/s3-request-presigner', () => ({
  getSignedUrl: jest.fn().mockResolvedValue('https://signed.example/put'),
}));

describe('ObjectStorageService', () => {
  const s3 = { send: jest.fn() } as unknown as S3Client;
  const svc = new ObjectStorageService(s3 as any as S3Client);

  it('createPutUrl: PutObjectCommand 파라미터 검증', async () => {
    const res = await svc.createPutUrl({
      key: 'u1/123.pdf',
      contentType: 'application/pdf',
      checksum: 'BASE64_SHA256',
      expiresSec: 120,
    });

    expect(getSignedUrl).toHaveBeenCalled();
    const cmd = (getSignedUrl as jest.Mock).mock.calls[0][0]; // client
    const put = (getSignedUrl as jest.Mock).mock
      .calls[0][1] as PutObjectCommand;
    const input = (put as any).input;

    expect(input.Bucket).toBe(process.env.S3_BUCKET);
    expect(input.Key).toBe('u1/123.pdf');
    expect(input.ContentType).toBe('application/pdf');
    expect(input.ChecksumSHA256).toBe('BASE64_SHA256');
    expect(res.url).toContain('https://signed.example/put');
    expect(res.expiresIn).toBe(120);
  });

  it('statObject: HeadObject 호출 확인', async () => {
    (s3.send as any).mockResolvedValue({
      ETag: '"etag"',
      ContentLength: 10,
      LastModified: new Date('2025-10-20T12:00:00Z'),
      ContentType: 'text/plain',
    });
    const r = await svc.statObject('b', 'k');
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(s3.send).toHaveBeenCalledWith(expect.any(HeadObjectCommand));
    expect(r.size).toBe(10);
  });
});
