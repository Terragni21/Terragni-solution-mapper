/*
 * Terragni site-wide behaviour (every page):
 *   - header gets a solid background once the page scrolls
 *   - elements with .reveal animate in when they enter the screen
 *     (common blocks are tagged automatically)
 *   - [data-count] numbers count up when visible
 */
(function () {
    "use strict";

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---------- Header state ---------- */

    function bindHeader() {
        const header = document.querySelector(".site-header");
        if (!header) return;

        const update = () => header.classList.toggle("is-scrolled", window.scrollY > 24);
        update();
        window.addEventListener("scroll", update, { passive: true });
    }

    /* ---------- Count-up numbers ---------- */

    function countUp(element) {
        if (element.dataset.counted) return;
        element.dataset.counted = "true";

        const target = parseFloat(element.dataset.count);
        if (!Number.isFinite(target)) return;

        const prefix = element.dataset.prefix || "";
        const suffix = element.dataset.suffix || "";

        if (reducedMotion) {
            element.textContent = `${prefix}${target}${suffix}`;
            return;
        }

        const duration = 1600;
        const start = performance.now();

        function frame(now) {
            const progress = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            element.textContent = `${prefix}${Math.round(target * eased)}${suffix}`;
            if (progress < 1) requestAnimationFrame(frame);
        }

        requestAnimationFrame(frame);

        // If animation frames are paused (background tab), still end on the
        // real number.
        setTimeout(() => {
            // Read data-count again: the home page may have updated it with
            // live numbers from /api/stats while counting.
            const latest = parseFloat(element.dataset.count);
            element.textContent = `${prefix}${Number.isFinite(latest) ? latest : target}${suffix}`;
        }, duration + 250);
    }

    /* ---------- Scroll reveal ---------- */

    // Blocks that should animate in even if the HTML did not tag them.
    // Result-page sections are NOT listed: app.js already fades them in
    // (.is-visible), and two systems on one element would conflict.
    const AUTO_REVEAL = [
        ".tv-how-step",
        ".contact-card",
        ".contact-detail",
        ".hero-stats-strip .hero-stat-tile"
    ].join(",");

    let observer = null;

    function observe(root = document) {
        root.querySelectorAll(AUTO_REVEAL).forEach(element => {
            if (!element.classList.contains("reveal")) {
                element.classList.add("reveal");
            }
        });

        // Stagger siblings that reveal together.
        root.querySelectorAll("[data-reveal-stagger]").forEach(group => {
            Array.from(group.children).forEach((child, index) => {
                child.classList.add("reveal");
                child.style.setProperty("--reveal-delay", `${index * 110}ms`);
            });
        });

        const targets = root.querySelectorAll(".reveal:not(.is-revealed), [data-count]:not([data-counted])");

        if (!("IntersectionObserver" in window) || reducedMotion) {
            targets.forEach(element => {
                element.classList.add("is-revealed");
                if (element.dataset.count) countUp(element);
            });
            return;
        }

        if (!observer) {
            observer = new IntersectionObserver(
                entries => {
                    entries.forEach(entry => {
                        if (!entry.isIntersecting) return;
                        const element = entry.target;
                        element.classList.add("is-revealed");
                        if (element.dataset.count !== undefined) countUp(element);
                        observer.unobserve(element);
                    });
                },
                { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
            );
        }

        targets.forEach(element => observer.observe(element));
    }

    /* Result pages are built after load; watch for new content. */
    function watchDynamicContent() {
        const container = document.getElementById("journey-content");
        if (!container || !("MutationObserver" in window)) return;

        let scheduled = false;
        new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            setTimeout(() => {
                scheduled = false;
                observe(container);
                // Results replace the page in one go: make sure what is on
                // screen shows even if the observer has not fired yet.
                setTimeout(revealVisibleNow, 200);

                // app.js fades result sections in on animation frames, which
                // pause in background tabs. Never leave a result page blank.
                setTimeout(() => {
                    document.querySelectorAll("#results .mapper-result-section:not(.is-visible)")
                        .forEach(section => section.classList.add("is-visible"));
                }, 1200);
            }, 30);
        }).observe(container, { childList: true, subtree: true });
    }

    /*
     * Backup for the observer: on scroll, reveal anything already on screen.
     * Content must never stay invisible if IntersectionObserver is slow or
     * unavailable (some embedded browsers, print previews).
     */
    function revealVisibleNow() {
        const limit = window.innerHeight * 0.95;
        document.querySelectorAll(".reveal:not(.is-revealed), [data-count]:not([data-counted])").forEach(element => {
            const top = element.getBoundingClientRect().top;
            if (top < limit) {
                element.classList.add("is-revealed");
                if (element.dataset.count !== undefined) countUp(element);
            }
        });
    }

    function bindRevealFallback() {
        let pending = false;
        window.addEventListener(
            "scroll",
            () => {
                if (pending) return;
                pending = true;
                setTimeout(() => {
                    pending = false;
                    revealVisibleNow();
                }, 150);
            },
            { passive: true }
        );
        window.addEventListener("load", revealVisibleNow);
    }

    /* ---------- Parallax: [data-parallax="0.25"] moves at 25% of scroll ---------- */

    function bindParallax() {
        if (reducedMotion) return;
        const items = Array.from(document.querySelectorAll("[data-parallax]"));
        if (!items.length) return;

        let pending = false;
        const update = () => {
            pending = false;
            const y = window.scrollY;
            items.forEach(item => {
                const speed = parseFloat(item.dataset.parallax) || 0.2;
                item.style.transform = `translateY(${Math.min(y * speed, 220)}px)`;
            });
        };

        window.addEventListener(
            "scroll",
            () => {
                if (!pending) {
                    pending = true;
                    requestAnimationFrame(update);
                }
            },
            { passive: true }
        );
    }

    function init() {
        bindHeader();
        bindParallax();
        observe();
        watchDynamicContent();
        bindRevealFallback();
    }

    window.TerragniSite = { observe, countUp };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
