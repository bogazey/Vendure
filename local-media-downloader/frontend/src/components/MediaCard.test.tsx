import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MediaCard from "./MediaCard";
import type { AnalyzeResponse } from "../types/api";

function makeMedia(overrides: Partial<AnalyzeResponse> = {}): AnalyzeResponse {
  return {
    url: "https://www.instagram.com/p/ABC123/",
    platform: "instagram",
    media_type: "video",
    id: "abc123",
    title: "A post",
    uploader: "someone",
    thumbnail: "https://example.com/thumb.jpg",
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
    video_presets: [],
    audio_presets: [],
    advanced_formats: [],
    ...overrides,
  };
}

describe("MediaCard", () => {
  it("shows an Image badge and dimensions for an image result", () => {
    render(
      <MediaCard
        media={makeMedia({
          media_type: "image",
          image_url: "https://example.com/photo.jpg",
          image_width: 1080,
          image_height: 1080,
        })}
      />
    );
    expect(screen.getByText("Image")).toBeInTheDocument();
    expect(screen.getByText("1080 × 1080")).toBeInTheDocument();
  });

  it("shows a Carousel badge when the post has multiple media items", () => {
    render(
      <MediaCard
        media={makeMedia({
          is_playlist: true,
          media_items: [
            { index: 1, media_type: "image", title: null, thumbnail: null, duration: null, image_url: "https://example.com/1.jpg", image_width: null, image_height: null, image_ext: null },
            { index: 2, media_type: "video", title: null, thumbnail: null, duration: 5, image_url: null, image_width: null, image_height: null, image_ext: null },
          ],
        })}
      />
    );
    expect(screen.getByText("Carousel detected")).toBeInTheDocument();
  });

  it("shows the ordinary Playlist badge for a URL-level playlist with no media_items", () => {
    render(<MediaCard media={makeMedia({ is_playlist: true, playlist_count: 20, media_items: [] })} />);
    expect(screen.getByText("Playlist detected")).toBeInTheDocument();
  });
});
