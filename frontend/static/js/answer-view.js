/* ============================================================
   TERRAGNI ANSWER VIEW
   One clear page per answer. Every part of the AI response is
   shown exactly once, in the order a consultant would explain it:

   Challenge:  answer -> why it happens -> how we'd solve it
               -> proof -> what could change -> next step
   Knowledge:  answer -> services & methods -> examples -> keep exploring

   app.js calls TerragniAnswer.challenge(...) / .knowledge(...).
   ============================================================ */

(function () {
    "use strict";

    const list = (value) => (Array.isArray(value) ? value.filter(Boolean) : []);

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }


    /* ---------- No-repeat guard ----------
       Remembers every sentence already shown on the page and drops any
       later text that says the same thing again. */

    function createDeduper() {
        const seen = [];
        const STOP = new Set("a an the and or of to for in on with by is are be this that it its your our their from as at".split(" "));

        const words = (text) =>
            new Set(
                String(text || "")
                    .toLowerCase()
                    .replace(/[^a-z0-9\s]/g, " ")
                    .split(/\s+/)
                    .filter((w) => w.length > 2 && !STOP.has(w))
            );

        return function fresh(text) {
            const value = String(text || "").trim();
            if (!value) return "";
            const mine = words(value);
            if (!mine.size) return value;
            for (const other of seen) {
                let shared = 0;
                mine.forEach((w) => other.has(w) && shared++);
                const smaller = Math.min(mine.size, other.size);
                // Short labels ("Low relevance") only count as repeats when identical.
                if (smaller < 4 ? shared === mine.size && shared === other.size : shared / smaller >= 0.7) {
                    return "";
                }
            }
            seen.push(mine);
            return value;
        };
    }


    /* ---------- Icons ---------- */

    const PATHS = {
        why: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5h.01"/>',
        steps: '<path d="M4 18h5v-4h5v-4h6"/><path d="m17 7 3 3-3 3"/>',
        proof: '<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
        change: '<path d="M3 17 9 11l4 4 8-8"/><path d="M15 7h6v6"/>',
        bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z"/>',
        tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4 2.5-2.5Z"/>',
        check: '<path d="m5 12 4.5 4.5L19 7"/>',
        did: '<path d="M4 20h16M6 16l9.5-9.5a2.1 2.1 0 0 1 3 3L9 19H6Z"/>',
        up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
        chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>',
        arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
        book: '<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4Z"/><path d="M20 4h-6a3 3 0 0 0-3 3"/><path d="M20 4v14h-7"/>',
        quote: '<path d="M7 7h4v4c0 3-1.5 5-4 6M14 7h4v4c0 3-1.5 5-4 6"/>',
        eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
        user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
        gift: '<rect x="3" y="8" width="18" height="13" rx="2"/><path d="M12 8v13M3 12h18M12 8S10 3 7.5 4.5 9 8 12 8Zm0 0s2-5 4.5-3.5S15 8 12 8Z"/>'
    };

    const icon = (name) =>
        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name]}</svg>`;


    /* ---------- Building blocks ---------- */

    function section(id, iconName, kicker, title, body, extraClass = "", intro = "") {
        if (!body) return "";
        return `
            <section class="av-section ${extraClass}" id="${id}">
                <header class="av-head av-fade">
                    <span class="av-head-icon">${icon(iconName)}</span>
                    <div>
                        <span class="av-kicker">${esc(kicker)}</span>
                        <h2>${esc(title)}</h2>
                        ${intro ? `<p class="av-intro">${esc(intro)}</p>` : ""}
                    </div>
                </header>
                ${body}
            </section>`;
    }

    // Sticky chapter bar under the hero; highlights the part being read.
    function chapterNav(links) {
        const items = links.filter((l) => l.show);
        if (items.length < 2) return "";
        return `
            <nav class="av-nav" aria-label="In this answer">
                <span class="av-nav-label">In this answer</span>
                <div class="av-nav-links">
                    ${items.map((l) => `<a href="#${l.id}" data-av-jump>${icon(l.icon)}<span>${esc(l.label)}</span></a>`).join("")}
                </div>
                <span class="av-nav-progress" aria-hidden="true"></span>
            </nav>`;
    }

    function hero({ kicker, question, title, lead, badge, badgeLevel, tags, points, role, roleNote }) {
        return `
            <section class="av-hero av-fade" id="av-top">
                <div class="av-hero-main">
                    ${question ? `
                        <p class="av-asked">${icon("quote")}<span><b>You asked</b>${esc(question)}</span></p>` : ""}
                    <div class="av-hero-row">
                        <span class="av-kicker">${esc(kicker)}</span>
                        ${badge ? `<span class="av-badge av-badge-${badgeLevel}">${esc(badge)}</span>` : ""}
                    </div>
                    <h2 class="av-title">${esc(title)}</h2>
                    ${lead ? `<p class="av-lead">${esc(lead)}</p>` : ""}
                    ${points.length ? `
                        <ul class="av-points">
                            ${points.map((p) => `<li>${icon("check")}<span>${esc(p)}</span></li>`).join("")}
                        </ul>` : ""}
                    ${tags.length ? `
                        <div class="av-tags">${tags.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
                </div>
                ${roleNote ? `
                    <div class="av-role">
                        <span class="av-role-icon">${icon("user")}</span>
                        <p><b>Why this matters${role ? ` for a ${esc(role)}` : " for you"}</b>${esc(roleNote)}</p>
                    </div>` : ""}
            </section>`;
    }

    // Plain-language cards (no product names).
    function helpCards(items, fresh) {
        return items
            .map((item) => ({ title: item.title, text: fresh(item.text) }))
            .filter((item) => item.title || item.text)
            .map((item, i) => `
                <article class="av-help av-fade" style="--i:${i}">
                    <span class="av-help-icon">${icon(["bulb", "steps", "change"][i % 3])}</span>
                    <h3>${esc(item.title)}</h3>
                    ${item.text ? `<p>${esc(item.text)}</p>` : ""}
                </article>`)
            .join("");
    }

    function stepList(items) {
        if (!items.length) return "";
        return `
            <ol class="av-steps">
                ${items.map((s, i) => `
                    <li class="av-step av-fade" style="--i:${i}">
                        <span class="av-step-dot">${i + 1}</span>
                        <div>
                            <h3>${esc(s.title)}</h3>
                            ${s.text ? `<p>${esc(s.text)}</p>` : ""}
                            ${s.get ? `<p class="av-step-get">${icon("gift")}<span><b>You get</b>${esc(s.get)}</span></p>` : ""}
                        </div>
                    </li>`).join("")}
            </ol>`;
    }

    function caseCards(items, fresh) {
        return items.map((item) => {
            const problem = fresh(item.their_challenge);
            const did = fresh(item.what_was_done || item.summary);
            const why = did ? "" : fresh(item.why_relevant);
            const result = fresh(item.result || item.outcome);
            const row = (cls, ic, label, text) => text ? `
                <div class="av-case-row ${cls}">
                    <span class="av-case-icon">${icon(ic)}</span>
                    <div><b>${label}</b><p>${esc(text)}</p></div>
                </div>` : "";
            return `
                <article class="av-case av-fade">
                    <span class="av-case-tag">${icon("book")} Terragni case study</span>
                    <h3>${esc(item.title)}</h3>
                    ${row("", "why", "Their challenge", problem)}
                    ${row("", "did", "What Terragni did", did || why)}
                    ${row("av-case-result", "up", "What changed", result)}
                </article>`;
        }).join("");
    }

    function closing(message, extra = "") {
        return `
            <section class="av-close av-fade" id="av-next">
                <div class="av-close-copy">
                    <span class="av-kicker">Next step</span>
                    <h2>${esc(message)}</h2>
                    <p>A Terragni consultant can take this further with you. Your question and this answer are shared automatically.</p>
                </div>
                <div class="av-close-actions">
                    <a class="av-btn av-btn-gold" href="/contact">${icon("chat")} Talk to Terragni</a>
                    <button type="button" class="av-btn av-btn-ghost" data-av-reset>Ask something else</button>
                </div>
                ${extra}
            </section>`;
    }


    /* ---------- Challenge page ---------- */

    function challenge(root, data, ctx = {}) {
        const fresh = createDeduper();
        data = data || {};

        const status = data.match_status || (data.has_terragni_solved_this ? "matched" : "needs_clarification");
        const conf = String(data.match_confidence || "").toLowerCase();
        const badge = status === "matched"
            ? (conf === "high" ? "Terragni has solved this before" : "Related Terragni experience")
            : status === "needs_clarification" ? "A little more detail will help" : "Let's talk it through";
        const badgeLevel = status === "matched" ? (conf === "high" ? "strong" : "medium") : "low";

        const question = ctx.question || data.challenge || "";
        fresh(question);

        const title = fresh(data.conceptual_translation?.business_problem) || "Your challenge, through the Terragni lens";
        const lead = fresh(data.summary) || "";
        const roleNote = fresh(data.for_your_role);

        // 1. Understanding the challenge: symptom vs. reality + journey map
        const seen = fresh(data.what_you_see);
        const insight = fresh(data.perspective);
        const journey = list(data.journey).filter((s) => s.stage);
        const showCompare = Boolean(seen && insight);
        const understandBody = showCompare || journey.length >= 3 ? `
            ${showCompare ? `
                <div class="av-compare av-fade">
                    <div class="av-compare-card">
                        <span class="av-compare-label">${icon("eye")} What you see</span>
                        <p>${esc(seen)}</p>
                    </div>
                    <span class="av-compare-arrow" aria-hidden="true">${icon("arrow")}</span>
                    <div class="av-compare-card av-compare-real">
                        <span class="av-compare-label">${icon("bulb")} What is really happening</span>
                        <p>${esc(insight)}</p>
                    </div>
                </div>` : ""}
            ${journey.length >= 3 ? `
                <h3 class="av-subtitle">Where it happens in the customer journey</h3>
                <ol class="av-journey">
                    ${journey.map((s, i) => `
                        <li class="av-stage av-fade ${s.friction ? "is-friction" : ""}" style="--i:${i}">
                            <span class="av-stage-dot">${s.friction ? "!" : i + 1}</span>
                            <h4>${esc(s.stage)}</h4>
                            ${s.what_happens ? `<p>${esc(s.what_happens)}</p>` : ""}
                            ${s.friction ? `<span class="av-stage-flag">Customers struggle here</span>` : ""}
                        </li>`).join("")}
                </ol>` : ""}` : "";

        // 2. Why it happens
        const reasons = list(data.why_it_happens)
            .map((r) => ({ title: r.title, text: fresh(r.explanation), thought: r.customer_thought }))
            .filter((r) => r.title || r.text);
        const tags = reasons.length ? [] : list(data.areas_of_concern).map(String);
        const whyBody = reasons.length ? `
            <div class="av-reasons">
                ${reasons.map((r, i) => `
                    <article class="av-reason av-fade" style="--i:${i}">
                        <span class="av-reason-num">${i + 1}</span>
                        <h3>${esc(r.title)}</h3>
                        ${r.text ? `<p>${esc(r.text)}</p>` : ""}
                        ${r.thought ? `<blockquote class="av-thought">${icon("chat")}<span>${esc(String(r.thought).replace(/^["“]|["”]$/g, ""))}</span></blockquote>` : ""}
                    </article>`).join("")}
            </div>
            ${insight && !showCompare ? `
                <aside class="av-insight av-fade">
                    <span>${icon("bulb")}</span>
                    <p><b>The Terragni insight</b>${esc(insight)}</p>
                </aside>` : ""}` : "";

        // 3. How Terragni would solve it
        const steps = list(data.approach)
            .map((s) => ({ title: s.title, text: fresh(s.what_we_do), get: fresh(s.you_get) }))
            .filter((s) => s.title || s.text);
        const solveBody = stepList(steps);

        // 4. Ideas to test early
        const ideasHtml = helpCards(list(data.early_ideas), fresh);

        // 5. Proof
        const caseHtml = caseCards(list(data.case_studies), fresh);
        const proofBody = caseHtml ? `<div class="av-cases">${caseHtml}</div>` : "";

        // 6. What could change (+ how to measure it)
        const outcomes = list(data.expected_outcomes)
            .map((o) => (typeof o === "string" ? { outcome: o } : o))
            .filter((o) => o.outcome && fresh(o.outcome));
        const changeBody = outcomes.length ? `
            <div class="av-outcomes">
                ${outcomes.map((o, i) => `
                    <div class="av-outcome av-fade" style="--i:${i}">
                        <span>${icon("change")}</span>
                        <div>
                            <b>${esc(o.outcome)}</b>
                            ${o.how_to_measure ? `<small>How you'd measure it: ${esc(o.how_to_measure)}</small>` : ""}
                        </div>
                    </div>`).join("")}
            </div>` : "";

        // 7. Questions for the first conversation
        const questions = list(data.discussion_questions).map((q) => fresh(q)).filter(Boolean);
        const questionsBody = questions.length ? `
            <ol class="av-questions">
                ${questions.map((q, i) => `<li class="av-fade" style="--i:${i}"><span>${i + 1}</span><p>${esc(q)}</p></li>`).join("")}
            </ol>` : "";

        root.innerHTML = `
            <div class="av-page">
                ${hero({
                    kicker: "The short answer",
                    question, title, lead, badge, badgeLevel, tags,
                    points: [],
                    role: ctx.role,
                    roleNote
                })}
                ${chapterNav([
                    { id: "av-understand", icon: "eye", label: "The challenge", show: Boolean(understandBody) },
                    { id: "av-why", icon: "why", label: "Why it happens", show: Boolean(whyBody) },
                    { id: "av-solve", icon: "steps", label: "Our approach", show: Boolean(solveBody) },
                    { id: "av-ideas", icon: "bulb", label: "Early ideas", show: Boolean(ideasHtml) },
                    { id: "av-proof", icon: "proof", label: "Proof", show: Boolean(proofBody) },
                    { id: "av-change", icon: "change", label: "Results", show: Boolean(changeBody) },
                    { id: "av-questions", icon: "chat", label: "Let's talk", show: Boolean(questionsBody) }
                ])}
                ${section("av-understand", "eye", "Understanding your challenge", "What is really going on", understandBody)}
                ${section("av-why", "why", "The behaviour behind it", "Why this is happening", whyBody, "",
                    "The behavioural reasons, and what your customers may be thinking at that moment.")}
                ${section("av-solve", "steps", "The Terragni approach", "How Terragni would solve it", solveBody, "",
                    "Step by step, and what your bank gets at each step.")}
                ${section("av-ideas", "bulb", "Start small", "Ideas you could test early",
                    ideasHtml ? `<div class="av-helps">${ideasHtml}</div>` : "", "",
                    "Low-risk experiments based on the same behavioural principles.")}
                ${section("av-proof", "proof", "Proof", "Terragni has done this before", proofBody)}
                ${section("av-change", "change", "The result", "What could change for you", changeBody, "av-section-dark")}
                ${section("av-questions", "chat", "Your first conversation", "What we would explore together", questionsBody)}
                ${closing(fresh(data.closing) || "Let's explore this together.")}
            </div>`;

        bind(root);
    }


    /* ---------- Knowledge page ---------- */

    function knowledge(root, data, ctx = {}) {
        const fresh = createDeduper();
        const k = data?.knowledge || {};
        const found = k.answer_found !== false;

        const question = ctx.question || "";
        fresh(question);

        const title = k.title || "What Terragni can tell you";
        const lead = fresh(k.answer) ||
            "This is not covered in Terragni's material yet. Our team will be glad to answer it directly.";
        const points = list(k.key_points).map((p) => fresh(p)).filter(Boolean);
        const roleNote = fresh(k.for_your_role);

        const deep = list(k.deep_dive)
            .map((d) => ({ heading: d.heading, text: fresh(d.text) }))
            .filter((d) => d.heading && d.text);
        const deepBody = deep.length ? `
            <div class="av-accordion">
                ${deep.map((d, i) => `
                    <details class="av-fade" style="--i:${i}" ${i === 0 ? "open" : ""}>
                        <summary><span>${esc(d.heading)}</span></summary>
                        <p>${esc(d.text)}</p>
                    </details>`).join("")}
            </div>` : "";

        const helpHtml = helpCards(list(k.how_it_helps), fresh);
        const steps = list(k.how_it_works)
            .map((s) => ({ title: s.title, text: fresh(s.text) }))
            .filter((s) => s.title || s.text);
        const worksBody = steps.length >= 2 ? stepList(steps) : "";
        const caseHtml = caseCards(list(k.case_studies), fresh);
        const sources = list(k.sources);

        const exploreExtra = `
            ${ctx.chips ? `<div class="av-explore"><b>People also ask</b>${ctx.chips}</div>` : ""}
            ${sources.length ? `<p class="av-sources">${icon("book")} Based on: ${sources.map(esc).join(" · ")}</p>` : ""}`;

        root.innerHTML = `
            <div class="av-page">
                ${hero({
                    kicker: "About Terragni",
                    question, title, lead,
                    badge: found ? "From Terragni's own material" : "Not in our material yet",
                    badgeLevel: found ? "strong" : "low",
                    tags: [],
                    points,
                    role: ctx.role,
                    roleNote
                })}
                ${chapterNav([
                    { id: "av-deep", icon: "why", label: "Go deeper", show: Boolean(deepBody) },
                    { id: "av-help", icon: "bulb", label: "How Terragni helps", show: Boolean(helpHtml) },
                    { id: "av-works", icon: "steps", label: "How it works", show: Boolean(worksBody) },
                    { id: "av-proof", icon: "proof", label: "Examples", show: Boolean(caseHtml) },
                    { id: "av-next", icon: "arrow", label: "Keep exploring", show: true }
                ])}
                ${section("av-deep", "why", "Go deeper", "Your next questions, answered", deepBody)}
                ${section("av-help", "bulb", "How Terragni helps", "What this means for you",
                    helpHtml ? `<div class="av-helps">${helpHtml}</div>` : "")}
                ${section("av-works", "steps", "Working together", "How it typically works", worksBody)}
                ${section("av-proof", "proof", "In practice", "Where Terragni has done this",
                    caseHtml ? `<div class="av-cases">${caseHtml}</div>` : "")}
                ${closing(data?.offer_challenge ? "Want us to look at your own challenge?" : "Keep exploring, or talk to Terragni.", `
                    ${exploreExtra}
                    ${ctx.describe ? `<div class="av-close-more">${ctx.describe}</div>` : ""}`)}
            </div>`;

        bind(root);
    }


    /* ---------- Behaviour: jump links, reset, gentle reveal ---------- */

    function bind(root) {
        root.querySelectorAll("[data-av-jump]").forEach((link) => {
            link.addEventListener("click", (event) => {
                const target = document.querySelector(link.getAttribute("href"));
                if (!target) return;
                event.preventDefault();
                const top = target.getBoundingClientRect().top + window.scrollY - 170;
                window.scrollTo({ top, behavior: "smooth" });
            });
        });

        // Chapter bar: highlight the part being read and show reading progress.
        const nav = root.querySelector(".av-nav");
        if (nav) {
            const links = Array.from(nav.querySelectorAll("[data-av-jump]"));
            const strip = nav.querySelector(".av-nav-links");
            const bar = nav.querySelector(".av-nav-progress");
            const spy = () => {
                let active = null;
                links.forEach((link) => {
                    const target = document.querySelector(link.getAttribute("href"));
                    if (target && target.getBoundingClientRect().top < 200) active = link;
                });
                links.forEach((link) => link.classList.toggle("is-active", link === active));
                if (active && strip) {
                    strip.scrollLeft = active.offsetLeft - strip.clientWidth / 2 + active.clientWidth / 2;
                }
                const page = root.querySelector(".av-page");
                if (bar && page) {
                    const r = page.getBoundingClientRect();
                    const ratio = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - window.innerHeight)));
                    bar.style.transform = `scaleX(${ratio})`;
                }
            };
            if (bind.spy) window.removeEventListener("scroll", bind.spy);
            bind.spy = spy;
            window.addEventListener("scroll", spy, { passive: true });
            spy();
        }

        root.querySelectorAll("[data-av-reset]").forEach((button) => {
            button.addEventListener("click", () => {
                const reset = document.getElementById("reset-btn");
                if (reset) reset.click();
            });
        });

        const items = Array.from(root.querySelectorAll(".av-fade"));
        const show = (el) => el.classList.add("is-in");

        if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            items.forEach(show);
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    show(entry.target);
                    observer.unobserve(entry.target);
                }
            });
        }, { rootMargin: "0px 0px -8% 0px" });

        items.forEach((el) => observer.observe(el));

        // Safety net when the observer does not fire (hidden tab, print, etc.).
        const check = () => {
            const limit = window.innerHeight * 0.95;
            items.forEach((el) => {
                if (!el.classList.contains("is-in") && el.getBoundingClientRect().top < limit) show(el);
            });
        };
        if (bind.check) window.removeEventListener("scroll", bind.check);
        bind.check = check;
        window.addEventListener("scroll", check, { passive: true });
        setTimeout(check, 400);
    }

    window.TerragniAnswer = { challenge, knowledge };
})();
