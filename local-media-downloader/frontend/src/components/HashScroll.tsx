import { useEffect } from "react";
import { useLocation } from "react-router-dom";

function getScrollContainer(): HTMLElement {
  const body = document.body;
  const bodyOverflow = window.getComputedStyle(body).overflowY;
  const bodyOwnsScroll = /^(auto|scroll|overlay)$/.test(bodyOverflow)
    && body.scrollHeight > body.clientHeight;

  return bodyOwnsScroll
    ? body
    : (document.scrollingElement as HTMLElement | null) ?? document.documentElement;
}

/** Restores route scroll position after the destination view has mounted. */
export default function HashScroll() {
  const { hash, pathname } = useLocation();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      if (!hash) {
        getScrollContainer().scrollTo({ top: 0, left: 0, behavior: "auto" });
        return;
      }

      const id = decodeURIComponent(hash.slice(1));
      const target = document.getElementById(id);
      if (!target) return;

      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [hash, pathname]);

  return null;
}
