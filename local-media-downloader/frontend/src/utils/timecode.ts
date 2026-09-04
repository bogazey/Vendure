const PATTERN = /^(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)$/;

export function parseTimecode(value: string): number {
  const match = PATTERN.exec(value.trim());
  if (!match) {
    throw new Error(`Invalid timecode '${value}'. Expected HH:MM:SS or MM:SS.`);
  }
  const hours = match[1] ? parseInt(match[1], 10) : 0;
  const minutes = parseInt(match[2], 10);
  const seconds = parseInt(match[3], 10);
  return hours * 3600 + minutes * 60 + seconds;
}
