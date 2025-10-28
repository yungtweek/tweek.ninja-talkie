// src/modules/ingest/ingest.module.ts
import { Module } from '@nestjs/common';
import { IngestController } from '@/modules/ingest/ingest.controller';
import { IngestService } from '@/modules/ingest/ingest.service';
import { ObjectStorageModule } from '@/modules/infra/object-storage/object-storage.module';
import { IngestRepository } from '@/modules/ingest/ingest.repository';
import { IngestResolver } from '@/modules/ingest/gql/ingest.resolver';
import { PubSub } from 'graphql-subscriptions';

@Module({
  imports: [ObjectStorageModule],
  controllers: [IngestController],
  providers: [
    IngestService,
    IngestRepository,
    IngestResolver,
    {
      provide: 'PUB_SUB',
      useFactory: () => new PubSub(),
    },
  ],
})
export class IngestModule {}
