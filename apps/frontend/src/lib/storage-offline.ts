import { StorageContents } from "./api";

const KEY = "domovoy.storage.recent";

type CachedSection = { nodeId: string; savedAt: string; contents: StorageContents };

function sections(): CachedSection[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]") as CachedSection[];
  } catch {
    return [];
  }
}

export function cacheStorageSection(nodeId: string, contents: StorageContents) {
  const next = [
    { nodeId, savedAt: new Date().toISOString(), contents },
    ...sections().filter((item) => item.nodeId !== nodeId),
  ].slice(0, 10);
  localStorage.setItem(KEY, JSON.stringify(next));
}

export function cachedStorageSection(nodeId: string): StorageContents | null {
  return sections().find((item) => item.nodeId === nodeId)?.contents ?? null;
}
