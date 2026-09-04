import { useEffect, useRef, useState } from "react";
import { PROGRESS_STREAM_URL, api } from "../services/api";
import type { DownloadJobOut } from "../types/api";

/**
 * Subscribes to the backend's SSE stream, which only emits when job state
 * actually changes. Falls back to a one-time fetch if the stream can't
 * connect, and reconnects automatically (browsers do this natively for SSE).
 */
export function useDownloadProgress() {
  const [jobs, setJobs] = useState<DownloadJobOut[]>([]);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let cancelled = false;

    api
      .listDownloads()
      .then((initial) => {
        if (!cancelled) setJobs(initial);
      })
      .catch(() => undefined);

    const source = new EventSource(PROGRESS_STREAM_URL);
    sourceRef.current = source;

    source.addEventListener("open", () => setConnected(true));
    source.addEventListener("error", () => setConnected(false));
    source.addEventListener("jobs", (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent).data) as DownloadJobOut[];
        setJobs(parsed);
      } catch {
        // ignore malformed frame
      }
    });

    return () => {
      cancelled = true;
      source.close();
    };
  }, []);

  return { jobs, connected };
}
