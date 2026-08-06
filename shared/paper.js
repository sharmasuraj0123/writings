/*
 * shared/paper.js — generic reading behaviors for research-paper posts.
 *
 * Provenance: generalized from the inline <script> in
 * what-is-quirq/index.html (that post stays self-contained and does NOT
 * load this file). Every feature is defensive: it no-ops when its hook
 * is absent, so a post may adopt any subset of the markup.
 *
 * Hooks a post may provide:
 *   <main>                 word-count source for reading time, and the
 *                          scope for scroll-spy targets (falls back to body)
 *   #reading-time          element that receives "About N minutes"
 *                          (225 wpm, rounded to 5, minimum 5)
 *   .progress              fixed top bar; width is set in % on scroll
 *   .floating-toc          collapsed TOC; expects a .toc-button, an optional
 *                          .toc-button-label, and .toc-menu a[href="#id"]
 *                          links. Gains .visible past 420px of scroll and
 *                          .open while expanded (Escape / click-outside close)
 *   .contents-rail         fixed rail of a[href="#id"] links; gains .visible
 *                          once the reader nears #introduction (or 420px if
 *                          no #introduction exists)
 *   [id] inside <main>     any element whose id matches a rail/TOC link href
 *                          participates in scroll-spy; the matching links
 *                          get .active
 */
(() => {
  "use strict";

  /* Reading time — #reading-time, computed from main's innerText. */
  const readingTime = document.querySelector("#reading-time");
  if (readingTime) {
    const readingText = document.querySelector("main")?.innerText || "";
    const wordCount = readingText.trim().split(/\s+/).filter(Boolean).length;
    const roundedMinutes = Math.max(5, Math.round(wordCount / 225 / 5) * 5);
    readingTime.textContent = `About ${roundedMinutes} minutes`;
  }

  const progress = document.querySelector(".progress");
  const floatingToc = document.querySelector(".floating-toc");
  const tocButton = floatingToc
    ? floatingToc.querySelector(".toc-button")
    : null;
  const tocButtonLabel = floatingToc
    ? floatingToc.querySelector(".toc-button-label")
    : null;
  const tocLinks = floatingToc
    ? [...floatingToc.querySelectorAll(".toc-menu a")]
    : [];
  const contentsRail = document.querySelector(".contents-rail");
  const railLinks = contentsRail
    ? [...contentsRail.querySelectorAll("a")]
    : [];
  const contentsLinks = [...tocLinks, ...railLinks];
  const introduction = document.querySelector("#introduction");

  /* Floating TOC — open/close, Escape, click-outside, close on navigate. */
  if (floatingToc && tocButton) {
    const setTocOpen = (open) => {
      floatingToc.classList.toggle("open", open);
      tocButton.setAttribute("aria-expanded", String(open));
    };

    tocButton.addEventListener("click", () => {
      setTocOpen(!floatingToc.classList.contains("open"));
    });

    document.addEventListener("click", (event) => {
      if (!floatingToc.contains(event.target)) setTocOpen(false);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && floatingToc.classList.contains("open")) {
        setTocOpen(false);
        tocButton.focus();
      }
    });

    tocLinks.forEach((link) => {
      link.addEventListener("click", () => setTocOpen(false));
    });
  }

  /*
   * Progress bar + nav reveal, rAF-throttled. The bar width is set
   * directly with no transition, so prefers-reduced-motion is honored
   * as-is (paper.css additionally zeroes all transition durations under
   * the reduced-motion media query).
   */
  if (progress || floatingToc || contentsRail) {
    let ticking = false;

    const updateScroll = () => {
      ticking = false;
      if (progress) {
        const available = document.documentElement.scrollHeight - innerHeight;
        progress.style.width =
          (available > 0 ? (scrollY / available) * 100 : 0) + "%";
      }
      if (floatingToc) {
        floatingToc.classList.toggle("visible", scrollY > 420);
      }
      if (contentsRail) {
        const threshold = introduction ? introduction.offsetTop - 180 : 420;
        contentsRail.classList.toggle("visible", scrollY > threshold);
      }
    };

    addEventListener(
      "scroll",
      () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(updateScroll);
      },
      { passive: true },
    );
    updateScroll();
  }

  /*
   * Scroll-spy — observe every element inside <main> (or body) whose id
   * has a corresponding href="#<id>" link in the rail or TOC; highlight
   * those links and update the TOC button label.
   */
  if (contentsLinks.length && "IntersectionObserver" in window) {
    const linkedIds = new Set(
      contentsLinks.map((link) => (link.hash || "").slice(1)).filter(Boolean),
    );
    const scope = document.querySelector("main") || document.body;
    const spyTargets = [...scope.querySelectorAll("[id]")].filter((element) =>
      linkedIds.has(element.id),
    );

    if (spyTargets.length) {
      const sectionObserver = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort(
              (a, b) => a.boundingClientRect.top - b.boundingClientRect.top,
            );

          if (!visible[0]) return;
          const id = visible[0].target.id;

          contentsLinks.forEach((link) => {
            link.classList.toggle("active", link.hash === "#" + id);
          });

          const activeLink = tocLinks.find((link) => link.hash === "#" + id);
          if (activeLink && tocButtonLabel) {
            tocButtonLabel.textContent = activeLink.classList.contains(
              "toc-parent",
            )
              ? activeLink.textContent
              : "§ " + activeLink.textContent.replace(" · ", " ");
          }
        },
        { rootMargin: "-14% 0px -72% 0px", threshold: 0 },
      );

      spyTargets.forEach((section) => sectionObserver.observe(section));
    }
  }
})();
