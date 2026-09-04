import { useState } from "react";

interface ErrorBannerProps {
  message: string;
  technical?: string | null;
  onDismiss?: () => void;
}

export default function ErrorBanner({ message, technical, onDismiss }: ErrorBannerProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      <div className="flex items-start justify-between gap-3">
        <p>{message}</p>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="shrink-0 text-red-300/70 hover:text-red-200"
            aria-label="Dismiss error"
          >
            ✕
          </button>
        )}
      </div>
      {technical && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-red-300/80 underline decoration-dotted underline-offset-2 hover:text-red-200"
          >
            {expanded ? "Hide" : "Show"} technical details
          </button>
          {expanded && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-black/30 p-2 text-xs text-red-100/80">
              {technical}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
