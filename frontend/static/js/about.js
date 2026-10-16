/*
 * Terragni About page interactions.
 * Site-wide reveal and counters come from site.js.
 */
document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---------- Reading progress + hero parallax + timeline fill ---------- */

    const progressBar = document.getElementById("ab-progress-bar");
    const heroImage = document.querySelector(".ab-hero-media img");
    const timeline = document.getElementById("ab-timeline");
    const timelineFill = document.getElementById("ab-timeline-fill");

    let ticking = false;

    function onScroll() {
        const scrollTop = window.scrollY;
        const max = document.documentElement.scrollHeight - window.innerHeight;

        if (progressBar) {
            progressBar.style.width = `${max > 0 ? (scrollTop / max) * 100 : 0}%`;
        }

        if (heroImage && !reducedMotion) {
            heroImage.style.transform = `translateY(${Math.min(scrollTop * 0.25, 200)}px)`;
        }

        if (timeline && timelineFill) {
            const rect = timeline.getBoundingClientRect();
            const visible = (window.innerHeight * 0.8 - rect.top) / (rect.height + window.innerHeight * 0.3);
            timelineFill.style.width = `${Math.max(0, Math.min(1, visible)) * 100}%`;
        }

        ticking = false;
    }

    window.addEventListener(
        "scroll",
        () => {
            if (!ticking) {
                ticking = true;
                requestAnimationFrame(onScroll);
            }
        },
        { passive: true }
    );
    onScroll();

    /* ---------- Lens: hover a circle to read about that force ---------- */

    const LENS = {
        friction: {
            title: "Friction · what gets in the way",
            text: "Effort, confusion, doubt and broken steps that stop people from acting, even when they want to.",
            color: "#c0563f"
        },
        motivation: {
            title: "Motivation · what drives people",
            text: "The needs, emotions and rewards that make people want to move, and the ones that hold them back.",
            color: "#5f4a9e"
        },
        context: {
            title: "Context · what shapes behaviour",
            text: "The moments, settings, cues and social norms around a decision that tilt behaviour one way or another.",
            color: "#c69b45"
        }
    };

    const detail = document.getElementById("ab-lens-detail");
    const circles = document.querySelectorAll(".ab-venn-c");

    function showLens(key) {
        const item = LENS[key];
        if (!item || !detail) return;

        circles.forEach(circle => circle.classList.toggle("is-active", circle.dataset.lens === key));
        detail.style.borderLeftColor = item.color;
        detail.innerHTML = `<strong>${item.title}</strong><p>${item.text}</p>`;
    }

    circles.forEach(circle => {
        circle.addEventListener("mouseenter", () => showLens(circle.dataset.lens));
        circle.addEventListener("click", () => showLens(circle.dataset.lens));
    });

    /* ---------- 3D tilt on cards ---------- */

    if (!reducedMotion && window.matchMedia("(hover: hover)").matches) {
        document.querySelectorAll(".ab-tilt").forEach(card => {
            card.addEventListener("mousemove", event => {
                const rect = card.getBoundingClientRect();
                const x = (event.clientX - rect.left) / rect.width - 0.5;
                const y = (event.clientY - rect.top) / rect.height - 0.5;
                card.style.transform =
                    `perspective(800px) rotateX(${(-y * 8).toFixed(2)}deg) rotateY(${(x * 8).toFixed(2)}deg) translateY(-4px)`;
            });

            card.addEventListener("mouseleave", () => {
                card.style.transform = "";
            });
        });
    }
});
