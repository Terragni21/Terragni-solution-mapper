document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    /* ============================================================
       TERRAGNI SOLUTION MAPPER
       COMPLETE RESULT JOURNEY

       IMPORTANT:
       - /api/query contract is unchanged.
       - Backend / JUMP / ranking logic is untouched.
       - This file controls how the returned answer becomes
         a coherent customer-facing solution journey.
       ============================================================ */


    /* ============================================================
       HELPERS
       ============================================================ */

    const $ = (selector, root = document) =>
        root.querySelector(selector);

    const $$ = (selector, root = document) =>
        Array.from(root.querySelectorAll(selector));

    const firstElement = (selectors) => {
        for (const selector of selectors) {
            const element = $(selector);
            if (element) return element;
        }

        return null;
    };

    const valueOf = (element) =>
        element ? String(element.value || "").trim() : "";

    const text = (value) => {
        if (value === null || value === undefined) return "";

        if (
            typeof value === "string" ||
            typeof value === "number" ||
            typeof value === "boolean"
        ) {
            return String(value).trim();
        }

        return "";
    };

    const asArray = (value) =>
        Array.isArray(value) ? value : [];

    const firstMeaningful = (...values) => {
        for (const value of values) {
            const result = text(value);

            if (result) {
                return result;
            }
        }

        return "";
    };

    const escapeHtml = (value) => {
        if (value === null || value === undefined) {
            return "";
        }

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    };

    const show = (element) => {
        if (element) {
            element.classList.remove("hidden");
        }
    };

    const hide = (element) => {
        if (element) {
            element.classList.add("hidden");
        }
    };

    const getName = (item) => {
        if (typeof item === "string") {
            return item.trim();
        }

        if (!item || typeof item !== "object") {
            return "";
        }

        return firstMeaningful(
            item.name,
            item.title,
            item.label,
            item.public_title,
            item.framework_name,
            item.offering_name,
            item.outcome_name
        );
    };

    const getDescription = (item) => {
        if (typeof item === "string") {
            return "";
        }

        if (!item || typeof item !== "object") {
            return "";
        }

        return firstMeaningful(
            item.description,
            item.summary,
            item.explanation,
            item.details,
            item.detail,
            item.what_it_is,
            item.approach,
            item.what_happens
        );
    };

    const getWhy = (item) => {
        if (!item || typeof item !== "object") {
            return "";
        }

        return firstMeaningful(
            item.why_relevant,
            item.relevance,
            item.reason,
            item.fit,
            item.why_it_fits,
            item.why
        );
    };

    const getSteps = (item) => {
        if (!item || typeof item !== "object") {
            return [];
        }

        return asArray(
            item.steps ||
            item.how_it_works ||
            item.approach ||
            item.process ||
            item.stages
        );
    };

    const scrollToElement = (
        element,
        offset = 30
    ) => {
        if (!element) return;

        const top =
            element.getBoundingClientRect().top +
            window.scrollY -
            offset;

        window.scrollTo({
            top: Math.max(0, top),
            behavior: "smooth"
        });
    };


    /* ============================================================
       DOM
       ============================================================ */

    const form = firstElement([
        "#query-form",
        "form[data-query-form]"
    ]);

    const challengeInput = firstElement([
        "#query-input",
        "#challenge-input",
        "#challenge",
        "textarea[name='challenge']",
        "textarea[name='query']"
    ]);

    const industryInput = firstElement([
        "#industry-input",
        "#industry",
        "#industryInput",
        "input[name='industry']",
        "select[name='industry']"
    ]);

    const roleSelect = document.getElementById("role-select");

    const roleInput = firstElement([
        "#role-input",
        "#role",
        "#roleInput",
        "#designation",
        "input[name='role']",
        "input[name='designation']",
        "select[name='role']"
    ]);

    const submitButton = firstElement([
        "#submit-btn",
        "button[type='submit']"
    ]);

    const hero = $("#hero");
    const loading = $("#loading");
    const results = $("#results");
    const resetButton = $("#reset-btn");

    const dynamicTitle = $("#dynamic-title");
    const problemSummary = $("#problem-summary");
    const resultContext = $("#result-context");

    const matchStatusPanel =
        $("#match-status-panel");

    const journeyContent =
        $("#journey-content");

    const clarificationSection =
        $("#clarification-section");

    const clarificationForm =
        $("#clarification-form");

    const clarificationQuestion =
        $("#clarification-question");

    const clarificationInput =
        $("#clarification-input");

    const clarificationSubmitButton =
        $("#clarification-submit-btn");

    const drawer =
        $("#solution-drawer");

    const closeDrawer =
        $("#close-drawer");

    const drawerTitle =
        $("#solution-drawer-title");

    const drawerBody =
        $("#solution-drawer-body");

    const characterCount =
        $("#query-character-count");

    const exploreResultsButton =
        $("#explore-results-btn");


    /* ============================================================
       STATE
       ============================================================ */

    let currentChallenge = "";
    let currentIndustry = "";
    let currentRole = "";
    let currentResponse = null;

    /*
     * Client-side visual interpretation generated by
     * static/js/visual-planner.js.
     *
     * This is intentionally separate from the backend response.
     */
    let currentVisualPlan = null;

    let loadingTimer = null;
    let loadingIndex = 0;

    /*
     * Which path the visitor chose: "challenge" or "knowledge".
     * The backend may still route a question to the other path when the
     * text clearly belongs there (see /api/ask).
     */
    let currentMode = "challenge";


    /* ============================================================
       PATH CHOICE (CHALLENGE / KNOWLEDGE)
       ============================================================ */

    const modeInput = $("#mode-input");
    const pathButtons = $$(".mapper-path-button");
    const exampleChips = $("#example-chips");
    const queryLabel = $("#query-label");

    const PATH_COPY = {
        challenge: {
            label: "What is not working?",
            placeholder:
                "e.g. Customers still come to our branches even though we launched an app.",
            submit: "Explore the challenge →",
            examples: [
                "Customers still come to our branches even though we launched an app.",
                "Our affluent customers are happy but rarely refer anyone.",
                "Our relationship managers do not resolve complaints well.",
                "Customers lose interest after trying to redeem their reward points."
            ]
        },
        knowledge: {
            label: "What would you like to know about Terragni?",
            placeholder:
                "e.g. What does Terragni do for banks?",
            submit: "Ask Terragni →",
            examples: [
                "What does Terragni do for banks?",
                "What is the Effort Assessment Score (EAS)?",
                "How does Experiential Segmentation work?",
                "How does Terragni use behavioural science?"
            ]
        }
    };

    function submitLabel() {
        return PATH_COPY[currentMode]?.submit || PATH_COPY.challenge.submit;
    }

    function renderExamples() {
        if (!exampleChips) return;

        exampleChips.innerHTML =
            PATH_COPY[currentMode].examples
                .map(
                    example => `
                        <button
                            type="button"
                            class="mapper-example-chip"
                            data-example="${escapeHtml(example)}"
                        >
                            ${escapeHtml(example)}
                        </button>
                    `
                )
                .join("");

        $$(".mapper-example-chip", exampleChips).forEach(chip => {
            chip.addEventListener("click", () => {
                if (!challengeInput) return;
                challengeInput.value = chip.dataset.example || "";
                updateCharacterCount();
                challengeInput.focus();
            });
        });
    }

    function setMode(mode) {
        currentMode = mode === "knowledge" ? "knowledge" : "challenge";

        if (modeInput) {
            modeInput.value = currentMode;
        }

        pathButtons.forEach(button => {
            const active = button.dataset.mode === currentMode;
            button.classList.toggle("active", active);
            button.setAttribute("aria-checked", active ? "true" : "false");
        });

        const copy = PATH_COPY[currentMode];

        if (queryLabel) {
            queryLabel.innerHTML = `
                <span class="mapper-step-inline">3</span>
                ${escapeHtml(copy.label)}
            `;
        }

        if (challengeInput) {
            challengeInput.placeholder = copy.placeholder;
        }

        if (submitButton && !submitButton.disabled) {
            submitButton.innerHTML = copy.submit;
        }

        renderExamples();
    }

    pathButtons.forEach(button => {
        button.addEventListener("click", () => {
            setMode(button.dataset.mode);
            setJourneyStep(2);
        });
    });


    /* ============================================================
       CONTACT CONTEXT
       Saved for the contact page so Terragni's team receives the
       visitor's role, industry and diagnosed problem with the lead.
       ============================================================ */

    function saveContactContext(context) {
        try {
            window.sessionStorage.setItem(
                "terragniContactContext",
                JSON.stringify({
                    industry: currentIndustry,
                    role: currentRole,
                    question: currentChallenge,
                    ...context
                })
            );
        } catch (error) {
            /* Storage can be blocked; the contact form still works. */
        }
    }

    function contactCtaHtml(secondary = "") {
        return `
            <div class="mapper-cta-row">
                <a class="mapper-cta-primary" href="/contact">
                    Contact Terragni ↗
                </a>
                ${secondary}
            </div>
        `;
    }


    /* ============================================================
       CHARACTER COUNT
       ============================================================ */

    function updateCharacterCount() {
        if (!challengeInput || !characterCount) {
            return;
        }

        const length =
            String(
                challengeInput.value || ""
            ).length;

        const max =
            challengeInput.maxLength > 0
                ? challengeInput.maxLength
                : 6000;

        characterCount.textContent =
            `${length.toLocaleString()} / ${max.toLocaleString()}`;

        characterCount.classList.toggle(
            "near-limit",
            length >= max * 0.85
        );

        characterCount.classList.toggle(
            "at-limit",
            length >= max
        );
    }


    /* ============================================================
       TOP JOURNEY INDICATOR
       ============================================================ */

    const journeyItems =
        $$(".mapper-journey-item");

    function setJourneyStep(step) {
        journeyItems.forEach(item => {
            const itemStep =
                Number(item.dataset.step || 0);

            item.classList.toggle(
                "active",
                itemStep === step
            );

            item.classList.toggle(
                "completed",
                itemStep < step
            );
        });
    }

    function resetJourneyStep() {
        journeyItems.forEach(item => {
            item.classList.remove(
                "active",
                "completed"
            );
        });

        if (journeyItems[0]) {
            journeyItems[0].classList.add("active");
        }
    }


    /* ============================================================
       ERROR
       ============================================================ */

    function getOrCreateError() {
        let error = $("#mapper-error");

        if (error) {
            return error;
        }

        error = document.createElement("div");
        error.id = "mapper-error";
        error.className = "mapper-error";
        error.setAttribute("role", "alert");

        if (form) {
            form.insertAdjacentElement(
                "afterend",
                error
            );
        }

        return error;
    }

    function showError(message) {
        const error = getOrCreateError();

        if (!error) return;

        error.innerHTML = `
            <span class="error-icon">!</span>
            <span>${escapeHtml(message)}</span>
        `;

        show(error);

        error.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    function clearError() {
        const error = $("#mapper-error");

        if (error) {
            hide(error);
            error.textContent = "";
        }
    }


    /* ============================================================
       VALIDATION
       ============================================================ */

    function validateQuery() {
        const industry =
            valueOf(industryInput);

        const role =
            valueOf(roleInput);

        const challenge =
            valueOf(challengeInput);

        if (!industry) {
            showError(
                "Please tell us your industry."
            );

            industryInput?.focus();
            return false;
        }

        if (!role) {
            showError(
                "Please tell us your role."
            );

            (roleInput && !roleInput.hidden ? roleInput : roleSelect || roleInput)?.focus();
            return false;
        }

        if (!challenge) {
            showError(
                currentMode === "knowledge"
                    ? "Type your question about Terragni first."
                    : "Tell us what is not working before exploring the challenge."
            );

            challengeInput?.focus();
            return false;
        }

        if (challenge.length < (currentMode === "knowledge" ? 5 : 10)) {
            showError(
                "Give us a little more detail so we can understand the situation properly."
            );

            challengeInput?.focus();
            return false;
        }

        if (challenge.length > 6000) {
            showError(
                "Please keep the challenge under 6,000 characters."
            );

            challengeInput?.focus();
            return false;
        }

        return true;
    }


    /* ============================================================
       LOADING
       ============================================================ */

    const challengeLoadingStages = [
        {
            title: "Understanding your challenge",
            copy:
                "Looking beneath the words to understand the business situation."
        },
        {
            title: "Finding the friction",
            copy:
                "Connecting the challenge to the moments where people or organisations may be getting stuck."
        },
        {
            title: "Applying the Terragni lens",
            copy:
                "Looking for relevant patterns, thinking and experience."
        },
        {
            title: "Building your solution",
            copy:
                "Turning the perspective into a practical direction rather than simply repeating the problem."
        }
    ];

    const knowledgeLoadingStages = [
        {
            title: "Reading your question",
            copy: "Working out what you would like to know about Terragni."
        },
        {
            title: "Searching Terragni's material",
            copy: "Looking through brochures, methods and banking case studies."
        },
        {
            title: "Writing a clear answer",
            copy: "Using only Terragni's own material, with the sources shown."
        }
    ];

    let loadingStages = challengeLoadingStages;

    function updateLoadingStage(index) {
        loadingIndex =
            Math.min(
                index,
                loadingStages.length - 1
            );

        $$(".loading-stage").forEach(
            (stage, stageIndex) => {
                stage.classList.toggle(
                    "active",
                    stageIndex === loadingIndex
                );

                stage.classList.toggle(
                    "completed",
                    stageIndex < loadingIndex
                );
            }
        );

        if (!loading) return;

        const message =
            loadingStages[loadingIndex];

        const title =
            $("strong", loading);

        const copy =
            $("p", loading);

        if (title) {
            title.textContent =
                message.title;
        }

        if (copy) {
            copy.textContent =
                message.copy;
        }
    }

    function startLoading() {
        stopLoading();

        loadingStages =
            currentMode === "knowledge"
                ? knowledgeLoadingStages
                : challengeLoadingStages;

        updateLoadingStage(0);

        loadingTimer =
            window.setInterval(() => {
                if (
                    loadingIndex <
                    loadingStages.length - 1
                ) {
                    updateLoadingStage(
                        loadingIndex + 1
                    );
                }
            }, 1600);
    }

    function stopLoading() {
        if (loadingTimer) {
            clearInterval(loadingTimer);
            loadingTimer = null;
        }
    }

    function setLoading(isLoading) {
        if (isLoading) {
            hide(hero);
            hide(results);
            show(loading);

            if (submitButton) {
                submitButton.disabled = true;

                submitButton.innerHTML = `
                    <span class="button-loading">
                        <span class="button-spinner"></span>
                        Exploring…
                    </span>
                `;
            }

            setJourneyStep(3);
            return;
        }

        hide(loading);

        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML =
                submitLabel();
        }
    }


    /* ============================================================
       RESPONSE NORMALISATION
       ============================================================ */

    function getTranslation(data) {
        const value =
            data?.conceptual_translation;

        if (typeof value === "string") {
            return {
                problem: value,
                explanation: ""
            };
        }

        return {
            problem: firstMeaningful(
                value?.business_problem,
                value?.problem,
                value?.summary,
                value?.title
            ),

            explanation: firstMeaningful(
                value?.explanation,
                value?.description,
                value?.detail,
                value?.context
            )
        };
    }

    function getPerspective(data) {
        const perspective =
            data?.perspective;

        if (typeof perspective === "string") {
            return {
                summary: perspective,
                points: [],
                outcomes: []
            };
        }

        return {
            summary: firstMeaningful(
                perspective?.summary,
                perspective?.perspective,
                perspective?.point_of_view,
                perspective?.description,
                data?.perspective_summary
            ),

            points: asArray(
                perspective?.points ||
                perspective?.insights ||
                perspective?.key_points
            ),

            outcomes: asArray(
                perspective?.outcomes ||
                perspective?.expected_outcomes
            )
        };
    }

    function getOfferings(data) {
        return asArray(
            data?.offerings ||
            data?.solutions ||
            data?.directions
        );
    }

    function getPrimaryOffering(data) {
        const offerings =
            getOfferings(data);

        return offerings.length
            ? offerings[0]
            : null;
    }

    function getFrameworks(data) {
        return asArray(
            data?.frameworks ||
            data?.toolkit ||
            data?.methodologies ||
            data?.tools
        );
    }

    function getCases(data) {
        return asArray(
            data?.case_studies ||
            data?.experiences ||
            data?.relevant_experience
        );
    }

    function getEvidence(data) {
        return asArray(
            data?.evidence ||
            data?.retrieval?.evidence
        );
    }

    function getOutcomes(data) {
        return asArray(
            data?.outcomes ||
            data?.expected_outcomes ||
            data?.perspective?.outcomes
        );
    }


    /* ============================================================
       STATUS
       ============================================================ */

    function hasUsableSolution(data) {
        const offerings =
            getOfferings(data);

        const perspective =
            getPerspective(data);

        const translation =
            getTranslation(data);

        return Boolean(
            offerings.length ||
            perspective.summary ||
            translation.problem ||
            data?.solution ||
            data?.solution_name ||
            data?.recommended_solution ||
            data?.has_terragni_solved_this === true
        );
    }

    function normalizeStatus(data) {
        const explicit =
            String(
                data?.match_status ||
                data?.status ||
                ""
            ).toLowerCase();

        if (
            explicit === "matched" ||
            explicit === "needs_clarification" ||
            explicit === "not_supported"
        ) {
            /*
             * A backend clarification flag should not erase a useful
             * solution if the same response already contains solution
             * material.
             */
            if (
                explicit === "needs_clarification" &&
                hasUsableSolution(data)
            ) {
                return "matched";
            }

            return explicit;
        }

        if (hasUsableSolution(data)) {
            return "matched";
        }

        if (
            asArray(
                data?.probing_questions
            ).length
        ) {
            return "needs_clarification";
        }

        return "not_supported";
    }


    /* ============================================================
       CLEAR RESULT
       ============================================================ */

    function clearResult() {
        if (journeyContent) {
            journeyContent.innerHTML = "";
        }

        if (matchStatusPanel) {
            matchStatusPanel.innerHTML = "";
        }

        if (resultContext) {
            resultContext.innerHTML = "";
        }

        if (problemSummary) {
            problemSummary.textContent = "";
        }

        hide(matchStatusPanel);
        hide(clarificationSection);
    }


    /* ============================================================
       CONTEXT
       ============================================================ */

    function renderContext(data) {
        if (!resultContext) return;

        const tags = [];

        if (currentIndustry) {
            tags.push(currentIndustry);
        }

        if (currentRole) {
            tags.push(currentRole);
        }

        if (data?.category) {
            if (!tags.includes(data.category)) {
                tags.push(data.category);
            }
        }

        /*
         * The old version visually ran these together.
         * Render them as independent pieces.
         */
        resultContext.innerHTML =
            tags
                .filter(Boolean)
                .map(
                    tag => `
                        <span class="result-context-tag">
                            ${escapeHtml(tag)}
                        </span>
                    `
                )
                .join("");
    }


    /* ============================================================
       STATUS PANEL
       ============================================================ */

    function renderStatus(data) {
        const status =
            normalizeStatus(data);

        if (!matchStatusPanel) {
            return status;
        }

        /*
         * Never display an empty / meaningless question mark when
         * the answer itself is already useful.
         */
        if (status === "matched") {
            matchStatusPanel.className =
                "match-status-panel mapper-status-matched";

            matchStatusPanel.innerHTML = `
                <div class="result-status-inner">
                    <span class="result-status-mark">✓</span>

                    <div>
                        <span class="result-status-kicker">
                            TERRAGNI PERSPECTIVE
                        </span>

                        <strong>
                            We found a relevant direction for your challenge.
                        </strong>
                    </div>
                </div>
            `;

            show(matchStatusPanel);
            hide(clarificationSection);

            return status;
        }

        if (status === "needs_clarification") {
            matchStatusPanel.className =
                "match-status-panel mapper-status-needs_clarification";

            matchStatusPanel.innerHTML = `
                <div class="result-status-inner">
                    <span class="result-status-mark">?</span>

                    <div>
                        <span class="result-status-kicker">
                            ONE USEFUL DETAIL
                        </span>

                        <strong>
                            We can see the direction, but one detail would sharpen it.
                        </strong>
                    </div>
                </div>
            `;

            show(matchStatusPanel);

            renderClarification(
                asArray(data?.probing_questions)
            );

            return status;
        }

        matchStatusPanel.className =
            "match-status-panel mapper-status-not_supported";

        matchStatusPanel.innerHTML = `
            <div class="result-status-inner">
                <span class="result-status-mark">—</span>

                <div>
                    <span class="result-status-kicker">
                        EVIDENCE BOUNDARY
                    </span>

                    <strong>
                        We need a little more context before recommending a specific direction.
                    </strong>
                </div>
            </div>
        `;

        show(matchStatusPanel);

        renderClarification(
            asArray(data?.probing_questions)
        );

        return status;
    }


    /* ============================================================
       CLARIFICATION
       ============================================================ */

    function renderClarification(questions) {
        if (!clarificationSection) {
            return;
        }

        /*
         * If there is already a strong result, clarification is not
         * allowed to dominate the page.
         */
        if (hasUsableSolution(currentResponse || {})) {
            hide(clarificationSection);
            return;
        }

        show(clarificationSection);

        const question =
            questions[0] ||
            "What part of the challenge is creating the biggest business impact?";

        if (clarificationQuestion) {
            clarificationQuestion.innerHTML = `
                <span class="clarification-question-label">
                    One useful detail
                </span>

                <strong>
                    ${escapeHtml(question)}
                </strong>
            `;
        }

        if (
            clarificationForm &&
            !clarificationForm.dataset.bound
        ) {
            clarificationForm.dataset.bound = "true";

            clarificationForm.addEventListener(
                "submit",
                event => {
                    event.preventDefault();

                    const extra =
                        valueOf(
                            clarificationInput
                        );

                    if (!extra) {
                        clarificationInput?.focus();
                        return;
                    }

                    if (clarificationSubmitButton) {
                        clarificationSubmitButton.disabled = true;
                        clarificationSubmitButton.textContent =
                            "Exploring…";
                    }

                    const combined =
                        `${currentChallenge}

Additional context:
${extra}`;

                    submitQuery(
                        combined,
                        currentIndustry,
                        currentRole,
                        {
                            mode: "challenge",
                            force: true
                        }
                    );
                }
            );
        }
    }


    /* ============================================================
       SECTION CREATOR
       ============================================================ */

    function createSection({
        id,
        number,
        kicker,
        title,
        intro = "",
        className = ""
    }) {
        if (!journeyContent) {
            return null;
        }

        const section =
            document.createElement("section");

        section.id = id;

        section.className =
            `mapper-result-section ${className}`.trim();

        section.innerHTML = `
            <div class="mapper-result-section-inner">

                <div class="mapper-section-heading">

                    <div class="mapper-section-meta">

                        ${
                            number
                                ? `
                                    <span class="mapper-section-number">
                                        ${escapeHtml(number)}
                                    </span>
                                `
                                : ""
                        }

                        ${
                            kicker
                                ? `
                                    <span class="mapper-section-kicker">
                                        ${escapeHtml(kicker)}
                                    </span>
                                `
                                : ""
                        }

                    </div>

                    <h2>
                        ${escapeHtml(title)}
                    </h2>

                    ${
                        intro
                            ? `
                                <p class="mapper-section-intro">
                                    ${escapeHtml(intro)}
                                </p>
                            `
                            : ""
                    }

                </div>

                <div class="mapper-section-content"></div>

            </div>
        `;

        journeyContent.appendChild(section);

        return $(
            ".mapper-section-content",
            section
        );
    }


    /* ============================================================
       01 — YOUR CHALLENGE
       ============================================================ */

    function renderChallenge() {
        const body =
            createSection({
                id:
                    "mapper-challenge-section",

                number:
                    "01",

                kicker:
                    "YOUR CHALLENGE",

                title:
                    "Let’s start with the situation you brought us.",

                intro:
                    "This is the starting point for the Terragni lens.",

                className:
                    "mapper-challenge-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-challenge-card">

                <div class="mapper-challenge-card-top">
                    <span>
                        ${escapeHtml(currentIndustry)}
                    </span>

                    <span>
                        ${escapeHtml(currentRole)}
                    </span>
                </div>

                <blockquote>
                    “${escapeHtml(currentChallenge)}”
                </blockquote>

            </div>
        `;
    }


    /* ============================================================
       02 — INTERPRETATION
       ============================================================ */

    function renderInterpretation(data) {
        const translation =
            getTranslation(data);

        const perspective =
            getPerspective(data);

        const problem =
            translation.problem ||
            perspective.summary ||
            "The visible symptom is pointing to a deeper business or human challenge.";

        const explanation =
            translation.explanation ||
            "The important question is not only what is going wrong, but what is creating that situation and preventing it from changing.";

        const body =
            createSection({
                id:
                    "mapper-interpretation-section",

                number:
                    "02",

                kicker:
                    "AI INTERPRETATION",

                title:
                    "What is really happening underneath?",

                intro:
                    "We separate the visible symptom from the business tension that needs to be addressed.",

                className:
                    "mapper-interpretation-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-insight-card">

                <div class="mapper-insight-label">
                    THE UNDERLYING BUSINESS TENSION
                </div>

                <h3>
                    ${escapeHtml(problem)}
                </h3>

                <div class="mapper-insight-line"></div>

                <p>
                    ${escapeHtml(explanation)}
                </p>

            </div>
        `;

        if (problemSummary) {
            problemSummary.textContent =
                problem;
        }
    }


    /* ============================================================
       03 — CHALLENGE ANATOMY
       ============================================================ */

    function renderFriction(data) {
        const areas =
            asArray(
                data?.areas_of_concern
            );

        const perspective =
            getPerspective(data);

        let items =
            areas.map(
                (item, index) => ({
                    name:
                        getName(item) ||
                        `Area ${index + 1}`,

                    description:
                        getDescription(item)
                })
            );

        /*
         * If the backend didn't provide areas_of_concern, use the
         * perspective points rather than deleting the entire section.
         */
        if (!items.length) {
            items =
                perspective.points
                    .slice(0, 4)
                    .map(
                        (item, index) => ({
                            name:
                                getName(item) ||
                                `Signal ${index + 1}`,

                            description:
                                getDescription(item) ||
                                text(item)
                        })
                    );
        }

        /*
         * Last-resort explanatory structure.
         * These are not claimed as Terragni evidence; they simply
         * explain what the customer should look at in the situation.
         */
        if (!items.length) {
            items = [
                {
                    name: "Experience friction",
                    description:
                        "Where the current experience is creating effort, confusion, uncertainty or drop-off."
                },
                {
                    name: "Human behaviour",
                    description:
                        "What people need to understand, believe or do differently for the situation to improve."
                },
                {
                    name: "System conditions",
                    description:
                        "The process, touchpoints or organisational conditions that keep reinforcing the problem."
                }
            ];
        }

        const body =
            createSection({
                id:
                    "mapper-friction-section",

                number:
                    "03",

                kicker:
                    "CHALLENGE ANATOMY",

                title:
                    "Where the problem is actually being created.",

                intro:
                    "These are the moving parts the solution needs to address — not just the symptom the business can see.",

                className:
                    "mapper-friction-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-friction-grid">

                ${
                    items
                        .slice(0, 4)
                        .map(
                            (item, index) => `
                                <article class="mapper-friction-card">

                                    <span class="mapper-card-number">
                                        ${String(
                                            index + 1
                                        ).padStart(2, "0")}
                                    </span>

                                    <h3>
                                        ${escapeHtml(
                                            item.name
                                        )}
                                    </h3>

                                    ${
                                        item.description
                                            ? `
                                                <p>
                                                    ${escapeHtml(
                                                        item.description
                                                    )}
                                                </p>
                                            `
                                            : ""
                                    }

                                </article>
                            `
                        )
                        .join("")
                }

            </div>
        `;
    }


    /* ============================================================
       04 — TERRAGNI LENS
       ============================================================ */

    function renderLens(data) {
        const perspective =
            getPerspective(data);

        const translation =
            getTranslation(data);

        const summary =
            perspective.summary ||
            translation.explanation ||
            "Look beyond the visible symptom and change the conditions that are creating it.";

        const points =
            perspective.points;

        const body =
            createSection({
                id:
                    "mapper-lens-section",

                number:
                    "04",

                kicker:
                    "TERRAGNI LENS",

                title:
                    "A different way to look at the situation.",

                intro:
                    "This is the shift in perspective that turns the diagnosis into a possible intervention.",

                className:
                    "mapper-lens-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-lens-card">

                <div class="mapper-lens-mark">
                    T
                </div>

                <div class="mapper-lens-copy">

                    <span class="mapper-lens-label">
                        THE TERRAGNI PERSPECTIVE
                    </span>

                    <h3>
                        ${escapeHtml(summary)}
                    </h3>

                    ${
                        points.length
                            ? `
                                <div class="mapper-lens-points">

                                    ${
                                        points
                                            .slice(0, 3)
                                            .map(
                                                (item, index) => `
                                                    <div class="mapper-lens-point">

                                                        <span>
                                                            ${String(
                                                                index + 1
                                                            ).padStart(2, "0")}
                                                        </span>

                                                        <div>

                                                            <strong>
                                                                ${escapeHtml(
                                                                    getName(item) ||
                                                                    `Perspective ${index + 1}`
                                                                )}
                                                            </strong>

                                                            ${
                                                                getDescription(item)
                                                                    ? `
                                                                        <p>
                                                                            ${escapeHtml(
                                                                                getDescription(item)
                                                                            )}
                                                                        </p>
                                                                    `
                                                                    : ""
                                                            }

                                                        </div>

                                                    </div>
                                                `
                                            )
                                            .join("")
                                    }

                                </div>
                            `
                            : ""
                    }

                </div>

            </div>
        `;
    }


    /* ============================================================
       SOLUTION DATA
       ============================================================ */

    function getSolutionName(data) {
        const primary =
            getPrimaryOffering(data);

        return firstMeaningful(
            data?.solution_name,
            data?.recommended_solution,
            data?.solution?.name,
            data?.solution?.title,
            data?.direction?.name,
            data?.direction?.title,
            getName(primary),
            "A Terragni-led change direction"
        );
    }

    function getSolutionDescription(data) {
        const primary =
            getPrimaryOffering(data);

        const solution =
            data?.solution ||
            data?.direction ||
            {};

        const perspective =
            getPerspective(data);

        return firstMeaningful(
            solution?.explanation,
            solution?.description,
            solution?.summary,
            solution?.what_it_is,
            solution?.approach,
            data?.solution_explanation,
            data?.recommendation,
            getDescription(primary),
            perspective.summary
        );
    }

    function getSolutionWhy(data) {
        const primary =
            getPrimaryOffering(data);

        const solution =
            data?.solution ||
            data?.direction ||
            {};

        return firstMeaningful(
            solution?.why_relevant,
            solution?.relevance,
            solution?.fit,
            solution?.why_it_fits,
            data?.why_relevant,
            data?.match_summary,
            getWhy(primary)
        );
    }


    /* ============================================================
       05 — THE ACTUAL SOLUTION
       ============================================================ */

    function renderDirection(data) {
        const offerings =
            getOfferings(data);

        const name =
            getSolutionName(data);

        const description =
            getSolutionDescription(data);

        const why =
            getSolutionWhy(data);

        const body =
            createSection({
                id:
                    "mapper-direction-section",

                number:
                    "05",

                kicker:
                    "THE TERRAGNI SOLUTION",

                title:
                    "So what would Terragni actually do?",

                intro:
                    "This is the bridge from understanding the problem to changing it.",

                className:
                    "mapper-direction-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-direction-card">

                <div class="mapper-direction-copy">

                    <span class="mapper-direction-label">
                        RECOMMENDED DIRECTION
                    </span>

                    <h3>
                        ${escapeHtml(name)}
                    </h3>

                    <p class="mapper-direction-description">
                        ${escapeHtml(
                            description ||
                            "The direction is to address the underlying conditions creating the problem rather than treating only the visible symptom."
                        )}
                    </p>

                    <div class="mapper-direction-divider"></div>

                    <div class="mapper-direction-why">

                        <span>
                            WHY THIS FITS YOUR SITUATION
                        </span>

                        <p>
                            ${escapeHtml(
                                why ||
                                "It connects the intervention to the underlying tension identified above, rather than treating the challenge as an isolated operational problem."
                            )}
                        </p>

                    </div>

                    ${
                        offerings.length
                            ? `
                                <button
                                    type="button"
                                    class="mapper-direction-button"
                                    data-direction-index="0"
                                >
                                    Explore this direction
                                    <span>↗</span>
                                </button>
                            `
                            : ""
                    }

                </div>

                <div class="mapper-direction-visual">

                    <div class="mapper-path">

                        <div class="mapper-path-node active">
                            <span>01</span>
                            <strong>
                                Your challenge
                            </strong>
                        </div>

                        <div class="mapper-path-line"></div>

                        <div class="mapper-path-node active">
                            <span>02</span>
                            <strong>
                                Terragni lens
                            </strong>
                        </div>

                        <div class="mapper-path-line"></div>

                        <div class="mapper-path-node final">
                            <span>03</span>
                            <strong>
                                The intervention
                            </strong>
                        </div>

                    </div>

                </div>

            </div>
        `;

        const button =
            $(".mapper-direction-button", body);

        if (button && offerings.length) {
            button.addEventListener(
                "click",
                () => {
                    openOfferingDrawer(
                        offerings[0]
                    );
                }
            );
        }

        /*
         * Alternative offerings remain useful, but they are no longer
         * allowed to dominate the main solution.
         */
        if (offerings.length > 1) {
            const alternatives =
                offerings.slice(1, 4);

            const wrapper =
                document.createElement("div");

            wrapper.className =
                "mapper-alternatives";

            wrapper.innerHTML = `
                <div class="mapper-alternatives-heading">

                    <span>
                        OTHER RELEVANT DIRECTIONS
                    </span>

                    <p>
                        Other Terragni capabilities connected to this situation.
                    </p>

                </div>

                <div class="mapper-alternatives-grid">

                    ${
                        alternatives
                            .map(
                                (item, index) => `
                                    <article
                                        class="mapper-alternative-card"
                                        tabindex="0"
                                        data-alternative-index="${index}"
                                    >

                                        <span>
                                            ${String(
                                                index + 2
                                            ).padStart(2, "0")}
                                        </span>

                                        <h4>
                                            ${escapeHtml(
                                                getName(item) ||
                                                "Relevant direction"
                                            )}
                                        </h4>

                                        ${
                                            getDescription(item)
                                                ? `
                                                    <p>
                                                        ${escapeHtml(
                                                            getDescription(item)
                                                        )}
                                                    </p>
                                                `
                                                : ""
                                        }

                                        <b>↗</b>

                                    </article>
                                `
                            )
                            .join("")
                    }

                </div>
            `;

            body.appendChild(wrapper);

            $$(".mapper-alternative-card", wrapper)
                .forEach(card => {
                    const index =
                        Number(
                            card.dataset.alternativeIndex
                        );

                    const open = () =>
                        openOfferingDrawer(
                            alternatives[index]
                        );

                    card.addEventListener(
                        "click",
                        open
                    );

                    card.addEventListener(
                        "keydown",
                        event => {
                            if (
                                event.key === "Enter" ||
                                event.key === " "
                            ) {
                                event.preventDefault();
                                open();
                            }
                        }
                    );
                });
        }
    }


    /* ============================================================
       06 — HOW THE SOLUTION WORKS
       ============================================================ */

    function getHowItWorks(data) {
        const primary =
            getPrimaryOffering(data);

        const solution =
            data?.solution ||
            data?.direction ||
            {};

        let steps =
            asArray(
                solution?.steps ||
                solution?.how_it_works ||
                solution?.approach ||
                primary?.steps ||
                primary?.how_it_works ||
                data?.how_it_works
            );

        if (steps.length) {
            return steps;
        }

        /*
         * When the API hasn't supplied formal stages, this gives the
         * customer a useful explanation of the intervention without
         * falsely claiming that these are named Terragni framework stages.
         */
        return [
            {
                title: "Understand the real friction",
                description:
                    "Identify where the current experience, behaviour or process is creating unnecessary effort, uncertainty or resistance."
            },
            {
                title: "Design the intervention",
                description:
                    "Translate that understanding into a focused change that addresses the underlying issue instead of only the visible symptom."
            },
            {
                title: "Make the change usable",
                description:
                    "Shape the experience, behaviours and supporting conditions so the people involved can understand and adopt the change."
            },
            {
                title: "Embed and learn",
                description:
                    "Use feedback and evidence to strengthen what works and make the change sustainable."
            }
        ];
    }

    function normaliseStep(item, index) {
        if (typeof item === "string") {
            return {
                title: item,
                description: ""
            };
        }

        return {
            title:
                firstMeaningful(
                    item?.title,
                    item?.name,
                    item?.label,
                    `Step ${index + 1}`
                ),

            description:
                firstMeaningful(
                    item?.description,
                    item?.summary,
                    item?.detail,
                    item?.explanation,
                    item?.why_relevant
                )
        };
    }

    function renderHowItWorks(data) {
        const steps =
            getHowItWorks(data)
                .map(normaliseStep);

        const body =
            createSection({
                id:
                    "mapper-how-it-works-section",

                number:
                    "06",

                kicker:
                    "HOW IT WORKS",

                title:
                    "How the solution moves from insight to change.",

                intro:
                    "The important part is not just the recommendation — it is how the intervention addresses the conditions creating the problem.",

                className:
                    "mapper-framework-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-framework-grid">

                ${
                    steps
                        .slice(0, 4)
                        .map(
                            (step, index) => `
                                <article
                                    class="mapper-framework-card"
                                >

                                    <span class="mapper-card-number">
                                        ${String(
                                            index + 1
                                        ).padStart(2, "0")}
                                    </span>

                                    <h3>
                                        ${escapeHtml(
                                            step.title
                                        )}
                                    </h3>

                                    ${
                                        step.description
                                            ? `
                                                <p>
                                                    ${escapeHtml(
                                                        step.description
                                                    )}
                                                </p>
                                            `
                                            : ""
                                    }

                                </article>
                            `
                        )
                        .join("")
                }

            </div>
        `;
    }


    /* ============================================================
       07 — WHY IT FITS
       ============================================================ */

    function renderFit(data) {
        const perspective =
            getPerspective(data);

        const translation =
            getTranslation(data);

        const primary =
            getPrimaryOffering(data);

        const problem =
            translation.problem ||
            "the underlying challenge";

        const solution =
            getSolutionName(data);

        const why =
            getSolutionWhy(data);

        const body =
            createSection({
                id:
                    "mapper-fit-section",

                number:
                    "07",

                kicker:
                    "WHY THIS FITS",

                title:
                    "Why this direction makes sense for your situation.",

                intro:
                    "The solution should feel connected to the actual problem — not like a generic service recommendation.",

                className:
                    "mapper-framework-section"
            });

        if (!body) return;

        const fitText =
            why ||
            (
                `Your challenge points to ${problem}. ` +
                `The ${solution} direction is relevant because it focuses on the underlying conditions rather than only responding to the visible symptom.`
            );

        body.innerHTML = `
            <div class="mapper-insight-card">

                <div class="mapper-insight-label">
                    THE CONNECTION
                </div>

                <h3>
                    ${escapeHtml(solution)}
                </h3>

                <div class="mapper-insight-line"></div>

                <p>
                    ${escapeHtml(fitText)}
                </p>

                ${
                    perspective.summary
                        ? `
                            <div class="mapper-direction-why">
                                <span>
                                    TERRAGNI LENS
                                </span>

                                <p>
                                    ${escapeHtml(
                                        perspective.summary
                                    )}
                                </p>
                            </div>
                        `
                        : ""
                }

            </div>
        `;
    }


    /* ============================================================
       08 — TOOLKIT / EXPERIENCE
       ============================================================ */

    function renderEvidence(data) {
        const frameworks =
            getFrameworks(data);

        const cases =
            getCases(data);

        const evidence =
            getEvidence(data);

        const body =
            createSection({
                id:
                    "mapper-experience-section",

                number:
                    "08",

                kicker:
                    frameworks.length
                        ? "TERRAGNI TOOLKIT"
                        : "DOCUMENTED EXPERIENCE",

                title:
                    frameworks.length
                        ? "What supports the direction."
                        : "What Terragni can substantiate.",

                intro:
                    frameworks.length
                        ? "These are the frameworks, methods or capabilities returned by the Terragni evidence."
                        : "We keep documented evidence separate from interpretation.",

                className:
                    "mapper-experience-section"
            });

        if (!body) return;

        if (frameworks.length) {
            body.innerHTML = `
                <div class="mapper-framework-grid">

                    ${
                        frameworks
                            .slice(0, 4)
                            .map(
                                (item, index) => `
                                    <article
                                        class="mapper-framework-card"
                                    >

                                        <span class="mapper-card-number">
                                            ${String(
                                                index + 1
                                            ).padStart(2, "0")}
                                        </span>

                                        <h3>
                                            ${escapeHtml(
                                                getName(item) ||
                                                `Terragni method ${index + 1}`
                                            )}
                                        </h3>

                                        ${
                                            getDescription(item)
                                                ? `
                                                    <p>
                                                        ${escapeHtml(
                                                            getDescription(item)
                                                        )}
                                                    </p>
                                                `
                                                : ""
                                        }

                                        ${
                                            getWhy(item)
                                                ? `
                                                    <div class="framework-relevance">
                                                        <small>
                                                            WHY IT MATTERS
                                                        </small>

                                                        <p>
                                                            ${escapeHtml(
                                                                getWhy(item)
                                                            )}
                                                        </p>
                                                    </div>
                                                `
                                                : ""
                                        }

                                    </article>
                                `
                            )
                            .join("")
                    }

                </div>
            `;

            return;
        }

        const proof =
            cases.length
                ? cases
                : evidence;

        if (proof.length) {
            body.innerHTML = `
                <div class="mapper-proof-grid">

                    ${
                        proof
                            .slice(0, 4)
                            .map(
                                (item, index) => {

                                    const title =
                                        firstMeaningful(
                                            item?.public_title,
                                            item?.title,
                                            item?.name,
                                            item?.source,
                                            item?.document_title,
                                            "Relevant Terragni experience"
                                        );

                                    const client =
                                        firstMeaningful(
                                            item?.public_client_name,
                                            item?.client_name
                                        );

                                    const summary =
                                        firstMeaningful(
                                            item?.why_relevant,
                                            item?.summary,
                                            item?.description,
                                            item?.claim,
                                            item?.evidence_text,
                                            item?.text,
                                            item?.challenge
                                        );

                                    return `
                                        <article
                                            class="mapper-proof-card"
                                        >

                                            <div class="mapper-proof-top">

                                                <span>
                                                    ${String(
                                                        index + 1
                                                    ).padStart(2, "0")}
                                                </span>

                                                ${
                                                    client
                                                        ? `
                                                            <small>
                                                                ${escapeHtml(
                                                                    client
                                                                )}
                                                            </small>
                                                        `
                                                        : ""
                                                }

                                            </div>

                                            <h3>
                                                ${escapeHtml(title)}
                                            </h3>

                                            ${
                                                summary
                                                    ? `
                                                        <p>
                                                            ${escapeHtml(
                                                                summary
                                                            )}
                                                        </p>
                                                    `
                                                    : ""
                                            }

                                        </article>
                                    `;
                                }
                            )
                            .join("")
                    }

                </div>
            `;

            return;
        }

        /*
         * Do NOT invent a client or case study.
         * Give the customer a clear evidence boundary instead.
         */
        body.innerHTML = `
            <div class="mapper-insight-card">

                <div class="mapper-insight-label">
                    EVIDENCE BOUNDARY
                </div>

                <h3>
                    The direction is useful, but no specific case study was returned for this query.
                </h3>

                <div class="mapper-insight-line"></div>

                <p>
                    We are deliberately not inventing a client example or framework name. The direction above is based on the Terragni perspective returned for your situation.
                </p>

            </div>
        `;
    }


    /* ============================================================
       09 — OUTCOMES
       ============================================================ */

    function renderOutcomes(data) {
        let outcomes =
            getOutcomes(data);

        const perspective =
            getPerspective(data);

        let items =
            outcomes.map(
                item => ({
                    title:
                        getName(item) ||
                        text(item),

                    description:
                        getDescription(item)
                })
            );

        if (!items.length) {
            items =
                perspective.outcomes
                    .map(
                        item => ({
                            title:
                                getName(item) ||
                                text(item),

                            description:
                                getDescription(item)
                        })
                    );
        }

        /*
         * We distinguish "potential change" from measured client results.
         */
        if (!items.length) {
            items = [
                {
                    title: "Less friction",
                    description:
                        "A clearer and easier experience around the part of the journey creating the problem."
                },
                {
                    title: "Stronger adoption",
                    description:
                        "People can understand what is changing and what is expected of them."
                },
                {
                    title: "More sustainable change",
                    description:
                        "The intervention addresses the conditions that influence experience and behaviour, rather than relying only on a one-off fix."
                }
            ];
        }

        const body =
            createSection({
                id:
                    "mapper-outcomes-section",

                number:
                    "09",

                kicker:
                    "WHAT COULD CHANGE",

                title:
                    "What success could look like.",

                intro:
                    "These are intended changes, not guaranteed results. Specific measures should be agreed against your situation.",

                className:
                    "mapper-outcomes-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-outcome-grid">

                ${
                    items
                        .slice(0, 4)
                        .map(
                            (item, index) => `
                                <article
                                    class="mapper-outcome-card"
                                >

                                    <span class="mapper-card-number">
                                        ${String(
                                            index + 1
                                        ).padStart(2, "0")}
                                    </span>

                                    <h3>
                                        ${escapeHtml(
                                            item.title
                                        )}
                                    </h3>

                                    ${
                                        item.description
                                            ? `
                                                <p>
                                                    ${escapeHtml(
                                                        item.description
                                                    )}
                                                </p>
                                            `
                                            : ""
                                    }

                                </article>
                            `
                        )
                        .join("")
                }

            </div>
        `;
    }


    /* ============================================================
       10 — NEXT STEP
       ============================================================ */

    function renderNextStep(data) {
        const closing =
            data?.closing;

        const message =
            typeof closing === "string"
                ? closing
                : firstMeaningful(
                    data?.next_step,
                    closing?.next_step,
                    closing?.message,
                    closing?.invitation,
                    closing?.text,
                    closing?.action
                );

        const body =
            createSection({
                id:
                    "mapper-next-section",

                number:
                    "10",

                kicker:
                    "WHAT NEXT",

                title:
                    "The answer is not the end of the journey.",

                intro:
                    "The direction gives you a better starting point for the next conversation.",

                className:
                    "mapper-next-section"
            });

        if (!body) return;

        body.innerHTML = `
            <div class="mapper-next-card">

                <div class="mapper-next-copy">

                    <span>
                        SUGGESTED NEXT MOVE
                    </span>

                    <h3>
                        ${escapeHtml(
                            message ||
                            "Explore the direction above in more detail with Terragni."
                        )}
                    </h3>

                    <p>
                        Use this perspective as the starting point for a more specific conversation about the people, experience and business conditions involved.
                    </p>

                </div>

                <div class="mapper-next-mark">
                    ↗
                </div>

            </div>
            ${contactCtaHtml()}
        `;
    }


    /* ============================================================
       COMPLETE JOURNEY
       ============================================================ */

    function renderJourney(data) {
        if (!journeyContent) {
            console.error(
                "Terragni Mapper: #journey-content is missing."
            );
            return;
        }

        journeyContent.innerHTML = "";

        // New single-page answer (answer-view.js): every fact shown once.
        if (window.TerragniAnswer) {
            document.body.classList.add("av-mode");
            window.TerragniAnswer.challenge(journeyContent, data, {
                question: currentChallenge,
                role: currentRole
            });
            return;
        }

        /*
         * IMPORTANT:
         * Every section is now intentionally rendered.
         * Missing API fields affect the content inside a section,
         * not whether the section disappears.
         */

        renderChallenge();

        renderInterpretation(data);

        renderFriction(data);

        renderLens(data);

        renderDirection(data);

        renderHowItWorks(data);

        renderFit(data);

        renderEvidence(data);

        renderOutcomes(data);

        renderNextStep(data);

        /*
         * Staggered reveal.
         */
        window.requestAnimationFrame(() => {
            const sections =
                $$(".mapper-result-section");

            sections.forEach(
                (section, index) => {

                    section.style.setProperty(
                        "--mapper-delay",
                        `${Math.min(
                            index * 90,
                            700
                        )}ms`
                    );

                    window.setTimeout(
                        () => {
                            section.classList.add(
                                "is-visible"
                            );
                        },
                        Math.min(
                            index * 90,
                            700
                        )
                    );
                }
            );
        });
    }


    /* ============================================================
       RESULT HEADER
       ============================================================ */

    function renderResultHeader(data) {
        const status =
            normalizeStatus(data);

        if (dynamicTitle) {
            if (status === "matched") {
                dynamicTitle.textContent =
                    "Here’s the Terragni solution we see.";
            } else if (
                status === "needs_clarification"
            ) {
                dynamicTitle.textContent =
                    "Here’s what we can see so far.";
            } else {
                dynamicTitle.textContent =
                    "Let’s understand the challenge.";
            }
        }

        if (problemSummary) {
            const translation =
                getTranslation(data);

            problemSummary.textContent =
                translation.problem ||
                currentChallenge;
        }
    }


    /* ============================================================
       VISUAL PLANNING
       ============================================================ */

    function createVisualPlan(data) {
        if (
            !window.TerragniVisualPlanner ||
            typeof window.TerragniVisualPlanner.createVisualPlan !== "function"
        ) {
            return null;
        }

        try {
            return window.TerragniVisualPlanner.createVisualPlan(
                data || {}
            );
        } catch (error) {
            console.warn(
                "Terragni Mapper: visual planning failed.",
                error
            );

            return null;
        }
    }


    /* ============================================================
       RESULT
       ============================================================ */

    function renderResult(data) {
        const response =
            data || {};

        clearResult();

        /*
         * Build a client-side visual plan from the returned solution.
         *
         * This does not change the backend response.
         */
        currentVisualPlan =
            createVisualPlan(response);

        /*
         * Keep the original API response intact while attaching
         * the client-side visual plan for the rendering layer.
         */
        currentResponse = {
            ...response,
            visual_plan:
                currentVisualPlan
        };

        renderStatus(currentResponse);

        renderContext(currentResponse);

        renderResultHeader(currentResponse);

        renderJourney(currentResponse);

        setResultsBanner("challenge");
        if (!window.TerragniAnswer) {
            renderChallengeVisuals(currentResponse);
        }
        announceResult("challenge", currentResponse);

        saveContactContext({
            path: "challenge",
            summary: getTranslation(currentResponse).problem || "",
            suggested_services: getOfferings(currentResponse)
                .map(getName)
                .filter(Boolean)
        });

        hide(hero);
        hide(loading);

        show(results);

        if (results) {
            results.setAttribute(
                "aria-busy",
                "false"
            );
        }

        setJourneyStep(4);

        window.setTimeout(
            () => {
                const firstSection =
                    $(".av-page") || $(".mapper-result-section");

                if (firstSection) {
                    scrollToElement(
                        firstSection,
                        20
                    );
                }
            },
            100
        );
    }


    /* ============================================================
       API
       ============================================================ */

    async function submitQuery(
        text,
        industry,
        role,
        options = {}
    ) {
        const safeText =
            String(text || "").trim();

        const safeIndustry =
            String(industry || "").trim();

        const safeRole =
            String(role || "").trim();

        if (!safeText) {
            showError(
                "Please type your question or describe the challenge."
            );
            return;
        }

        currentChallenge = safeText;
        currentIndustry = safeIndustry;
        currentRole = safeRole;

        const mode =
            options.mode || currentMode;

        clearError();
        clearResult();
        setLoading(true);
        startLoading();

        try {
            /*
             * One entry point for both paths. The server works out
             * whether this is a challenge or a question about Terragni
             * and returns "path" to say which page to show.
             */
            const response =
                await fetch(
                    "/api/ask",
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        },
                        body: JSON.stringify({
                            industry: safeIndustry,
                            role: safeRole,
                            text: safeText,
                            mode,
                            force: Boolean(options.force)
                        })
                    }
                );

            let data;

            try {
                data = await response.json();
            } catch (error) {
                throw new Error(
                    "The server returned an invalid response."
                );
            }

            if (!response.ok || data?.ok === false) {
                throw new Error(
                    data?.error ||
                    data?.message ||
                    `Request failed with status ${response.status}.`
                );
            }

            if (data.path === "knowledge") {
                renderKnowledgeResult(data);
            } else if (data.path === "out_of_scope") {
                renderOutOfScopeResult(data);
            } else {
                renderResult(data || {});
            }
        } catch (error) {
            console.error(
                "Terragni mapper error:",
                error
            );

            show(hero);
            hide(results);

            showError(
                error?.message ||
                "Something went wrong. Please try again."
            );

            setJourneyStep(2);
        } finally {
            stopLoading();
            setLoading(false);

            if (results) {
                results.setAttribute(
                    "aria-busy",
                    "false"
                );
            }
        }
    }



    /* ============================================================
       VISUALS (mapper-visuals.js)
       ============================================================ */

    const Visuals = window.TerragniVisuals || null;

    const visualIcon = (name) =>
        Visuals ? Visuals.icon(name) : "";

    const shorten = (value, length) => {
        const textValue = String(value || "").trim();
        return textValue.length > length
            ? `${textValue.slice(0, length - 1).trim()}…`
            : textValue;
    };

    function setResultsBanner(path) {
        if (results) {
            results.dataset.path = path;
        }
    }

    /*
     * "At a glance" section: a flow (optional) and the Terragni map.
     * Inserted as the first result section so the visitor sees the
     * picture before the detail.
     */
    function renderGlanceSection({ title, intro, flowSteps, map, afterId }) {
        if (!Visuals || !journeyContent) return;

        const flowHtml = flowSteps ? Visuals.flowDiagram(flowSteps) : "";
        const mapHtml = map ? Visuals.mapDiagram(map) : "";

        if (!flowHtml && !mapHtml) return;

        const body = createSection({
            id: "mapper-glance-section",
            number: "",
            kicker: "AT A GLANCE",
            title,
            intro,
            className: "mapper-glance-section"
        });

        if (!body) return;

        body.innerHTML = `${flowHtml}${mapHtml}`;

        const section = body.closest(".mapper-result-section");
        const anchor = afterId ? document.getElementById(afterId) : null;

        if (!section) return;

        if (anchor && anchor.parentNode === journeyContent) {
            anchor.after(section);
        } else if (journeyContent.firstChild !== section) {
            journeyContent.insertBefore(section, journeyContent.firstChild);
        }
    }

    function namesOf(items) {
        return asArray(items).map(getName).filter(Boolean);
    }

    function renderChallengeVisuals(data) {
        const translation = getTranslation(data);
        const offerings = getOfferings(data);
        const primary = offerings[0];
        const concerns = asArray(data?.areas_of_concern).filter(Boolean);

        const flowSteps = [
            {
                kicker: "WHAT YOU TOLD US",
                title: shorten(currentChallenge, 110),
                icon: "chat",
                tone: "neutral"
            },
            translation.problem && {
                kicker: "WHAT IS REALLY HAPPENING",
                title: translation.problem,
                text: concerns.length ? shorten(concerns.slice(0, 2).join(" · "), 120) : "",
                icon: "alert",
                tone: "warning"
            },
            primary && {
                kicker: "WHAT TERRAGNI WOULD DO",
                title: getName(primary),
                text: shorten(getWhy(primary), 130),
                icon: "spark",
                tone: "primary"
            },
            {
                kicker: "WHAT SUCCESS LOOKS LIKE",
                title: shorten(
                    firstMeaningful(
                        data?.closing,
                        getPerspective(data).summary
                    ) || "A clear next step with Terragni.",
                    120
                ),
                icon: "target",
                tone: "success"
            }
        ].filter(Boolean);

        renderGlanceSection({
            title: "Your challenge, mapped to Terragni's proven work.",
            intro: "Read left to right: what you told us, what is really happening, and how Terragni would respond.",
            flowSteps,
            map: {
                centerLabel: "Your challenge",
                centerText: translation.problem || shorten(currentChallenge, 70),
                ariaLabel: "Map of your challenge and the Terragni services, methods and examples linked to it",
                groups: [
                    { key: "service", label: "Terragni services", items: namesOf(offerings) },
                    { key: "method", label: "Methods", items: namesOf(getFrameworks(data)) },
                    { key: "example", label: "Banking examples", items: namesOf(getCases(data)) }
                ]
            }
        });
    }

    function renderKnowledgeVisuals(knowledge) {
        renderGlanceSection({
            title: "How your question connects to Terragni's work.",
            intro: "Your question in the middle, with the services, methods and banking examples that answer it.",
            flowSteps: null,
            afterId: "mapper-answer-section",
            map: {
                centerLabel: "Your question",
                centerText: shorten(currentChallenge, 70),
                ariaLabel: "Map of your question and the related Terragni services, methods and examples",
                groups: [
                    { key: "service", label: "Terragni services", items: namesOf(knowledge.offerings) },
                    { key: "method", label: "Methods", items: namesOf(knowledge.frameworks) },
                    { key: "example", label: "Banking examples", items: asArray(knowledge.case_studies).map(item => item.title).filter(Boolean) }
                ]
            }
        });
    }

    function renderHomeVisuals() {
        const strip = $("#how-it-works-strip");

        if (strip && Visuals) {
            strip.innerHTML = Visuals.howItWorks();
        }

        // The question band scrolls by -50%: duplicate its items so the loop is seamless.
        const track = $(".sm-marquee-track");
        if (track && !track.dataset.cloned) {
            track.dataset.cloned = "true";
            Array.from(track.children).forEach(item => {
                const copy = item.cloneNode(true);
                copy.setAttribute("tabindex", "-1");
                copy.setAttribute("aria-hidden", "true");
                track.appendChild(copy);
            });
        }

        // Example questions in the scrolling band fill in the form.
        $$(".sm-q").forEach(button => {
            button.addEventListener("click", () => {
                setMode(button.dataset.exampleMode || "challenge");
                if (challengeInput) {
                    challengeInput.value = button.textContent.trim().replace(/^“|”$/g, "");
                    updateCharacterCount();
                }
                scrollToElement(form || challengeInput, 90);
                window.setTimeout(() => {
                    (valueOf(industryInput) ? challengeInput : industryInput)?.focus();
                }, 500);
            });
        });
    }

    /* ============================================================
       SHARED RESULT HELPERS (KNOWLEDGE + OUT OF SCOPE)
       ============================================================ */

    function revealSections() {
        window.requestAnimationFrame(() => {
            $$(".mapper-result-section").forEach(
                (section, index) => {
                    const delay = Math.min(index * 90, 700);
                    section.style.setProperty(
                        "--mapper-delay",
                        `${delay}ms`
                    );
                    window.setTimeout(
                        () => section.classList.add("is-visible"),
                        delay
                    );
                }
            );
        });
    }


    function announceResult(path, data) {
        document.dispatchEvent(
            new CustomEvent("terragni:result", {
                detail: { path, data, question: currentChallenge }
            })
        );
    }

    function showResultsPage() {
        hide(hero);
        hide(loading);
        show(results);

        if (results) {
            results.setAttribute("aria-busy", "false");
        }

        setJourneyStep(4);

        window.setTimeout(() => {
            scrollToElement(
                $(".av-page") || $(".mapper-result-section") || results,
                20
            );
        }, 100);
    }

    function setStatusPanel(kind, kicker, message, mark) {
        if (!matchStatusPanel) return;

        matchStatusPanel.className =
            `match-status-panel mapper-status-${kind}`;

        matchStatusPanel.innerHTML = `
            <div class="result-status-inner">
                <span class="result-status-mark">${escapeHtml(mark)}</span>
                <div>
                    <span class="result-status-kicker">
                        ${escapeHtml(kicker)}
                    </span>
                    <strong>
                        ${escapeHtml(message)}
                    </strong>
                </div>
            </div>
        `;

        show(matchStatusPanel);
    }

    function questionCardHtml(label) {
        return `
            <div class="mapper-challenge-card">
                <div class="mapper-challenge-card-top">
                    <span>${escapeHtml(currentIndustry)}</span>
                    <span>${escapeHtml(currentRole)}</span>
                </div>
                <blockquote>
                    “${escapeHtml(currentChallenge)}”
                </blockquote>
                ${label ? `<p class="mapper-section-intro">${escapeHtml(label)}</p>` : ""}
            </div>
        `;
    }

    function suggestionChipsHtml(questions) {
        const items = asArray(questions).filter(Boolean);

        if (!items.length) return "";

        return `
            <div class="mapper-example-chips" data-suggestions>
                ${items.map(q => `
                    <button
                        type="button"
                        class="mapper-example-chip"
                        data-question="${escapeHtml(q)}"
                    >
                        ${escapeHtml(q)}
                    </button>
                `).join("")}
            </div>
        `;
    }

    function bindSuggestionChips(root) {
        $$("[data-question]", root).forEach(chip => {
            chip.addEventListener("click", () => {
                setMode("knowledge");
                submitQuery(
                    chip.dataset.question || "",
                    currentIndustry,
                    currentRole,
                    {
                        mode: "knowledge",
                        force: true
                    }
                );
            });
        });

        $$("[data-describe-challenge]", root).forEach(button => {
            button.addEventListener("click", () => {
                goToChallengeForm();
            });
        });
    }

    function goToChallengeForm() {
        clearResult();
        hide(results);
        show(hero);
        setMode("challenge");

        if (challengeInput) {
            challengeInput.value = "";
            updateCharacterCount();
        }

        setJourneyStep(2);

        window.setTimeout(() => {
            scrollToElement(challengeInput || hero, 120);
            challengeInput?.focus();
        }, 100);
    }

    const describeChallengeButton = `
        <button
            type="button"
            class="mapper-cta-secondary"
            data-describe-challenge
        >
            Describe your own challenge →
        </button>
    `;


    /* ============================================================
       KNOWLEDGE RESULT PAGE
       ============================================================ */

    function renderKnowledgeResult(data) {
        clearResult();

        currentResponse = data;

        const knowledge = data?.knowledge || {};
        const found = Boolean(knowledge.answer_found);
        const offerings = asArray(knowledge.offerings);
        const frameworks = asArray(knowledge.frameworks);
        const cases = asArray(knowledge.case_studies);
        const sources = asArray(knowledge.sources);

        let number = 0;
        const next = () => String(++number).padStart(2, "0");

        renderContext(data);
        setResultsBanner("knowledge");

        if (dynamicTitle) {
            dynamicTitle.textContent =
                knowledge.title || "What Terragni can tell you";
        }

        setStatusPanel(
            found ? "matched" : "not_supported",
            "ABOUT TERRAGNI",
            found
                ? "Here is what Terragni's own material says."
                : "We could not find this in Terragni's material.",
            found ? "✓" : "—"
        );

        if (window.TerragniAnswer) {
            document.body.classList.add("av-mode");
            window.TerragniAnswer.knowledge(journeyContent, data, {
                question: currentChallenge,
                role: currentRole,
                chips: suggestionChipsHtml(knowledge.suggested_questions),
                describe: data?.offer_challenge ? describeChallengeButton : ""
            });
            bindSuggestionChips(journeyContent);
            saveContactContext({
                path: "knowledge",
                summary: knowledge.answer || "",
                suggested_services: offerings.map(item => item.name)
            });
            showResultsPage();
            announceResult("knowledge", currentResponse);
            return;
        }

        let body = createSection({
            id: "mapper-question-section",
            number: next(),
            kicker: "YOUR QUESTION",
            title: "Here is what you asked.",
            className: "mapper-challenge-section"
        });

        if (body) {
            body.innerHTML = questionCardHtml("");
        }

        body = createSection({
            id: "mapper-answer-section",
            number: next(),
            kicker: "THE ANSWER",
            title: found ? "The short answer" : "What we can say"
        });

        if (body) {
            const points = asArray(knowledge.key_points);

            body.innerHTML = `
                <div class="mapper-answer-card">
                    <p>${escapeHtml(
                        knowledge.answer ||
                        "This is not covered in Terragni's material yet. Our team will be glad to answer it directly."
                    )}</p>
                    ${points.length ? `
                        <ol class="mapper-answer-points">
                            ${points.map(point => `<li><span>${escapeHtml(point)}</span></li>`).join("")}
                        </ol>
                    ` : ""}
                </div>
                ${data?.industry_supported === false ? `
                    <p class="mapper-notice" style="margin-top:16px">
                        This first version focuses on banking, so the examples
                        shown are from banks. Terragni also works in other
                        industries; our team can tell you more.
                    </p>
                ` : ""}
            `;
        }

        if (offerings.length) {
            body = createSection({
                id: "mapper-services-section",
                number: next(),
                kicker: "TERRAGNI SERVICES",
                title: "The services that relate to your question",
                intro: "What each service is, and why it matters for you."
            });

            if (body) {
                body.innerHTML = `
                    <div class="mapper-card-grid">
                        ${offerings.map(item => `
                            <article class="mapper-info-card mapper-info-service">
                                <div class="mapper-info-icon">${visualIcon("spark")}</div>
                                <h3>${escapeHtml(item.name)}</h3>
                                <p>${escapeHtml(item.what_it_is)}</p>
                                ${item.why_relevant ? `
                                    <p class="mapper-info-why">
                                        <strong>For you:</strong>
                                        ${escapeHtml(item.why_relevant)}
                                    </p>
                                ` : ""}
                            </article>
                        `).join("")}
                    </div>
                `;
            }
        }

        if (frameworks.length) {
            body = createSection({
                id: "mapper-methods-section",
                number: next(),
                kicker: "METHODS",
                title: "How Terragni approaches it"
            });

            if (body) {
                body.innerHTML = `
                    <div class="mapper-card-grid">
                        ${frameworks.map(item => `
                            <article class="mapper-info-card mapper-info-method">
                                <div class="mapper-info-icon">${visualIcon("layers")}</div>
                                <h3>${escapeHtml(item.name)}</h3>
                                <p>${escapeHtml(item.what_it_is)}</p>
                            </article>
                        `).join("")}
                    </div>
                `;
            }
        }

        if (cases.length) {
            body = createSection({
                id: "mapper-examples-section",
                number: next(),
                kicker: "BANKING EXAMPLES",
                title: "Where Terragni has done this before",
                intro: "Real Terragni projects, shown without client names."
            });

            if (body) {
                body.innerHTML = `
                    <div class="mapper-card-grid">
                        ${cases.map(item => `
                            <article class="mapper-info-card mapper-info-example">
                                <div class="mapper-info-icon">${visualIcon("bank")}</div>
                                <h3>${escapeHtml(item.title)}</h3>
                                ${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}
                                ${item.outcome ? `
                                    <p class="mapper-info-why">
                                        <strong>Result:</strong>
                                        ${escapeHtml(item.outcome)}
                                    </p>
                                ` : ""}
                                ${item.why_relevant ? `
                                    <p class="mapper-info-why">${escapeHtml(item.why_relevant)}</p>
                                ` : ""}
                            </article>
                        `).join("")}
                    </div>
                `;
            }
        }

        if (sources.length) {
            body = createSection({
                id: "mapper-sources-section",
                number: next(),
                kicker: "SOURCES",
                title: "Where this answer came from"
            });

            if (body) {
                body.innerHTML = `
                    <ul class="mapper-source-list">
                        ${sources.map(source => `<li>${visualIcon("doc")}<span>${escapeHtml(source)}</span></li>`).join("")}
                    </ul>
                `;
            }
        }

        body = createSection({
            id: "mapper-knowledge-next-section",
            number: next(),
            kicker: "WHAT NEXT",
            title: data?.offer_challenge
                ? "Would you like us to look at your own challenge?"
                : "Keep exploring, or talk to Terragni.",
            className: "mapper-next-section"
        });

        if (body) {
            body.innerHTML = `
                ${suggestionChipsHtml(knowledge.suggested_questions)}
                ${contactCtaHtml(describeChallengeButton)}
            `;
            bindSuggestionChips(body);
        }

        renderKnowledgeVisuals(knowledge);

        saveContactContext({
            path: "knowledge",
            summary: knowledge.answer || "",
            suggested_services: offerings.map(item => item.name)
        });

        revealSections();
        showResultsPage();
        announceResult(currentResponse?.path || "knowledge", currentResponse);
    }


    /* ============================================================
       OUT-OF-SCOPE PAGE (NON-BANKING CHALLENGE)
       ============================================================ */

    function renderOutOfScopeResult(data) {
        clearResult();

        currentResponse = data;

        renderContext(data);

        setResultsBanner("knowledge");

        if (dynamicTitle) {
            dynamicTitle.textContent =
                "This prototype covers banking for now.";
        }

        setStatusPanel(
            "not_supported",
            "OUTSIDE THIS PROTOTYPE",
            "We cannot match this challenge to past work yet.",
            "—"
        );

        let body = createSection({
            id: "mapper-question-section",
            number: "01",
            kicker: "YOUR CHALLENGE",
            title: "Here is what you shared.",
            className: "mapper-challenge-section"
        });

        if (body) {
            body.innerHTML = questionCardHtml("");
        }

        body = createSection({
            id: "mapper-scope-section",
            number: "02",
            kicker: "WHAT WE CAN DO",
            title: "You can still learn about Terragni, or talk to our team.",
            className: "mapper-next-section"
        });

        if (body) {
            body.innerHTML = `
                <p class="mapper-notice">${escapeHtml(data?.message || "")}</p>
                ${suggestionChipsHtml(data?.suggested_questions)}
                ${contactCtaHtml()}
            `;
            bindSuggestionChips(body);
        }

        saveContactContext({
            path: "out_of_scope",
            summary: ""
        });

        revealSections();
        showResultsPage();
        announceResult(currentResponse?.path || "knowledge", currentResponse);
    }


    /* ============================================================
       FORM
       ============================================================ */

    if (form) {
        form.addEventListener(
            "submit",
            event => {
                event.preventDefault();

                clearError();

                if (!validateQuery()) {
                    return;
                }

                const industry =
                    valueOf(
                        industryInput
                    );

                const role =
                    valueOf(
                        roleInput
                    );

                const challenge =
                    valueOf(
                        challengeInput
                    );

                submitQuery(
                    challenge,
                    industry,
                    role,
                    {
                        mode: currentMode
                    }
                );
            }
        );
    }


    /* ============================================================
       INPUT INTERACTIONS
       ============================================================ */

    if (industryInput) {
        industryInput.addEventListener(
            "focus",
            () => {
                setJourneyStep(1);
            }
        );
    }

    /*
     * Role picker: a click-to-choose list. "Other" reveals a text box.
     * The chosen role is always written into #role-input, which the rest
     * of the app reads.
     */
    if (roleSelect && roleInput) {
        roleSelect.addEventListener("change", () => {
            const isOther = roleSelect.value === "__other";
            roleInput.hidden = !isOther;
            roleInput.value = isOther ? "" : roleSelect.value;
            roleSelect.closest(".mapper-field")?.classList.toggle("has-other", isOther);
            clearError();
            setJourneyStep(1);
            if (isOther) {
                roleInput.focus();
            }
        });
    }

    if (roleInput) {
        roleInput.addEventListener(
            "focus",
            () => {
                setJourneyStep(1);
            }
        );
    }

    if (challengeInput) {
        challengeInput.addEventListener(
            "focus",
            () => {
                setJourneyStep(2);
            }
        );

        challengeInput.addEventListener(
            "input",
            () => {
                updateCharacterCount();
                setJourneyStep(2);
            }
        );

        challengeInput.addEventListener(
            "keydown",
            event => {
                if (
                    (event.ctrlKey ||
                        event.metaKey) &&
                    event.key === "Enter"
                ) {
                    event.preventDefault();

                    if (
                        validateQuery()
                    ) {
                        form?.requestSubmit();
                    }
                }
            }
        );
    }


    /* ============================================================
       EXPLORE RESULTS
       ============================================================ */

    if (exploreResultsButton) {
        exploreResultsButton.addEventListener(
            "click",
            () => {
                const firstSection =
                    $(".av-page") || $(".mapper-result-section");

                scrollToElement(
                    firstSection ||
                    journeyContent ||
                    results,
                    30
                );
            }
        );
    }


    /* ============================================================
       RESET
       ============================================================ */

    function resetMapper() {
        document.dispatchEvent(new CustomEvent("terragni:reset"));
        stopLoading();

        currentChallenge = "";
        currentIndustry = "";
        currentRole = "";
        currentResponse = null;
        currentVisualPlan = null;

        clearError();
        clearResult();

        hide(loading);
        hide(results);
        hide(matchStatusPanel);
        hide(clarificationSection);

        show(hero);

        if (challengeInput) {
            challengeInput.value = "";
        }

        if (clarificationInput) {
            clarificationInput.value = "";
        }

        if (clarificationSubmitButton) {
            clarificationSubmitButton.disabled = false;
            clarificationSubmitButton.textContent =
                "Re-run the Terragni lens →";
        }

        updateCharacterCount();
        resetJourneyStep();

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });
    }

    if (resetButton) {
        resetButton.addEventListener(
            "click",
            resetMapper
        );
    }


    /* ============================================================
       SOLUTION DRAWER
       ============================================================ */

    function openOfferingDrawer(
        offering
    ) {
        if (!drawer) {
            return;
        }

        const title =
            getName(offering) ||
            "Terragni direction";

        const description =
            getDescription(offering) ||
            getSolutionDescription(
                currentResponse || {}
            );

        const why =
            getWhy(offering) ||
            getSolutionWhy(
                currentResponse || {}
            );

        const steps =
            getSteps(offering);

        if (drawerTitle) {
            drawerTitle.textContent =
                title;
        }

        if (drawerBody) {
            drawerBody.innerHTML = `

                ${
                    description
                        ? `
                            <div class="drawer-block">

                                <span>
                                    WHAT IT IS
                                </span>

                                <p>
                                    ${escapeHtml(
                                        description
                                    )}
                                </p>

                            </div>
                        `
                        : ""
                }

                ${
                    why
                        ? `
                            <div class="drawer-block">

                                <span>
                                    WHY IT IS RELEVANT
                                </span>

                                <p>
                                    ${escapeHtml(
                                        why
                                    )}
                                </p>

                            </div>
                        `
                        : ""
                }

                ${
                    steps.length
                        ? `
                            <div class="drawer-block">

                                <span>
                                    HOW IT WORKS
                                </span>

                                <div class="drawer-steps">

                                    ${
                                        steps
                                            .slice(0, 5)
                                            .map(
                                                (
                                                    step,
                                                    index
                                                ) => `
                                                    <div class="drawer-step">

                                                        <b>
                                                            ${String(
                                                                index + 1
                                                            ).padStart(2, "0")}
                                                        </b>

                                                        <p>
                                                            ${escapeHtml(
                                                                typeof step === "string"
                                                                    ? step
                                                                    : (
                                                                        getDescription(step) ||
                                                                        getName(step)
                                                                    )
                                                            )}
                                                        </p>

                                                    </div>
                                                `
                                            )
                                            .join("")
                                    }

                                </div>

                            </div>
                        `
                        : ""
                }

            `;
        }

        show(drawer);

        document.body.classList.add(
            "drawer-open"
        );

        drawer.setAttribute(
            "aria-hidden",
            "false"
        );
    }

    function closeSolutionDrawer() {
        if (!drawer) {
            return;
        }

        hide(drawer);

        document.body.classList.remove(
            "drawer-open"
        );

        drawer.setAttribute(
            "aria-hidden",
            "true"
        );
    }

    if (closeDrawer) {
        closeDrawer.addEventListener(
            "click",
            closeSolutionDrawer
        );
    }

    if (drawer) {
        const backdrop =
            $(".drawer-backdrop", drawer);

        if (backdrop) {
            backdrop.addEventListener(
                "click",
                closeSolutionDrawer
            );
        }
    }

    document.addEventListener(
        "keydown",
        event => {
            if (
                event.key === "Escape" &&
                drawer &&
                !drawer.classList.contains(
                    "hidden"
                )
            ) {
                closeSolutionDrawer();
            }
        }
    );


    /* ============================================================
       FOCUS STATES
       ============================================================ */

    [
        industryInput,
        roleInput,
        challengeInput
    ]
        .filter(Boolean)
        .forEach(input => {

            input.addEventListener(
                "focus",
                () => {
                    input.closest(
                        ".field, .form-field, .input-field"
                    )?.classList.add(
                        "is-focused"
                    );
                }
            );

            input.addEventListener(
                "blur",
                () => {
                    input.closest(
                        ".field, .form-field, .input-field"
                    )?.classList.remove(
                        "is-focused"
                    );
                }
            );

        });


    /* ============================================================
       INITIAL STATE
       ============================================================ */

    if (results) {
        hide(results);

        results.setAttribute(
            "aria-busy",
            "false"
        );
    }

    hide(loading);
    hide(matchStatusPanel);
    hide(clarificationSection);

    resetJourneyStep();
    updateCharacterCount();
    setMode(currentMode);
    renderHomeVisuals();


    /* ============================================================
       DEBUG API
       ============================================================ */

    window.TerragniMapper = {

        reset:
            resetMapper,
        /*
         * Render a saved /api/ask response (for design checks without
         * spending AI calls): TerragniMapper.preview(response, text, industry, role)
         */
        preview(data, text = "", industry = "Banking", role = "") {
            currentChallenge = text;
            currentIndustry = industry;
            currentRole = role;
            if (data?.path === "knowledge") {
                renderKnowledgeResult(data);
            } else if (data?.path === "out_of_scope") {
                renderOutOfScopeResult(data);
            } else {
                renderResult(data || {});
            }
        },

        getState() {
            return {
                challenge:
                    currentChallenge,

                industry:
                    currentIndustry,

                role:
                    currentRole,

                hasResult:
                    Boolean(
                        currentResponse
                    ),

                hasVisualPlan:
                    Boolean(
                        currentVisualPlan
                    ),

                visualPlan:
                    currentVisualPlan
            };
        }

    };

});