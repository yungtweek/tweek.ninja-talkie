// apps/gateway/src/modules/graphql/types/chat/session.type.ts
import { Field, HideField, ID, ObjectType, PickType } from '@nestjs/graphql';
import { ChatSessionsZod } from '@tweek/types-zod';
import { SessionEventType } from '@/modules/chat/gql/chat.session.resolver';

@ObjectType()
export class ChatSessions implements ChatSessionsZod {
  @Field(() => ID)
  id!: string;

  @Field({ nullable: true })
  title?: string;

  @Field({ nullable: true })
  lastMessagePreview?: string;

  @Field({ nullable: true })
  lastMessageAt?: Date;

  @Field()
  createdAt!: Date;

  @Field()
  updatedAt!: Date;
}

@ObjectType()
export class DeleteChatSessionResult {
  @Field()
  ok!: boolean;

  @Field()
  status!: string;

  @Field(() => ID)
  sessionId!: string;
}

@ObjectType()
export class SessionSummary extends PickType(ChatSessions, ['id', 'title'] as const) {}

@ObjectType()
export class SessionEvent {
  @Field(() => SessionEventType)
  type!: SessionEventType;

  // CREATED / UPDATED 에서 내려줄 요약 정보
  @Field(() => SessionSummary, { nullable: true })
  session?: SessionSummary;

  // DELETED 에서만 사용
  @Field(() => ID, { nullable: true })
  id?: string;

  // 서버 필터용 내부 필드 (스키마 비노출)
  @HideField()
  userId?: string;
}
