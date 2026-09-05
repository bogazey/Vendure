import { useState } from "react";
import LoadyLogo from "./LoadyLogo";

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
    <div className="relative z-10 mx-auto flex min-h-[70vh] max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <LoadyLogo size={40} withWordmark={false} />
      <h1 className="font-display text-xl font-bold text-slate-50">FFmpeg is required</h1>
      <p className="text-sm text-slate-400">
        Loady uses FFmpeg to merge video/audio streams and convert audio formats. It wasn't found on this system.
        Install it with the command for your platform, then recheck.
      </p>

      <div className="flex w-full flex-col gap-2 text-left">
        {INSTRUCTIONS.map((item) => (
          <div key={item.os} className="glass-panel flex items-center justify-between gap-3 px-4 py-2.5">
            <div>
              <p className="text-xs text-slate-500">{item.os}</p>
              <code className="text-sm text-slate-200">{item.command}</code>
            </div>
            <button
              type="button"
              onClick={() => copy(item.command)}
              className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-slate-400 hover:border-white/30"
            >
              {copied === item.command ? "Copied" : "Copy"}
            </button>
          </div>
        ))}
      </div>

      <button type="button" onClick={onRecheck} disabled={checking} className="btn-gradient">
        {checking ? "Checking…" : "Recheck"}
      </button>
    </div>
  );
}
