import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import CarouselPicker from "./CarouselPicker";
import i18n from "../i18n";
import type { AnalyzeResponse, MediaEntry } from "../types/api";

function makeEntry(overrides: Partial<MediaEntry> = {}): MediaEntry {
  return { index: 1, media_type: "image", title: null, thumbnail: "https://example.com/1.jpg", duration: null, image_url: null, image_width: null, image_height: null, image_ext: null, ...overrides };
}

function makeMedia(items: MediaEntry[]): AnalyzeResponse {
  return {
    url: "https://www.instagram.com/p/ABC123/",
    platform: "instagram",
    media_type: items[0]?.media_type ?? "image",
    id: "abc123",
    title: "A carousel post",
    uploader: "someone",
    thumbnail: null,
    duration: null,
    description: null,
    image_url: null,
    image_width: null,
    image_height: null,
    image_ext: null,
    is_playlist: true,
    playlist_title: null,
    playlist_count: items.length,
    playlist_entries_preview: [],
    media_items: items,
    video_presets: [],
    audio_presets: [],
    advanced_formats: [],
  };
}

describe("CarouselPicker", () => {
  it("renders each item with its image/video indicator", () => {
    const media = makeMedia([
      makeEntry({ index: 1, media_type: "image" }),
      makeEntry({ index: 2, media_type: "video", duration: 8 }),
    ]);
    render(<CarouselPicker media={media} onStartDownload={vi.fn()} submitting={false} />);

    expect(screen.getByText("2 items in this post")).toBeInTheDocument();
    expect(screen.getByText("Image")).toBeInTheDocument();
    expect(screen.getByText("Video")).toBeInTheDocument();
  });

  it("downloads only the individually selected item", async () => {
    const onStartDownload = vi.fn();
    const media = makeMedia([makeEntry({ index: 1 }), makeEntry({ index: 2, media_type: "video" })]);
    render(<CarouselPicker media={media} onStartDownload={onStartDownload} submitting={false} />);

    await userEvent.click(screen.getByRole("checkbox", { name: "Select item 1" }));
    await userEvent.click(screen.getByRole("button", { name: "Download selected" }));

    expect(onStartDownload).toHaveBeenCalledTimes(1);
    expect(onStartDownload).toHaveBeenCalledWith(
      expect.objectContaining({ playlist_item_indices: [1], media_type: "image", playlist_mode: "selected" })
    );
  });

  it("selects all items via Select all and downloads each one", async () => {
    const onStartDownload = vi.fn();
    const media = makeMedia([makeEntry({ index: 1 }), makeEntry({ index: 2, media_type: "video" }), makeEntry({ index: 3 })]);
    render(<CarouselPicker media={media} onStartDownload={onStartDownload} submitting={false} />);

    await userEvent.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByText((_, element) => element?.textContent === "3 items in this post · 3 selected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Download selected" }));

    expect(onStartDownload).toHaveBeenCalledTimes(3);
  });

  it("Download all ignores current selection and downloads every item", async () => {
    const onStartDownload = vi.fn();
    const media = makeMedia([makeEntry({ index: 1 }), makeEntry({ index: 2, media_type: "video" })]);
    render(<CarouselPicker media={media} onStartDownload={onStartDownload} submitting={false} />);

    await userEvent.click(screen.getByRole("button", { name: "Download all" }));
    expect(onStartDownload).toHaveBeenCalledTimes(2);
  });

  it("disables Download selected until something is checked", () => {
    const media = makeMedia([makeEntry({ index: 1 })]);
    render(<CarouselPicker media={media} onStartDownload={vi.fn()} submitting={false} />);
    expect(screen.getByRole("button", { name: "Download selected" })).toBeDisabled();
  });

  it("renders in Arabic with translated labels", async () => {
    await i18n.changeLanguage("ar");
    const media = makeMedia([makeEntry({ index: 1 }), makeEntry({ index: 2, media_type: "video" })]);
    render(<CarouselPicker media={media} onStartDownload={vi.fn()} submitting={false} />);

    expect(screen.getByText("عنصر في هذا المنشور", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تحديد الكل" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تنزيل المحدد" })).toBeInTheDocument();
    expect(screen.getByText("صورة")).toBeInTheDocument();
    expect(screen.getByText("فيديو")).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });
});
