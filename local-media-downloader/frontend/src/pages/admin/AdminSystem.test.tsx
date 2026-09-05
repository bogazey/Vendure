import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import AdminSystem from "./AdminSystem";
import { api } from "../../services/api";
import type { AdminHealthOut } from "../../types/commercial";

vi.mock("../../services/api", () => ({
  api: { adminGetHealth: vi.fn() },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminSystem />
    </MemoryRouter>
  );
}

describe("AdminSystem", () => {
  it("never displays absolute filesystem paths, even though the backend health snapshot could carry them", async () => {
    // AdminHealthOut has no ffmpeg_path/download_dir fields at all (see
    // types/commercial.ts) - this cast simulates a hypothetical regression
    // where the backend accidentally widened the response, to prove the
    // component itself doesn't render such a field if present.
    vi.mocked(api.adminGetHealth).mockResolvedValue({
      status: "ok",
      database_ok: true,
      ffmpeg_available: true,
      ytdlp_version: "2026.01.01",
      download_dir_writable: true,
      ffmpeg_path: "/opt/homebrew/bin/ffmpeg",
      download_dir: "/Users/someone/local-media-downloader/downloads",
    } as unknown as AdminHealthOut);

    renderPage();

    expect(await screen.findByText("Found")).toBeInTheDocument();
    expect(screen.getByText("Writable")).toBeInTheDocument();
    expect(screen.getByText("2026.01.01")).toBeInTheDocument();
    expect(screen.queryByText(/\/opt\/homebrew/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/Users\//)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\/(opt|Users|home)\//);
  });

  it("shows Ready for a healthy backend and database", async () => {
    vi.mocked(api.adminGetHealth).mockResolvedValue({
      status: "ok",
      database_ok: true,
      ffmpeg_available: true,
      ytdlp_version: "2026.01.01",
      download_dir_writable: true,
    });
    renderPage();

    const readyLabels = await screen.findAllByText("Ready");
    expect(readyLabels.length).toBe(2);
  });
});
