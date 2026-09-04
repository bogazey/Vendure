import type { Platform } from "../types/api";

export const PLATFORM_LABELS: Record<Platform, string> = {
  youtube: "YouTube",
  tiktok: "TikTok",
  instagram: "Instagram",
  facebook: "Facebook",
  unknown: "Unknown",
};

export const PLATFORM_ICONS: Record<Platform, string> = {
  youtube: "▶",
  tiktok: "♪",
  instagram: "◎",
  facebook: "f",
  unknown: "?",
};

export const PLATFORM_COLORS: Record<Platform, string> = {
  youtube: "bg-red-500/15 text-red-400 border-red-500/30",
  tiktok: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30",
  instagram: "bg-pink-500/15 text-pink-300 border-pink-500/30",
  facebook: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  unknown: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};
