// src/modules/chat/chat.module.ts
import { Module } from '@nestjs/common';
import { ChatController } from './chat.controller';
import { ChatService } from './chat.service';
import { ChatRepository } from '@/modules/chat/chat.repository';
import { ChatSessionResolver } from '@/modules/chat/gql/chat.session.resolver';
import { ChatResolver } from '@/modules/chat/gql/chat.resolver';

@Module({
  controllers: [ChatController],
  providers: [ChatService, ChatRepository, ChatSessionResolver, ChatResolver],
  exports: [ChatService],
})
export class ChatModule {}
