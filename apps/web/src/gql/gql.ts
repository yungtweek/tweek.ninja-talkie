/* eslint-disable */
import * as types from './graphql';
import type { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';

/**
 * Map of all GraphQL operations in the project.
 *
 * This map has several performance disadvantages:
 * 1. It is not tree-shakeable, so it will include all operations in the project.
 * 2. It is not minifiable, so the string of a GraphQL query will be multiple times inside the bundle.
 * 3. It does not support dead code elimination, so it will add unused operations.
 *
 * Therefore it is highly recommended to use the babel or swc plugin for production.
 * Learn more about it here: https://the-guild.dev/graphql/codegen/plugins/presets/preset-client#reducing-bundle-size
 */
type Documents = {
    "query ChatSession($id: ID!, $first: Int = 50) {\n  chatSession(id: $id) {\n    id\n    title\n    createdAt\n    updatedAt\n    messages(first: $first) {\n      edges {\n        cursor\n        node {\n          id\n          role\n          content\n          turn\n          messageIndex\n          sourcesJson\n        }\n      }\n      pageInfo {\n        hasPreviousPage\n        hasNextPage\n        startCursor\n        endCursor\n      }\n    }\n  }\n}\n\nfragment ChatSessionMeta on ChatSession {\n  id\n  title\n  createdAt\n  updatedAt\n}\n\nquery ChatSessionList($first: Int = 20, $after: String) {\n  chatSessionList(first: $first, after: $after) {\n    edges {\n      node {\n        id\n        title\n        createdAt\n        updatedAt\n      }\n    }\n    pageInfo {\n      hasPreviousPage\n      hasNextPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nmutation DeleteSession($sessionId: ID!) {\n  deleteChatSession(sessionId: $sessionId) {\n    ok\n    status\n    sessionId\n  }\n}": typeof types.ChatSessionDocument,
    "query Files($first: Int!, $after: String) {\n  files(first: $first, after: $after) {\n    edges {\n      cursor\n      node {\n        ...FileMeta\n      }\n    }\n    pageInfo {\n      hasNextPage\n      hasPreviousPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nfragment FileMeta on FileListType {\n  __typename\n  id\n  filename\n  contentType\n  size\n  status\n  visibility\n  uploadedAt\n  createdAt\n}\n\nfragment FileStatus on FileListType {\n  __typename\n  id\n  status\n}\n\nfragment FileVisibility on FileListType {\n  __typename\n  id\n  visibility\n}\n\nmutation DeleteFile($fileId: ID!) {\n  deleteFile(fileId: $fileId) {\n    ok\n    fileId\n    deletedCount\n    message\n  }\n}\n\nmutation UpdateVisibility($fileId: ID!, $visibility: FileVisibility!) {\n  updateVisibility(fileId: $fileId, visibility: $visibility)\n}": typeof types.FilesDocument,
};
const documents: Documents = {
    "query ChatSession($id: ID!, $first: Int = 50) {\n  chatSession(id: $id) {\n    id\n    title\n    createdAt\n    updatedAt\n    messages(first: $first) {\n      edges {\n        cursor\n        node {\n          id\n          role\n          content\n          turn\n          messageIndex\n          sourcesJson\n        }\n      }\n      pageInfo {\n        hasPreviousPage\n        hasNextPage\n        startCursor\n        endCursor\n      }\n    }\n  }\n}\n\nfragment ChatSessionMeta on ChatSession {\n  id\n  title\n  createdAt\n  updatedAt\n}\n\nquery ChatSessionList($first: Int = 20, $after: String) {\n  chatSessionList(first: $first, after: $after) {\n    edges {\n      node {\n        id\n        title\n        createdAt\n        updatedAt\n      }\n    }\n    pageInfo {\n      hasPreviousPage\n      hasNextPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nmutation DeleteSession($sessionId: ID!) {\n  deleteChatSession(sessionId: $sessionId) {\n    ok\n    status\n    sessionId\n  }\n}": types.ChatSessionDocument,
    "query Files($first: Int!, $after: String) {\n  files(first: $first, after: $after) {\n    edges {\n      cursor\n      node {\n        ...FileMeta\n      }\n    }\n    pageInfo {\n      hasNextPage\n      hasPreviousPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nfragment FileMeta on FileListType {\n  __typename\n  id\n  filename\n  contentType\n  size\n  status\n  visibility\n  uploadedAt\n  createdAt\n}\n\nfragment FileStatus on FileListType {\n  __typename\n  id\n  status\n}\n\nfragment FileVisibility on FileListType {\n  __typename\n  id\n  visibility\n}\n\nmutation DeleteFile($fileId: ID!) {\n  deleteFile(fileId: $fileId) {\n    ok\n    fileId\n    deletedCount\n    message\n  }\n}\n\nmutation UpdateVisibility($fileId: ID!, $visibility: FileVisibility!) {\n  updateVisibility(fileId: $fileId, visibility: $visibility)\n}": types.FilesDocument,
};

/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 *
 *
 * @example
 * ```ts
 * const query = graphql(`query GetUser($id: ID!) { user(id: $id) { name } }`);
 * ```
 *
 * The query argument is unknown!
 * Please regenerate the types.
 */
export function graphql(source: string): unknown;

/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "query ChatSession($id: ID!, $first: Int = 50) {\n  chatSession(id: $id) {\n    id\n    title\n    createdAt\n    updatedAt\n    messages(first: $first) {\n      edges {\n        cursor\n        node {\n          id\n          role\n          content\n          turn\n          messageIndex\n          sourcesJson\n        }\n      }\n      pageInfo {\n        hasPreviousPage\n        hasNextPage\n        startCursor\n        endCursor\n      }\n    }\n  }\n}\n\nfragment ChatSessionMeta on ChatSession {\n  id\n  title\n  createdAt\n  updatedAt\n}\n\nquery ChatSessionList($first: Int = 20, $after: String) {\n  chatSessionList(first: $first, after: $after) {\n    edges {\n      node {\n        id\n        title\n        createdAt\n        updatedAt\n      }\n    }\n    pageInfo {\n      hasPreviousPage\n      hasNextPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nmutation DeleteSession($sessionId: ID!) {\n  deleteChatSession(sessionId: $sessionId) {\n    ok\n    status\n    sessionId\n  }\n}"): (typeof documents)["query ChatSession($id: ID!, $first: Int = 50) {\n  chatSession(id: $id) {\n    id\n    title\n    createdAt\n    updatedAt\n    messages(first: $first) {\n      edges {\n        cursor\n        node {\n          id\n          role\n          content\n          turn\n          messageIndex\n          sourcesJson\n        }\n      }\n      pageInfo {\n        hasPreviousPage\n        hasNextPage\n        startCursor\n        endCursor\n      }\n    }\n  }\n}\n\nfragment ChatSessionMeta on ChatSession {\n  id\n  title\n  createdAt\n  updatedAt\n}\n\nquery ChatSessionList($first: Int = 20, $after: String) {\n  chatSessionList(first: $first, after: $after) {\n    edges {\n      node {\n        id\n        title\n        createdAt\n        updatedAt\n      }\n    }\n    pageInfo {\n      hasPreviousPage\n      hasNextPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nmutation DeleteSession($sessionId: ID!) {\n  deleteChatSession(sessionId: $sessionId) {\n    ok\n    status\n    sessionId\n  }\n}"];
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "query Files($first: Int!, $after: String) {\n  files(first: $first, after: $after) {\n    edges {\n      cursor\n      node {\n        ...FileMeta\n      }\n    }\n    pageInfo {\n      hasNextPage\n      hasPreviousPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nfragment FileMeta on FileListType {\n  __typename\n  id\n  filename\n  contentType\n  size\n  status\n  visibility\n  uploadedAt\n  createdAt\n}\n\nfragment FileStatus on FileListType {\n  __typename\n  id\n  status\n}\n\nfragment FileVisibility on FileListType {\n  __typename\n  id\n  visibility\n}\n\nmutation DeleteFile($fileId: ID!) {\n  deleteFile(fileId: $fileId) {\n    ok\n    fileId\n    deletedCount\n    message\n  }\n}\n\nmutation UpdateVisibility($fileId: ID!, $visibility: FileVisibility!) {\n  updateVisibility(fileId: $fileId, visibility: $visibility)\n}"): (typeof documents)["query Files($first: Int!, $after: String) {\n  files(first: $first, after: $after) {\n    edges {\n      cursor\n      node {\n        ...FileMeta\n      }\n    }\n    pageInfo {\n      hasNextPage\n      hasPreviousPage\n      startCursor\n      endCursor\n    }\n  }\n}\n\nfragment FileMeta on FileListType {\n  __typename\n  id\n  filename\n  contentType\n  size\n  status\n  visibility\n  uploadedAt\n  createdAt\n}\n\nfragment FileStatus on FileListType {\n  __typename\n  id\n  status\n}\n\nfragment FileVisibility on FileListType {\n  __typename\n  id\n  visibility\n}\n\nmutation DeleteFile($fileId: ID!) {\n  deleteFile(fileId: $fileId) {\n    ok\n    fileId\n    deletedCount\n    message\n  }\n}\n\nmutation UpdateVisibility($fileId: ID!, $visibility: FileVisibility!) {\n  updateVisibility(fileId: $fileId, visibility: $visibility)\n}"];

export function graphql(source: string) {
  return (documents as any)[source] ?? {};
}

export type DocumentType<TDocumentNode extends DocumentNode<any, any>> = TDocumentNode extends DocumentNode<  infer TType,  any>  ? TType  : never;