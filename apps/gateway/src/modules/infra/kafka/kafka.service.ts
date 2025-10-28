// src/modules/kafka/kafka.service.ts
import {
  Injectable,
  OnModuleInit,
  OnModuleDestroy,
  Logger,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Kafka, Producer } from 'kafkajs';

const logger = new Logger('KafkaService');
@Injectable()
export class KafkaService implements OnModuleInit, OnModuleDestroy {
  private kafka: Kafka;
  private producer: Producer;

  constructor(private readonly config: ConfigService) {
    const brokersStr =
      this.config.get<string>('KAFKA_BROKERS') ?? 'localhost:9092';
    const brokers = brokersStr
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (!brokers.length) throw new Error('KAFKA_BROKERS is empty');

    this.kafka = new Kafka({ brokers });
    this.producer = this.kafka.producer();
  }

  async onModuleInit() {
    await this.producer.connect();
  }
  async onModuleDestroy() {
    await this.producer.disconnect();
  }

  async produce(topic: string, value: object, correlationId?: string) {
    logger.debug(`produce topic:${topic} correlationId:${correlationId}`);
    const key = correlationId ?? crypto.randomUUID();
    await this.producer.send({
      topic,
      messages: [
        {
          key: key,
          value: JSON.stringify(value),
          headers: {
            'x-correlation-id': correlationId,
          },
        },
      ],
    });
  }
}
