// apps/gateway/src/graphql/types/chat/chat.type.ts
import { Field, HideField, ID, Int, ObjectType, PickType } from '@nestjs/graphql';
import { PageInfo } from '@/modules/infra/graphql/types/page-info.type';
import { SessionEventType } from '@/modules/chat/gql/chat.session.resolver';

@ObjectType()
export class Message {
  @Field(() => ID) id!: string;
  @Field() role!: 'user' | 'assistant' | 'system';
  @Field() content!: string;
  @Field(() => Int) turn!: number;
  @Field(() => Int) messageIndex!: number;
  @Field({ nullable: true }) sourcesJson?: string;
}

@ObjectType()
export class MessageEdge {
  @Field(() => Message) node!: Message;
  @Field() cursor!: string;
}

@ObjectType()
export class MessageConnection {
  @Field(() => [MessageEdge]) edges!: MessageEdge[];
  @Field(() => PageInfo) pageInfo!: PageInfo;
}

@ObjectType()
export class ChatSession {
  @Field(() => ID)
  id!: string;

  @Field({ nullable: true })
  title?: string;

  @Field({ nullable: true })
  lastMessagePreview?: string;

  @Field({ nullable: true })
  lastMessageAt?: Date;

  @Field({ nullable: true })
  createdAt?: Date;

  @Field({ nullable: true })
  updatedAt?: Date;

  @Field(() => MessageConnection) messages!: MessageConnection;
}

@ObjectType()
export class ChatSessionEdge {
  @Field(() => ChatSession)
  node!: ChatSession;
}

@ObjectType()
export class ChatSessionConnection {
  @Field(() => [ChatSessionEdge])
  edges!: ChatSessionEdge[];

  @Field(() => PageInfo)
  pageInfo!: PageInfo;
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
export class SessionSummary extends PickType(ChatSession, ['id', 'title'] as const) {}

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
