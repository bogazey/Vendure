import { useState } from "react";

interface FirstRunSetupProps {
  onRecheck: () => void;
  checking: boolean;
}

const INSTRUCTIONS: { os: string; command: string }[] = [
  { os: "macOS (Homebrew)", command: "brew install ffmpeg" },
  { os: "Windows (winget)", command: "winget install Gyan.FFmpeg" },
  { os: "Windows (Chocolatey)", command: "choco install ffmpeg" },
  { os: "Ubuntu / Debian", command: "sudo apt update && sudo apt install ffmpeg" },
  { os: "Fedora", command: "sudo dnf install ffmpeg" },
  { os: "Arch Linux", command: "sudo pacman -S ffmpeg" },
];

export default function FirstRunSetup({ onRecheck, checking }: FirstRunSetupProps) {
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (command: string) => {
    navigator.clipboard?.writeText(command).then(() => {
      setCopied(command);
      setTimeout(() => setCopied(null), 1500);
    });
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <span className="text-4xl">🛠️</span>
      <h1 className="text-xl font-bold text-slate-50">FFmpeg is required</h1>
      <p className="text-sm text-slate-400">
        Local Media Downloader uses FFmpeg to merge video/audio streams and convert audio formats. It wasn't found
        on this system. Install it with the command for your platform, then recheck.
      </p>

      <div className="flex w-full flex-col gap-2 text-left">
        {INSTRUCTIONS.map((item) => (
          <div
            key={item.os}
            className="flex items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-raised px-4 py-2.5"
          >
            <div>
              <p className="text-xs text-slate-500">{item.os}</p>
              <code className="text-sm text-slate-200">{item.command}</code>
            </div>
            <button
              type="button"
              onClick={() => copy(item.command)}
              className="rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-400 hover:border-slate-500"
            >
              {copied === item.command ? "Copied" : "Copy"}
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={onRecheck}
        disabled={checking}
        className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
      >
        {checking ? "Checking…" : "Recheck"}
      </button>
    </div>
  );
}
