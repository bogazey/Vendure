import { useState } from "react";
import { useTranslation } from "react-i18next";

interface ErrorBannerProps {
  message: string;
  technical?: string | null;
  onDismiss?: () => void;
}

export default function ErrorBanner({ message, technical, onDismiss }: ErrorBannerProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200 backdrop-blur-xl">
      <div className="flex items-start justify-between gap-3">
        <p>{message}</p>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="shrink-0 text-red-300/70 hover:text-red-200"
            aria-label={t("common.dismissError")}
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
            {expanded ? t("common.hide") : t("common.show")} {t("common.technical")}
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
