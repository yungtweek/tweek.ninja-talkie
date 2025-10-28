import { Module } from '@nestjs/common';
import { ObjectStorageService } from './object-storage.service';
import { createMinioClient } from './object-storage.client';
import { S3Client } from '@aws-sdk/client-s3';

@Module({
  providers: [
    {
      provide: S3Client,
      useFactory: () =>
        createMinioClient({
          endPoint: process.env.S3_ENDPOINT ?? '127.0.0.1',
          accessKey: process.env.S3_ACCESS_KEY ?? 'admin',
          secretKey: process.env.S3_SECRET_KEY ?? 'admin12345',
        }),
    },
    ObjectStorageService,
  ],
  exports: [ObjectStorageService],
})
export class ObjectStorageModule {}
