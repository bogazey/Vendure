import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

interface UrlInputProps {
  onAnalyze: (url: string) => void;
  loading: boolean;
}

export default function UrlInput({ onAnalyze, loading }: UrlInputProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [justPasted, setJustPasted] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onAnalyze(value.trim());
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setValue(text.trim());
        setJustPasted(true);
        setTimeout(() => setJustPasted(false), 1200);
      }
    } catch {
      // Clipboard access denied by the browser; user can paste manually.
    }
  };

  return (
    <form onSubmit={handleSubmit} className="dashboard-url mx-auto w-full max-w-2xl">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t("downloader.placeholder")}
            dir="ltr"
            className="input-glass w-full px-5 py-4 text-base"
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handlePaste}
            className={`btn-glass px-4 py-4 transition-colors sm:px-5 ${justPasted ? "!border-brand-aqua/50 !text-brand-aqua" : ""}`}
          >
            {justPasted ? t("downloader.pasted") : t("downloader.paste")}
          </button>
          <button
            type="submit"
            disabled={loading || !value.trim()}
            className="btn-gradient px-5 py-4 sm:px-6"
          >
            {loading ? t("downloader.analyzing") : t("downloader.analyze")}
          </button>
        </div>
      </div>
    </form>
  );
}
