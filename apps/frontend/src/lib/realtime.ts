import { useEffect, useState } from "react";

import { SyncEvent } from "./api";

const CURSOR_KEY = "domovoy.sync.cursor";

export function useRealtime(enabled: boolean): number {
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const cursor = localStorage.getItem(CURSOR_KEY) ?? "0";
    const source = new EventSource(`/api/v1/sync/stream?after=${encodeURIComponent(cursor)}`);
    source.addEventListener("change", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as SyncEvent;
        localStorage.setItem(CURSOR_KEY, String(payload.sequence));
        setRevision((value) => value + 1);
      } catch {
        // A malformed event is ignored; EventSource will continue with the next event.
      }
    });
    return () => source.close();
  }, [enabled]);

  return revision;
}
