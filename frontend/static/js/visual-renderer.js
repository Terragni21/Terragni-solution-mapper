/* ============================================================
   TERRAGNI SOLUTION MAPPER
   VISUAL RENDERER
   ------------------------------------------------------------
   Converts the visual plan created by visual-planner.js into
   actual DOM / SVG visuals.

   This file is intentionally:
   - industry agnostic
   - solution agnostic
   - safe for AI-generated text
   - responsive
   - accessible
   - compatible with the Terragni visual system

   Depends on:
   - visual-planner.js
   - style.css

   Public API:
   window.TerragniVisualRenderer
   ============================================================ */

(function () {

    "use strict";


    /* =========================================================
       CONFIGURATION
       ========================================================= */

    const CONFIG = {
        maxVisuals: 4,
        maxTextLength: 420,
        maxNodeLength: 90,
        animationDelay: 80
    };


    /* =========================================================
       BASIC UTILITIES
       ========================================================= */

    function isString(value) {
        return typeof value === "string" && value.trim().length > 0;
    }


    function cleanText(value, fallback = "") {

        if (value === null || value === undefined) {
            return fallback;
        }

        if (typeof value === "string") {
            return value.trim();
        }

        if (typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }

        return fallback;
    }


    function truncate(value, length = CONFIG.maxTextLength) {

        const text = cleanText(value);

        if (!text) {
            return "";
        }

        if (text.length <= length) {
            return text;
        }

        return text.slice(0, length).trimEnd() + "…";
    }


    function escapeHtml(value) {

        const text = cleanText(value);

        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }


    function escapeAttribute(value) {
        return escapeHtml(value);
    }


    function safeArray(value) {

        if (!Array.isArray(value)) {
            return [];
        }

        return value;
    }


    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }


    function slug(value) {

        return cleanText(value)
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "")
            .slice(0, 80);
    }


    function createElement(tag, className = "", attributes = {}) {

        const element = document.createElement(tag);

        if (className) {
            element.className = className;
        }

        Object.entries(attributes).forEach(([key, value]) => {

            if (
                value !== null &&
                value !== undefined
            ) {
                element.setAttribute(
                    key,
                    String(value)
                );
            }

        });

        return element;
    }


    /* =========================================================
       VISUAL SHELL
       ========================================================= */

    function createVisualShell(spec, index) {

        const type = cleanText(spec.type, "visual");

        const id =
            cleanText(spec.id) ||
            `terragni-visual-${index + 1}`;

        const title =
            cleanText(
                spec.title,
                "Visual explanation"
            );

        const purpose =
            cleanText(spec.purpose);


        const wrapper = createElement(
            "article",
            `mapper-visual mapper-visual--${slug(type)}`,
            {
                "data-visual-id": id,
                "data-visual-type": type,
                "aria-label": title
            }
        );


        wrapper.style.setProperty(
            "--visual-index",
            String(index)
        );


        const inner = createElement(
            "div",
            "mapper-visual__inner"
        );


        const meta = createElement(
            "div",
            "mapper-visual__meta"
        );

        meta.textContent =
            "TERRAGNI VISUAL EXPLANATION";


        inner.appendChild(meta);


        if (title) {

            const heading = createElement(
                "h3",
                "mapper-visual__title"
            );

            heading.textContent = title;

            inner.appendChild(heading);

        }


        if (purpose) {

            const description = createElement(
                "p",
                "mapper-visual__description"
            );

            description.textContent =
                truncate(purpose, 240);

            inner.appendChild(description);

        }


        wrapper.appendChild(inner);

        return {
            wrapper,
            inner
        };
    }


    /* =========================================================
       FLOW VISUAL
       ========================================================= */

    function renderFlow(spec, index) {

        const shell =
            createVisualShell(spec, index);

        const steps =
            safeArray(spec.data && spec.data.steps)
                .slice(0, 6)
                .filter(step => {

                    return isString(
                        step && step.label
                    );

                });


        if (!steps.length) {
            return null;
        }


        const flow = createElement(
            "div",
            "mapper-flow",
            {
                role: "list",
                "aria-label": "Process flow"
            }
        );


        steps.forEach((step, stepIndex) => {

            const node = createElement(
                "div",
                "mapper-flow-node",
                {
                    role: "listitem"
                }
            );


            const number = createElement(
                "div",
                "mapper-flow-node__number"
            );

            number.textContent =
                String(stepIndex + 1).padStart(2, "0");


            const content = createElement(
                "div",
                "mapper-flow-node__content"
            );


            const label = createElement(
                "strong",
                "mapper-flow-node__label"
            );

            label.textContent =
                truncate(
                    step.label,
                    CONFIG.maxNodeLength
                );


            content.appendChild(label);


            if (isString(step.description)) {

                const description =
                    createElement(
                        "span",
                        "mapper-flow-node__description"
                    );

                description.textContent =
                    truncate(
                        step.description,
                        180
                    );

                content.appendChild(
                    description
                );

            }


            node.appendChild(number);
            node.appendChild(content);


            flow.appendChild(node);


            if (stepIndex < steps.length - 1) {

                const connector =
                    createElement(
                        "div",
                        "mapper-flow-connector",
                        {
                            "aria-hidden": "true"
                        }
                    );

                connector.innerHTML = `
                    <span></span>
                `;

                flow.appendChild(connector);

            }

        });


        shell.inner.appendChild(flow);

        shell.wrapper.classList.add(
            "mapper-visual--flow"
        );

        return shell.wrapper;
    }


    /* =========================================================
       RELATIONSHIP MAP
       ========================================================= */

    function renderRelationshipMap(spec, index) {

        const shell =
            createVisualShell(spec, index);

        const nodes =
            safeArray(
                spec.data && spec.data.nodes
            )
                .map(cleanText)
                .filter(Boolean)
                .slice(0, 9);


        if (!nodes.length) {
            return null;
        }


        const visual = createElement(
            "div",
            "mapper-relationship",
            {
                role: "img",
                "aria-label":
                    "Relationship map showing the forces shaping the situation"
            }
        );


        const core = createElement(
            "div",
            "mapper-relationship-core"
        );

        core.innerHTML = `
            <span class="mapper-relationship-core__eyebrow">
                TERRAGNI
            </span>
            <strong class="mapper-relationship-core__label">
                THE SITUATION
            </strong>
        `;


        visual.appendChild(core);


        const ring = createElement(
            "div",
            "mapper-relationship-ring"
        );


        nodes.forEach((nodeText, nodeIndex) => {

            const angle =
                (360 / nodes.length) *
                nodeIndex;

            const radians =
                angle *
                Math.PI /
                180;


            const radius =
                nodes.length <= 5
                    ? 38
                    : 42;


            const x =
                50 +
                Math.sin(radians) * radius;

            const y =
                50 -
                Math.cos(radians) * radius;


            const node = createElement(
                "div",
                "mapper-relationship-node"
            );


            node.style.left =
                `${clamp(x, 9, 91)}%`;

            node.style.top =
                `${clamp(y, 12, 88)}%`;


            node.setAttribute(
                "title",
                nodeText
            );


            const orb = createElement(
                "span",
                "mapper-relationship-orb"
            );


            const label = createElement(
                "span",
                "mapper-relationship-label"
            );

            label.textContent =
                truncate(
                    nodeText,
                    CONFIG.maxNodeLength
                );


            node.appendChild(orb);
            node.appendChild(label);

            ring.appendChild(node);

        });


        visual.appendChild(ring);


        const insight = createElement(
            "div",
            "mapper-visual-insight"
        );

        insight.textContent =
            `${nodes.length} connected forces identified`;

        visual.appendChild(insight);


        shell.inner.appendChild(visual);

        shell.wrapper.classList.add(
            "mapper-visual--relationship"
        );

        return shell.wrapper;
    }


    /* =========================================================
       TENSION MAP
       ========================================================= */

    function renderTensionMap(spec, index) {

        const shell =
            createVisualShell(spec, index);

        const data =
            spec.data || {};


        const visible =
            cleanText(
                data.visible,
                "Visible symptom"
            );


        const underlying =
            cleanText(
                data.underlying,
                "Underlying issue"
            );


        const friction =
            safeArray(data.friction)
                .map(cleanText)
                .filter(Boolean)
                .slice(0, 4);


        const visual = createElement(
            "div",
            "mapper-tension",
            {
                role: "img",
                "aria-label":
                    "Tension map showing visible symptoms, underlying issues and friction"
            }
        );


        const sides = createElement(
            "div",
            "mapper-tension-sides"
        );


        const visibleSide = createElement(
            "div",
            "mapper-tension-side mapper-tension-side--visible"
        );


        visibleSide.innerHTML = `
            <span class="mapper-tension-side__eyebrow">
                WHAT WE SEE
            </span>
            <strong class="mapper-tension-side__title"></strong>
        `;

        visibleSide
            .querySelector(
                ".mapper-tension-side__title"
            )
            .textContent =
                truncate(visible, 190);


        const underlyingSide = createElement(
            "div",
            "mapper-tension-side mapper-tension-side--underlying"
        );


        underlyingSide.innerHTML = `
            <span class="mapper-tension-side__eyebrow">
                WHAT MAY BE UNDERNEATH
            </span>
            <strong class="mapper-tension-side__title"></strong>
        `;

        underlyingSide
            .querySelector(
                ".mapper-tension-side__title"
            )
            .textContent =
                truncate(underlying, 190);


        sides.appendChild(visibleSide);
        sides.appendChild(underlyingSide);


        const center = createElement(
            "div",
            "mapper-tension-center",
            {
                "aria-hidden": "true"
            }
        );


        center.innerHTML = `
            <span></span>
            <span></span>
            <span></span>
        `;


        visual.appendChild(sides);
        visual.appendChild(center);


        if (friction.length) {

            const frictionWrap =
                createElement(
                    "div",
                    "mapper-tension-friction"
                );


            const frictionLabel =
                createElement(
                    "span",
                    "mapper-tension-friction__label"
                );

            frictionLabel.textContent =
                "FRICTION";


            frictionWrap.appendChild(
                frictionLabel
            );


            const list =
                createElement(
                    "div",
                    "mapper-tension-friction__list"
                );


            friction.forEach(item => {

                const pill =
                    createElement(
                        "span",
                        "mapper-tension-friction__item"
                    );

                pill.textContent =
                    truncate(
                        item,
                        110
                    );

                list.appendChild(pill);

            });


            frictionWrap.appendChild(list);
            visual.appendChild(frictionWrap);

        }


        shell.inner.appendChild(visual);

        shell.wrapper.classList.add(
            "mapper-visual--tension"
        );

        return shell.wrapper;
    }


    /* =========================================================
       TRANSFORMATION VISUAL
       ========================================================= */

    function renderTransformation(spec, index) {

        const shell =
            createVisualShell(spec, index);

        const data =
            spec.data || {};


        const current =
            cleanText(
                data.current,
                "Current condition"
            );


        const intervention =
            cleanText(
                data.intervention,
                "Terragni intervention"
            );


        const desired =
            safeArray(data.desired)
                .map(cleanText)
                .filter(Boolean)
                .slice(0, 3);


        const visual = createElement(
            "div",
            "mapper-transformation",
            {
                role: "img",
                "aria-label":
                    "Transformation from current condition through intervention to desired outcomes"
            }
        );


        const stateCurrent =
            createTransformationState(
                "01",
                "TODAY",
                current,
                "current"
            );


        const stateIntervention =
            createTransformationState(
                "02",
                "THE SHIFT",
                intervention,
                "intervention"
            );


        const stateDesired =
            createTransformationState(
                "03",
                "WHAT CHANGES",
                desired.length
                    ? desired.join(" • ")
                    : "Desired condition",
                "desired"
            );


        visual.appendChild(
            stateCurrent
        );


        visual.appendChild(
            createTransformationArrow()
        );


        visual.appendChild(
            stateIntervention
        );


        visual.appendChild(
            createTransformationArrow()
        );


        visual.appendChild(
            stateDesired
        );


        shell.inner.appendChild(visual);

        shell.wrapper.classList.add(
            "mapper-visual--transformation"
        );

        return shell.wrapper;
    }


    function createTransformationState(
        number,
        eyebrow,
        text,
        modifier
    ) {

        const state =
            createElement(
                "div",
                `mapper-transformation-state mapper-transformation-state--${modifier}`
            );


        const numberEl =
            createElement(
                "span",
                "mapper-transformation-state__number"
            );

        numberEl.textContent =
            number;


        const eyebrowEl =
            createElement(
                "span",
                "mapper-transformation-state__eyebrow"
            );

        eyebrowEl.textContent =
            eyebrow;


        const textEl =
            createElement(
                "strong",
                "mapper-transformation-state__text"
            );

        textEl.textContent =
            truncate(text, 190);


        state.appendChild(
            numberEl
        );

        state.appendChild(
            eyebrowEl
        );

        state.appendChild(
            textEl
        );


        return state;
    }


    function createTransformationArrow() {

        const arrow =
            createElement(
                "div",
                "mapper-transformation-arrow",
                {
                    "aria-hidden": "true"
                }
            );


        arrow.innerHTML = `
            <span></span>
        `;


        return arrow;
    }


    /* =========================================================
       CONCEPTUAL / EDITORIAL VISUAL
       ---------------------------------------------------------
       The planner provides a conceptual-image specification,
       not an actual image URL.

       Therefore we deliberately render an editorial
       abstraction instead of pretending an AI image exists.

       This gives us a visual fallback that still communicates
       the concept beautifully without external image APIs.
       ========================================================= */

    function renderConceptualImage(spec, index) {

        const shell =
            createVisualShell(spec, index);


        const context =
            spec.promptContext || {};


        const perspective =
            cleanText(
                context.perspective,
                context.direction,
                "A human-centred shift"
            );


        const challenge =
            cleanText(
                context.challenge,
                "The challenge"
            );


        const direction =
            cleanText(
                context.direction,
                "A clearer direction"
            );


        const visual =
            createElement(
                "div",
                "mapper-concept",
                {
                    role: "img",
                    "aria-label":
                        "Editorial conceptual representation of the Terragni perspective"
                }
            );


        const field =
            createElement(
                "div",
                "mapper-concept__field"
            );


        /* Large editorial rings */

        for (let i = 0; i < 3; i++) {

            const ring =
                createElement(
                    "div",
                    `mapper-concept-ring mapper-concept-ring--${i + 1}`
                );

            field.appendChild(
                ring
            );

        }


        /* Central idea */

        const core =
            createElement(
                "div",
                "mapper-concept-core"
            );


        const coreEyebrow =
            createElement(
                "span",
                "mapper-concept-core__eyebrow"
            );

        coreEyebrow.textContent =
            "THE TERRAGNI SHIFT";


        const coreTitle =
            createElement(
                "strong",
                "mapper-concept-core__title"
            );

        coreTitle.textContent =
            truncate(
                perspective,
                120
            );


        core.appendChild(
            coreEyebrow
        );

        core.appendChild(
            coreTitle
        );


        field.appendChild(
            core
        );


        /* Satellite ideas */

        const satellites = [
            {
                label: "CHALLENGE",
                text: challenge
            },
            {
                label: "DIRECTION",
                text: direction
            }
        ];


        satellites.forEach(
            (item, itemIndex) => {

                const satellite =
                    createElement(
                        "div",
                        `mapper-concept-satellite mapper-concept-satellite--${itemIndex + 1}`
                    );


                const label =
                    createElement(
                        "span",
                        "mapper-concept-satellite__label"
                    );

                label.textContent =
                    item.label;


                const text =
                    createElement(
                        "strong",
                        "mapper-concept-satellite__text"
                    );

                text.textContent =
                    truncate(
                        item.text,
                        100
                    );


                satellite.appendChild(
                    label
                );

                satellite.appendChild(
                    text
                );


                field.appendChild(
                    satellite
                );

            }
        );


        visual.appendChild(
            field
        );


        const note =
            createElement(
                "div",
                "mapper-visual-insight"
            );

        note.textContent =
            "A conceptual reading of the central idea — not a literal representation.";

        visual.appendChild(
            note
        );


        shell.inner.appendChild(
            visual
        );


        shell.wrapper.classList.add(
            "mapper-visual--concept"
        );


        return shell.wrapper;
    }


    /* =========================================================
       GENERIC VISUAL DISPATCHER
       ========================================================= */

    function renderVisual(spec, index = 0) {

        if (!spec || typeof spec !== "object") {
            return null;
        }


        const type =
            cleanText(spec.type)
                .toLowerCase();


        switch (type) {

            case "flow":
                return renderFlow(
                    spec,
                    index
                );


            case "relationship_map":
                return renderRelationshipMap(
                    spec,
                    index
                );


            case "tension_map":
                return renderTensionMap(
                    spec,
                    index
                );


            case "transformation":
                return renderTransformation(
                    spec,
                    index
                );


            case "editorial_concept":
                return renderConceptualImage(
                    spec,
                    index
                );


            default:
                return null;
        }

    }


    /* =========================================================
       PLAN NORMALISATION
       ========================================================= */

    function normalisePlan(plan) {

        if (!plan || typeof plan !== "object") {

            return {
                visual_needed: false,
                visuals: []
            };

        }


        const visuals =
            safeArray(plan.visuals)
                .filter(
                    item =>
                        item &&
                        typeof item === "object"
                )
                .slice(
                    0,
                    CONFIG.maxVisuals
                );


        return {
            ...plan,
            visuals
        };
    }


    /* =========================================================
       CLEAR CONTAINER
       ========================================================= */

    function clearContainer(container) {

        if (!container) {
            return;
        }

        while (container.firstChild) {
            container.removeChild(
                container.firstChild
            );
        }

    }


    /* =========================================================
       RENDER COMPLETE PLAN
       ========================================================= */

    function renderVisualPlan(
        plan,
        options = {}
    ) {

        const normalised =
            normalisePlan(plan);


        let container =
            options.container;


        if (
            typeof container === "string"
        ) {

            container =
                document.querySelector(
                    container
                );

        }


        if (!container) {

            container =
                document.getElementById(
                    "visual-plan-container"
                );

        }


        if (!container) {

            console.warn(
                "[Terragni Visual Renderer] No visual container found."
            );

            return {
                rendered: 0,
                skipped: normalised.visuals.length
            };

        }


        clearContainer(
            container
        );


        if (
            normalised.visual_needed === false ||
            !normalised.visuals.length
        ) {

            container.classList.remove(
                "has-visuals"
            );

            container.setAttribute(
                "data-visual-count",
                "0"
            );

            return {
                rendered: 0,
                skipped: 0
            };

        }


        container.classList.add(
            "has-visuals"
        );


        container.setAttribute(
            "data-visual-count",
            String(
                normalised.visuals.length
            )
        );


        const grid =
            createElement(
                "div",
                "mapper-visual-plan__grid"
            );


        let rendered = 0;


        normalised.visuals.forEach(
            (spec, index) => {

                const visual =
                    renderVisual(
                        spec,
                        index
                    );


                if (!visual) {
                    return;
                }


                const placement =
                    cleanText(
                        spec.placement
                    );


                visual.setAttribute(
                    "data-visual-placement",
                    placement
                );


                grid.appendChild(
                    visual
                );


                rendered++;

            }
        );


        if (!rendered) {

            container.classList.remove(
                "has-visuals"
            );

            return {
                rendered: 0,
                skipped:
                    normalised.visuals.length
            };

        }


        container.appendChild(
            grid
        );


        requestAnimationFrame(
            () => {

                const visuals =
                    container.querySelectorAll(
                        ".mapper-visual"
                    );


                visuals.forEach(
                    (visual, index) => {

                        visual.style.setProperty(
                            "--visual-delay",
                            `${index * CONFIG.animationDelay}ms`
                        );


                        visual.classList.add(
                            "is-visible"
                        );

                    }
                );

            }
        );


        return {
            rendered,
            skipped:
                normalised.visuals.length -
                rendered
        };

    }


    /* =========================================================
       RENDER BY PLACEMENT
       ---------------------------------------------------------
       This lets app.js optionally place each visual directly
       near the journey section it belongs to.
       ========================================================= */

    function getPlacementContainer(
        placement
    ) {

        const map = {
            interpretation:
                "visual-mount-interpretation",

            challenge_anatomy:
                "visual-mount-challenge-anatomy",

            how_it_works:
                "visual-mount-how-it-works",

            outcomes:
                "visual-mount-outcomes",

            direction:
                "visual-mount-direction"
        };


        const id =
            map[
                cleanText(placement)
            ];


        if (!id) {
            return null;
        }


        return document.getElementById(
            id
        );

    }


    function renderVisualsByPlacement(
        plan,
        options = {}
    ) {

        const normalised =
            normalisePlan(plan);


        const results = [];


        normalised.visuals.forEach(
            (spec, index) => {

                const container =
                    getPlacementContainer(
                        spec.placement
                    );


                if (!container) {
                    return;
                }


                const visual =
                    renderVisual(
                        spec,
                        index
                    );


                if (!visual) {
                    return;
                }


                clearContainer(
                    container
                );


                container.classList.add(
                    "has-visual"
                );


                container.setAttribute(
                    "aria-hidden",
                    "false"
                );


                container.appendChild(
                    visual
                );


                requestAnimationFrame(
                    () => {

                        visual.classList.add(
                            "is-visible"
                        );

                    }
                );


                results.push({
                    id: spec.id,
                    placement:
                        spec.placement,
                    rendered: true
                });

            }
        );


        return results;

    }


    /* =========================================================
       AUTO RENDER HELPER
       ========================================================= */

    function renderFromSolution(
        solution,
        options = {}
    ) {

        if (
            !window.TerragniVisualPlanner ||
            typeof
                window.TerragniVisualPlanner
                    .createVisualPlan !==
                "function"
        ) {

            console.warn(
                "[Terragni Visual Renderer] visual-planner.js is not available."
            );

            return null;

        }


        const plan =
            window.TerragniVisualPlanner
                .createVisualPlan(
                    solution
                );


        if (options.byPlacement) {

            renderVisualsByPlacement(
                plan,
                options
            );

        }


        const container =
            options.container ||
            document.getElementById(
                "visual-plan-container"
            );


        if (
            container &&
            options.byPlacement !== true
        ) {

            renderVisualPlan(
                plan,
                {
                    ...options,
                    container
                }
            );

        }


        return plan;

    }


    /* =========================================================
       CLEAR ALL VISUALS
       ========================================================= */

    function clearVisuals() {

        const main =
            document.getElementById(
                "visual-plan-container"
            );


        if (main) {
            clearContainer(main);

            main.classList.remove(
                "has-visuals"
            );

            main.setAttribute(
                "data-visual-count",
                "0"
            );
        }


        const mounts =
            document.querySelectorAll(
                ".mapper-visual-mount"
            );


        mounts.forEach(
            mount => {

                clearContainer(
                    mount
                );

                mount.classList.remove(
                    "has-visual"
                );

                mount.setAttribute(
                    "aria-hidden",
                    "true"
                );

            }
        );

    }


    /* =========================================================
       DEBUG HELPERS
       ========================================================= */

    function inspectPlan(plan) {

        if (!plan) {

            console.info(
                "[Terragni Visual Renderer] No visual plan."
            );

            return;

        }


        console.group(
            "[Terragni Visual Renderer]"
        );

        console.log(
            "Visual needed:",
            plan.visual_needed
        );

        console.log(
            "Signals:",
            plan.signals
        );

        console.log(
            "Visuals:",
            plan.visuals
        );

        console.groupEnd();

    }


    /* =========================================================
       PUBLIC API
       ========================================================= */

    window.TerragniVisualRenderer = {

        renderVisual,

        renderVisualPlan,

        renderVisualsByPlacement,

        renderFromSolution,

        clearVisuals,

        inspectPlan

    };


    /* =========================================================
       READY
       ========================================================= */

    if (
        document.readyState === "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            () => {

                document.documentElement
                    .classList.add(
                        "terragni-visual-renderer-ready"
                    );

            },
            {
                once: true
            }
        );

    } else {

        document.documentElement
            .classList.add(
                "terragni-visual-renderer-ready"
            );

    }


})();