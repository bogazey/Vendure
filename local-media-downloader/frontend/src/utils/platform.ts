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

/**
 * Cosmetic, client-side-only mirror of the backend's url_detect.py, used
 * purely to show a "we recognize this" badge as someone types into the
 * hero URL input. Never used for validation or authorization - the
 * backend is always the real source of truth for what's supported. Returns
 * null (rather than "unknown") for an empty/unrecognized string so the
 * hero input can distinguish "nothing typed yet" from "not supported".
 */
export function detectPlatformFromUrl(rawUrl: string): Platform | null {
  const url = rawUrl.trim().toLowerCase();
  if (!url) return null;
  if (/(^|\.)youtube\.com|youtu\.be/.test(url)) return "youtube";
  if (/(^|\.)tiktok\.com/.test(url)) return "tiktok";
  if (/(^|\.)instagram\.com/.test(url)) return "instagram";
  if (/(^|\.)facebook\.com|fb\.watch/.test(url)) return "facebook";
  return "unknown";
}
