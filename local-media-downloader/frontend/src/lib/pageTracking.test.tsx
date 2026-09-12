import { StrictMode } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { usePageViewTracking } from "./pageTracking";
import { api } from "../services/api";

vi.mock("../services/api", () => ({
  api: { trackEvent: vi.fn() },
}));

function Probe() {
  usePageViewTracking();
  return <div>probe</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<Probe />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(api.trackEvent).mockReset();
  vi.mocked(api.trackEvent).mockResolvedValue(undefined as never);
});

describe("usePageViewTracking", () => {
  it("fires exactly one page_view even under React 18 StrictMode's double-invoked effect", () => {
    render(
      <StrictMode>
        <MemoryRouter initialEntries={["/pricing"]}>
          <Routes>
            <Route path="*" element={<Probe />} />
          </Routes>
        </MemoryRouter>
      </StrictMode>
    );

    expect(api.trackEvent).toHaveBeenCalledTimes(1);
    expect(api.trackEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: "page_view", path: "/pricing" })
    );
  });

  it("fires again after navigating to a different path", () => {
    renderAt("/pricing");
    expect(api.trackEvent).toHaveBeenCalledTimes(1);

    renderAt("/dashboard");
    expect(api.trackEvent).toHaveBeenCalledTimes(2);
    expect(api.trackEvent).toHaveBeenLastCalledWith(expect.objectContaining({ path: "/dashboard" }));
  });

  it("does not break rendering when the tracking call rejects (fails silently)", async () => {
    vi.mocked(api.trackEvent).mockRejectedValue(new Error("network down"));
    expect(() => renderAt("/dashboard")).not.toThrow();
  });

  it("includes utm parameters from the URL when present", () => {
    render(
      <MemoryRouter initialEntries={["/pricing?utm_source=newsletter&utm_medium=email&utm_campaign=launch"]}>
        <Routes>
          <Route path="*" element={<Probe />} />
        </Routes>
      </MemoryRouter>
    );

    expect(api.trackEvent).toHaveBeenCalledWith(
      expect.objectContaining({ utm_source: "newsletter", utm_medium: "email", utm_campaign: "launch" })
    );
  });
});
