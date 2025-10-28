// src/modules/infra/storage/object-storage.service.ts
import {
  S3Client,
  HeadObjectCommand,
  PutObjectCommand,
  GetObjectCommand,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { Injectable, Logger } from '@nestjs/common';

@Injectable()
export class ObjectStorageService {
  constructor(private readonly client: S3Client) {}
  private readonly logger = new Logger(ObjectStorageService.name);
  private bucket = process.env.S3_BUCKET!;

  async createPutUrl(params: {
    bucket?: string;
    key: string;
    contentType: string;
    checksum: string;
    expiresSec?: number;
    contentLength?: number;
  }) {
    const { key, bucket = params.bucket ?? this.bucket, contentType, expiresSec = 300 } = params;

    const cmd = new PutObjectCommand({
      Bucket: this.bucket,
      Key: key,
      ContentType: contentType,
      ChecksumSHA256: params.checksum,
    });
    const url = await getSignedUrl(this.client, cmd, { expiresIn: expiresSec });
    return { url, bucket, key, expiresIn: expiresSec };
  }

  async statObject(bucket: string, key: string) {
    const cmd = new HeadObjectCommand({
      Bucket: bucket,
      Key: key,
    });
    const res = await this.client.send(cmd);
    return {
      etag: res.ETag,
      size: res.ContentLength,
      lastModified: res.LastModified,
      contentType: res.ContentType,
    };
  }

  async finalize(user_id: string, bucket: string, key: string) {
    const cmd = new HeadObjectCommand({
      Bucket: bucket,
      Key: key,
    });
    const res = await this.client.send(cmd);
  }

  async createGetUrl(key: string, expiresSec = 300) {
    const cmd = new GetObjectCommand({ Bucket: this.bucket, Key: key });
    return getSignedUrl(this.client, cmd, { expiresIn: expiresSec });
  }
}
