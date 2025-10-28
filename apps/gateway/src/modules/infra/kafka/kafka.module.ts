// src/modules/kafka/kafka.module.ts
import { Module, Global } from '@nestjs/common';
import { KafkaService } from './kafka.service';

@Global()
@Module({
  providers: [KafkaService],
  exports: [KafkaService],
})
export class KafkaModule {}
