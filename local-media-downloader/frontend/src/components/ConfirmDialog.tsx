import { useTranslation } from "react-i18next";

interface ConfirmDialogProps {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Small, reusable "are you sure?" modal - same visual pattern as the
 * grant-credits dialog it was factored out of, generalized for any
 * destructive/impactful action that needs a confirmation step first. */
export default function ConfirmDialog({ title, body, confirmLabel, danger = false, onConfirm, onCancel }: ConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
      <div className="glass-panel-raised flex w-full max-w-sm flex-col gap-4 p-5">
        <h2 className="font-display text-sm font-semibold text-slate-50">{title}</h2>
        <p className="text-sm text-slate-400">{body}</p>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="btn-glass px-3 py-1.5">
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={danger ? "rounded-full bg-red-600 px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-red-500" : "btn-gradient px-3 py-1.5"}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
