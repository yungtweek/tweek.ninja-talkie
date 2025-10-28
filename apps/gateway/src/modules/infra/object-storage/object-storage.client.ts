import { S3Client } from '@aws-sdk/client-s3';
export function createMinioClient(cfg: {
  endPoint: string;
  accessKey: string;
  secretKey: string;
}) {
  return new S3Client({
    region: 'us-east-1',
    endpoint: cfg.endPoint,
    credentials: {
      accessKeyId: cfg.accessKey,
      secretAccessKey: cfg.secretKey,
    },
    forcePathStyle: true, // MinIO 필수
  });
}
