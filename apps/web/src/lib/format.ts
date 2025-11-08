// apps/web/src/lib/format.ts
export function formatBytes(bytes?: number | null): string {
  if (bytes == null) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return Number.isInteger(size) ? `${size} ${units[i]}` : `${size.toFixed(1)} ${units[i]}`;
}
