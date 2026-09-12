import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FormatSelector from "./FormatSelector";
import type { AnalyzeResponse, MediaEntry } from "../types/api";

function makeMedia(overrides: Partial<AnalyzeResponse> = {}): AnalyzeResponse {
  return {
    url: "https://www.instagram.com/p/ABC123/",
    platform: "instagram",
    media_type: "video",
    id: "abc123",
    title: "A post",
    uploader: "someone",
    thumbnail: null,
    duration: null,
    description: null,
    image_url: null,
    image_width: null,
    image_height: null,
    image_ext: null,
    is_playlist: false,
    playlist_title: null,
    playlist_count: null,
    playlist_entries_preview: [],
    media_items: [],
    video_presets: [{ key: "best", label: "Best Available", kind: "video", available: true, height: null, expected_container: "mp4", will_transcode: false }],
    audio_presets: [{ key: "best", label: "Best Audio", kind: "audio", available: true, height: null, expected_container: null, will_transcode: null }],
    advanced_formats: [],
    ...overrides,
  };
}

function makeEntry(overrides: Partial<MediaEntry> = {}): MediaEntry {
  return { index: 1, media_type: "image", title: null, thumbnail: null, duration: null, image_url: null, image_width: null, image_height: null, image_ext: null, ...overrides };
}

describe("FormatSelector", () => {
  it("shows video/audio quality controls for an ordinary video result", () => {
    render(<FormatSelector media={makeMedia()} onStartDownload={vi.fn()} submitting={false} maxResolutionHeight={null} />);
    expect(screen.getByText("Best Available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start download/i })).toBeInTheDocument();
  });

  it("shows the plan's resolution ceiling next to Best Available when the plan is capped", () => {
    render(<FormatSelector media={makeMedia()} onStartDownload={vi.fn()} submitting={false} maxResolutionHeight={720} />);
    expect(screen.getByText("Best Available · Up to 720p on your plan")).toBeInTheDocument();
    expect(screen.queryByText("Best Available", { exact: true })).not.toBeInTheDocument();
  });

  it("shows plain Best Available with no suffix when the plan is uncapped", () => {
    render(<FormatSelector media={makeMedia()} onStartDownload={vi.fn()} submitting={false} maxResolutionHeight={null} />);
    expect(screen.getByText("Best Available")).toBeInTheDocument();
  });

  it("shows a single Download Image action for an image result, with no video/audio controls", () => {
    render(<FormatSelector media={makeMedia({ media_type: "image", image_url: "https://example.com/a.jpg" })} onStartDownload={vi.fn()} submitting={false} maxResolutionHeight={720} />);

    expect(screen.getByRole("button", { name: "Download Image" })).toBeInTheDocument();
    expect(screen.queryByText("Video")).not.toBeInTheDocument();
    expect(screen.queryByText("Audio Only")).not.toBeInTheDocument();
    expect(screen.queryByText("Best Available")).not.toBeInTheDocument();
  });

  it("submits an image download request when Download Image is clicked", async () => {
    const onStartDownload = vi.fn();
    render(<FormatSelector media={makeMedia({ media_type: "image" })} onStartDownload={onStartDownload} submitting={false} maxResolutionHeight={720} />);
    await userEvent.click(screen.getByRole("button", { name: "Download Image" }));

    expect(onStartDownload).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://www.instagram.com/p/ABC123/", media_type: "image" })
    );
  });

  it("renders the carousel picker instead of video/audio controls when media_items is non-empty", () => {
    render(
      <FormatSelector
        media={makeMedia({ is_playlist: true, media_items: [makeEntry({ index: 1 }), makeEntry({ index: 2, media_type: "video", duration: 5 })] })}
        onStartDownload={vi.fn()}
        submitting={false}
        maxResolutionHeight={720}
      />
    );
    expect(screen.getByText("2 items in this post")).toBeInTheDocument();
    expect(screen.queryByText("Best Available")).not.toBeInTheDocument();
  });
});
