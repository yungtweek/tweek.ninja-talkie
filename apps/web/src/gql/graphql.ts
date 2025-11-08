/* eslint-disable */
import type { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';
export type Maybe<T> = T | null;
export type InputMaybe<T> = T | null | undefined;
export type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
export type MakeOptional<T, K extends keyof T> = Omit<T, K> & { [SubKey in K]?: Maybe<T[SubKey]> };
export type MakeMaybe<T, K extends keyof T> = Omit<T, K> & { [SubKey in K]: Maybe<T[SubKey]> };
export type MakeEmpty<T extends { [key: string]: unknown }, K extends keyof T> = { [_ in K]?: never };
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
/** All built-in and custom scalars, mapped to their actual values */
export type Scalars = {
  ID: { input: string; output: string; }
  String: { input: string; output: string; }
  Boolean: { input: boolean; output: boolean; }
  Int: { input: number; output: number; }
  Float: { input: number; output: number; }
  /** A date-time string at UTC, such as 2019-12-03T09:54:33Z, compliant with the date-time format. */
  DateTime: { input: string; output: string; }
};

export type ChatSession = {
  __typename?: 'ChatSession';
  createdAt?: Maybe<Scalars['DateTime']['output']>;
  id: Scalars['ID']['output'];
  lastMessageAt?: Maybe<Scalars['DateTime']['output']>;
  lastMessagePreview?: Maybe<Scalars['String']['output']>;
  messages: MessageConnection;
  title?: Maybe<Scalars['String']['output']>;
  updatedAt?: Maybe<Scalars['DateTime']['output']>;
};


export type ChatSessionMessagesArgs = {
  before?: InputMaybe<Scalars['String']['input']>;
  first?: InputMaybe<Scalars['Int']['input']>;
};

export type ChatSessionConnection = {
  __typename?: 'ChatSessionConnection';
  edges: Array<ChatSessionEdge>;
  pageInfo: PageInfo;
};

export type ChatSessionEdge = {
  __typename?: 'ChatSessionEdge';
  node: ChatSession;
};

export type DeleteChatSessionResult = {
  __typename?: 'DeleteChatSessionResult';
  ok: Scalars['Boolean']['output'];
  sessionId: Scalars['ID']['output'];
  status: Scalars['String']['output'];
};

export type DeleteFilePayload = {
  __typename?: 'DeleteFilePayload';
  deletedCount?: Maybe<Scalars['Float']['output']>;
  fileId?: Maybe<Scalars['ID']['output']>;
  message?: Maybe<Scalars['String']['output']>;
  ok: Scalars['Boolean']['output'];
};

export type FileConnection = {
  __typename?: 'FileConnection';
  edges: Array<FileEdge>;
  pageInfo: PageInfo;
};

export type FileEdge = {
  __typename?: 'FileEdge';
  cursor?: Maybe<Scalars['String']['output']>;
  node: FileListType;
};

export type FileListType = {
  __typename?: 'FileListType';
  contentType: Scalars['String']['output'];
  createdAt: Scalars['DateTime']['output'];
  filename: Scalars['String']['output'];
  id: Scalars['ID']['output'];
  size: Scalars['Float']['output'];
  status: FileStatus;
  uploadedAt: Scalars['DateTime']['output'];
  visibility: FileVisibility;
};

export type FileStatus =
  | 'deleted'
  | 'failed'
  | 'indexed'
  | 'pending'
  | 'ready'
  | 'vectorized';

export type FileType = {
  __typename?: 'FileType';
  bucket: Scalars['String']['output'];
  checksumSha256Expected?: Maybe<Scalars['String']['output']>;
  contentType?: Maybe<Scalars['String']['output']>;
  createdAt: Scalars['DateTime']['output'];
  etag?: Maybe<Scalars['String']['output']>;
  extension?: Maybe<Scalars['String']['output']>;
  filename: Scalars['String']['output'];
  id: Scalars['ID']['output'];
  key: Scalars['String']['output'];
  modifiedAt?: Maybe<Scalars['DateTime']['output']>;
  ownerId: Scalars['String']['output'];
  size?: Maybe<Scalars['Float']['output']>;
  sizeExpected?: Maybe<Scalars['Float']['output']>;
  status: FileStatus;
  uploadedAt?: Maybe<Scalars['DateTime']['output']>;
  visibility: FileVisibility;
};

export type FileVisibility =
  | 'department'
  | 'followers'
  | 'private'
  | 'public';

export type Message = {
  __typename?: 'Message';
  content: Scalars['String']['output'];
  id: Scalars['ID']['output'];
  messageIndex: Scalars['Int']['output'];
  role: Scalars['String']['output'];
  sourcesJson?: Maybe<Scalars['String']['output']>;
  turn: Scalars['Int']['output'];
};

export type MessageConnection = {
  __typename?: 'MessageConnection';
  edges: Array<MessageEdge>;
  pageInfo: PageInfo;
};

export type MessageEdge = {
  __typename?: 'MessageEdge';
  cursor: Scalars['String']['output'];
  node: Message;
};

export type Mutation = {
  __typename?: 'Mutation';
  deleteChatSession: DeleteChatSessionResult;
  deleteFile: DeleteFilePayload;
  registerFile: FileType;
  updateVisibility: Scalars['Boolean']['output'];
};


export type MutationDeleteChatSessionArgs = {
  sessionId: Scalars['ID']['input'];
};


export type MutationDeleteFileArgs = {
  fileId: Scalars['ID']['input'];
};


export type MutationRegisterFileArgs = {
  bucket: Scalars['String']['input'];
  contentType: Scalars['String']['input'];
  filename: Scalars['String']['input'];
  key: Scalars['String']['input'];
  ownerId: Scalars['String']['input'];
  status?: InputMaybe<FileStatus>;
  visibility?: InputMaybe<FileVisibility>;
};


export type MutationUpdateVisibilityArgs = {
  fileId: Scalars['ID']['input'];
  visibility: FileVisibility;
};

export type PageInfo = {
  __typename?: 'PageInfo';
  endCursor?: Maybe<Scalars['String']['output']>;
  hasNextPage: Scalars['Boolean']['output'];
  hasPreviousPage: Scalars['Boolean']['output'];
  startCursor?: Maybe<Scalars['String']['output']>;
};

export type Query = {
  __typename?: 'Query';
  chatSession: ChatSession;
  chatSessionList: ChatSessionConnection;
  /** List files */
  files: FileConnection;
};


export type QueryChatSessionArgs = {
  id: Scalars['ID']['input'];
};


export type QueryChatSessionListArgs = {
  after?: InputMaybe<Scalars['String']['input']>;
  first?: InputMaybe<Scalars['Int']['input']>;
};


export type QueryFilesArgs = {
  after?: InputMaybe<Scalars['String']['input']>;
  first: Scalars['Int']['input'];
};

export type SessionEvent = {
  __typename?: 'SessionEvent';
  id?: Maybe<Scalars['ID']['output']>;
  session?: Maybe<SessionSummary>;
  type: SessionEventType;
};

export type SessionEventType =
  | 'CREATED'
  | 'DELETED'
  | 'UPDATED';

export type SessionSummary = {
  __typename?: 'SessionSummary';
  id: Scalars['ID']['output'];
  title?: Maybe<Scalars['String']['output']>;
};

export type Subscription = {
  __typename?: 'Subscription';
  fileStatusChanged: FileType;
  sessionEvents: SessionEvent;
};


export type SubscriptionFileStatusChangedArgs = {
  fileId: Scalars['String']['input'];
};

export type ChatSessionQueryVariables = Exact<{
  id: Scalars['ID']['input'];
  first?: InputMaybe<Scalars['Int']['input']>;
}>;


export type ChatSessionQuery = { __typename?: 'Query', chatSession: { __typename?: 'ChatSession', id: string, title?: string | null, createdAt?: string | null, updatedAt?: string | null, messages: { __typename?: 'MessageConnection', edges: Array<{ __typename?: 'MessageEdge', cursor: string, node: { __typename?: 'Message', id: string, role: string, content: string, turn: number, messageIndex: number, sourcesJson?: string | null } }>, pageInfo: { __typename?: 'PageInfo', hasPreviousPage: boolean, hasNextPage: boolean, startCursor?: string | null, endCursor?: string | null } } } };

export type ChatSessionMetaFragment = { __typename?: 'ChatSession', id: string, title?: string | null, createdAt?: string | null, updatedAt?: string | null } & { ' $fragmentName'?: 'ChatSessionMetaFragment' };

export type ChatSessionListQueryVariables = Exact<{
  first?: InputMaybe<Scalars['Int']['input']>;
  after?: InputMaybe<Scalars['String']['input']>;
}>;


export type ChatSessionListQuery = { __typename?: 'Query', chatSessionList: { __typename?: 'ChatSessionConnection', edges: Array<{ __typename?: 'ChatSessionEdge', node: { __typename?: 'ChatSession', id: string, title?: string | null, createdAt?: string | null, updatedAt?: string | null } }>, pageInfo: { __typename?: 'PageInfo', hasPreviousPage: boolean, hasNextPage: boolean, startCursor?: string | null, endCursor?: string | null } } };

export type DeleteSessionMutationVariables = Exact<{
  sessionId: Scalars['ID']['input'];
}>;


export type DeleteSessionMutation = { __typename?: 'Mutation', deleteChatSession: { __typename?: 'DeleteChatSessionResult', ok: boolean, status: string, sessionId: string } };

export type FilesQueryVariables = Exact<{
  first: Scalars['Int']['input'];
  after?: InputMaybe<Scalars['String']['input']>;
}>;


export type FilesQuery = { __typename?: 'Query', files: { __typename?: 'FileConnection', edges: Array<{ __typename?: 'FileEdge', cursor?: string | null, node: (
        { __typename?: 'FileListType' }
        & { ' $fragmentRefs'?: { 'FileMetaFragment': FileMetaFragment } }
      ) }>, pageInfo: { __typename?: 'PageInfo', hasNextPage: boolean, hasPreviousPage: boolean, startCursor?: string | null, endCursor?: string | null } } };

export type FileMetaFragment = { __typename: 'FileListType', id: string, filename: string, contentType: string, size: number, status: FileStatus, visibility: FileVisibility, uploadedAt: string, createdAt: string } & { ' $fragmentName'?: 'FileMetaFragment' };

export type FileStatusFragment = { __typename: 'FileListType', id: string, status: FileStatus } & { ' $fragmentName'?: 'FileStatusFragment' };

export type FileVisibilityFragment = { __typename: 'FileListType', id: string, visibility: FileVisibility } & { ' $fragmentName'?: 'FileVisibilityFragment' };

export type DeleteFileMutationVariables = Exact<{
  fileId: Scalars['ID']['input'];
}>;


export type DeleteFileMutation = { __typename?: 'Mutation', deleteFile: { __typename?: 'DeleteFilePayload', ok: boolean, fileId?: string | null, deletedCount?: number | null, message?: string | null } };

export type UpdateVisibilityMutationVariables = Exact<{
  fileId: Scalars['ID']['input'];
  visibility: FileVisibility;
}>;


export type UpdateVisibilityMutation = { __typename?: 'Mutation', updateVisibility: boolean };

export const ChatSessionMetaFragmentDoc = {"kind":"Document","definitions":[{"kind":"FragmentDefinition","name":{"kind":"Name","value":"ChatSessionMeta"},"typeCondition":{"kind":"NamedType","name":{"kind":"Name","value":"ChatSession"}},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"title"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}},{"kind":"Field","name":{"kind":"Name","value":"updatedAt"}}]}}]} as unknown as DocumentNode<ChatSessionMetaFragment, unknown>;
export const FileMetaFragmentDoc = {"kind":"Document","definitions":[{"kind":"FragmentDefinition","name":{"kind":"Name","value":"FileMeta"},"typeCondition":{"kind":"NamedType","name":{"kind":"Name","value":"FileListType"}},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"__typename"}},{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"filename"}},{"kind":"Field","name":{"kind":"Name","value":"contentType"}},{"kind":"Field","name":{"kind":"Name","value":"size"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"visibility"}},{"kind":"Field","name":{"kind":"Name","value":"uploadedAt"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}}]} as unknown as DocumentNode<FileMetaFragment, unknown>;
export const FileStatusFragmentDoc = {"kind":"Document","definitions":[{"kind":"FragmentDefinition","name":{"kind":"Name","value":"FileStatus"},"typeCondition":{"kind":"NamedType","name":{"kind":"Name","value":"FileListType"}},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"__typename"}},{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"status"}}]}}]} as unknown as DocumentNode<FileStatusFragment, unknown>;
export const FileVisibilityFragmentDoc = {"kind":"Document","definitions":[{"kind":"FragmentDefinition","name":{"kind":"Name","value":"FileVisibility"},"typeCondition":{"kind":"NamedType","name":{"kind":"Name","value":"FileListType"}},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"__typename"}},{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"visibility"}}]}}]} as unknown as DocumentNode<FileVisibilityFragment, unknown>;
export const ChatSessionDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"ChatSession"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ID"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"first"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}},"defaultValue":{"kind":"IntValue","value":"50"}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"chatSession"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"title"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}},{"kind":"Field","name":{"kind":"Name","value":"updatedAt"}},{"kind":"Field","name":{"kind":"Name","value":"messages"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"first"},"value":{"kind":"Variable","name":{"kind":"Name","value":"first"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"edges"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"cursor"}},{"kind":"Field","name":{"kind":"Name","value":"node"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"role"}},{"kind":"Field","name":{"kind":"Name","value":"content"}},{"kind":"Field","name":{"kind":"Name","value":"turn"}},{"kind":"Field","name":{"kind":"Name","value":"messageIndex"}},{"kind":"Field","name":{"kind":"Name","value":"sourcesJson"}}]}}]}},{"kind":"Field","name":{"kind":"Name","value":"pageInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"hasPreviousPage"}},{"kind":"Field","name":{"kind":"Name","value":"hasNextPage"}},{"kind":"Field","name":{"kind":"Name","value":"startCursor"}},{"kind":"Field","name":{"kind":"Name","value":"endCursor"}}]}}]}}]}}]}}]} as unknown as DocumentNode<ChatSessionQuery, ChatSessionQueryVariables>;
export const ChatSessionListDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"ChatSessionList"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"first"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}},"defaultValue":{"kind":"IntValue","value":"20"}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"after"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"chatSessionList"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"first"},"value":{"kind":"Variable","name":{"kind":"Name","value":"first"}}},{"kind":"Argument","name":{"kind":"Name","value":"after"},"value":{"kind":"Variable","name":{"kind":"Name","value":"after"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"edges"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"node"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"title"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}},{"kind":"Field","name":{"kind":"Name","value":"updatedAt"}}]}}]}},{"kind":"Field","name":{"kind":"Name","value":"pageInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"hasPreviousPage"}},{"kind":"Field","name":{"kind":"Name","value":"hasNextPage"}},{"kind":"Field","name":{"kind":"Name","value":"startCursor"}},{"kind":"Field","name":{"kind":"Name","value":"endCursor"}}]}}]}}]}}]} as unknown as DocumentNode<ChatSessionListQuery, ChatSessionListQueryVariables>;
export const DeleteSessionDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"DeleteSession"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"sessionId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ID"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"deleteChatSession"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"sessionId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"sessionId"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"ok"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"sessionId"}}]}}]}}]} as unknown as DocumentNode<DeleteSessionMutation, DeleteSessionMutationVariables>;
export const FilesDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"Files"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"first"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"after"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"files"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"first"},"value":{"kind":"Variable","name":{"kind":"Name","value":"first"}}},{"kind":"Argument","name":{"kind":"Name","value":"after"},"value":{"kind":"Variable","name":{"kind":"Name","value":"after"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"edges"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"cursor"}},{"kind":"Field","name":{"kind":"Name","value":"node"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"FragmentSpread","name":{"kind":"Name","value":"FileMeta"}}]}}]}},{"kind":"Field","name":{"kind":"Name","value":"pageInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"hasNextPage"}},{"kind":"Field","name":{"kind":"Name","value":"hasPreviousPage"}},{"kind":"Field","name":{"kind":"Name","value":"startCursor"}},{"kind":"Field","name":{"kind":"Name","value":"endCursor"}}]}}]}}]}},{"kind":"FragmentDefinition","name":{"kind":"Name","value":"FileMeta"},"typeCondition":{"kind":"NamedType","name":{"kind":"Name","value":"FileListType"}},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"__typename"}},{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"filename"}},{"kind":"Field","name":{"kind":"Name","value":"contentType"}},{"kind":"Field","name":{"kind":"Name","value":"size"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"visibility"}},{"kind":"Field","name":{"kind":"Name","value":"uploadedAt"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}}]} as unknown as DocumentNode<FilesQuery, FilesQueryVariables>;
export const DeleteFileDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"DeleteFile"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"fileId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ID"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"deleteFile"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"fileId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"fileId"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"ok"}},{"kind":"Field","name":{"kind":"Name","value":"fileId"}},{"kind":"Field","name":{"kind":"Name","value":"deletedCount"}},{"kind":"Field","name":{"kind":"Name","value":"message"}}]}}]}}]} as unknown as DocumentNode<DeleteFileMutation, DeleteFileMutationVariables>;
export const UpdateVisibilityDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"UpdateVisibility"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"fileId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ID"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"visibility"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"FileVisibility"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"updateVisibility"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"fileId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"fileId"}}},{"kind":"Argument","name":{"kind":"Name","value":"visibility"},"value":{"kind":"Variable","name":{"kind":"Name","value":"visibility"}}}]}]}}]} as unknown as DocumentNode<UpdateVisibilityMutation, UpdateVisibilityMutationVariables>;