import type {
  FileStatus as ZFileStatus,
  FileVisibility as ZFileVisibility,
} from '@talkie/types-zod';
import {
  FileStatus as FileStatusT,
  FileStatusFragment,
  FileStatusFragmentDoc,
  FileVisibility as FileVisibilityT,
  FileVisibilityFragment,
  FileVisibilityFragmentDoc,
} from '@/gql/graphql';
import { ApolloCache } from '@apollo/client';

export const toGqlStatus = (s: ZFileStatus): FileStatusT => s as unknown as FileStatusT;
export const toGqlVisibility = (s: ZFileVisibility): FileVisibilityT =>
  s as unknown as FileVisibilityT;

// --- Apollo cache helpers -----------------------------------------------------
export const writeFileStatus = (cache: ApolloCache, id: string, status: FileStatusT) => {
  const cacheId = cache.identify({ __typename: 'FileListType', id });
  if (!cacheId) return;
  cache.writeFragment<FileStatusFragment>({
    id: cacheId,
    fragment: FileStatusFragmentDoc,
    data: { __typename: 'FileListType', id, status },
  });
};

export const writeFileVisibility = (
  cache: ApolloCache,
  id: string,
  visibility: FileVisibilityT,
) => {
  const cacheId = cache.identify({ __typename: 'FileListType', id });
  if (!cacheId) return;
  cache.writeFragment<FileVisibilityFragment>({
    id: cacheId,
    fragment: FileVisibilityFragmentDoc,
    data: { __typename: 'FileListType', id, visibility },
  });
};
