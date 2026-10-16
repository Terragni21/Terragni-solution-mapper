/*
============================================================
TERRAGNI SOLUTION MAPPER
GENERIC VISUAL PLANNER

Purpose:
- Read the generated solution.
- Identify concepts that may benefit from visual explanation.
- Produce a generic visual plan.
- Never depend on industry-specific rules.
- Never assume a particular solution.
- Never force a visual when one is not useful.

This module does NOT generate images itself.

It creates a visual specification that the renderer
can later turn into SVG, HTML/CSS visuals, or
AI-generated conceptual imagery.
============================================================
*/

(function () {
    "use strict";


    /* ============================================================
       BASIC HELPERS
       ============================================================ */

    function clean(value) {
        if (
            value === null ||
            value === undefined
        ) {
            return "";
        }

        return String(value).trim();
    }


    function array(value) {
        return Array.isArray(value)
            ? value
            : [];
    }


    function first(...values) {
        for (const value of values) {
            if (
                value !== null &&
                value !== undefined &&
                clean(value)
            ) {
                return value;
            }
        }

        return "";
    }


    function object(value) {
        return (
            value &&
            typeof value === "object" &&
            !Array.isArray(value)
        )
            ? value
            : {};
    }


    function itemText(item) {
        if (typeof item === "string") {
            return item;
        }

        const source = object(item);

        return first(
            source.name,
            source.title,
            source.label,
            source.description,
            source.summary,
            source.text,
            source.value
        );
    }


    function itemDescription(item) {
        const source = object(item);

        return first(
            source.description,
            source.summary,
            source.explanation,
            source.details,
            source.why_relevant,
            source.relevance
        );
    }


    function unique(values) {
        return Array.from(
            new Set(
                values
                    .map(clean)
                    .filter(Boolean)
            )
        );
    }


    /* ============================================================
       SOLUTION NORMALISATION
       ============================================================ */

    function normaliseSolution(data) {

        const source = object(data);

        const perspective =
            object(
                source.perspective
            );

        const solution =
            object(
                source.solution
            );

        return {

            challenge:
                first(
                    source.challenge,
                    source.query,
                    solution.challenge
                ),

            interpretation:
                first(
                    source.interpretation,
                    source.business_tension,
                    source.underlying_tension,
                    source.diagnosis,
                    solution.interpretation,
                    solution.diagnosis
                ),

            friction:
                array(
                    source.friction ||
                    source.challenge_anatomy ||
                    source.friction_points ||
                    solution.friction
                ),

            perspective:
                first(
                    typeof source.perspective === "string"
                        ? source.perspective
                        : "",
                    perspective.summary,
                    perspective.perspective,
                    perspective.point_of_view,
                    perspective.description,
                    solution.perspective
                ),

            perspectivePoints:
                array(
                    perspective.points ||
                    perspective.insights ||
                    perspective.key_points
                ),

            direction:
                first(
                    source.recommended_direction,
                    source.recommendation,
                    source.primary_offering,
                    source.direction,
                    solution.direction
                ),

            directionDescription:
                first(
                    source.solution_copy,
                    source.solution_description,
                    source.recommended_direction_description,
                    solution.description
                ),

            howItWorks:
                array(
                    source.how_it_works ||
                    source.steps ||
                    source.process ||
                    solution.how_it_works
                ),

            frameworks:
                array(
                    source.frameworks ||
                    source.toolkit ||
                    source.methods ||
                    solution.frameworks
                ),

            outcomes:
                array(
                    source.outcomes ||
                    source.impact ||
                    source.success_measures ||
                    solution.outcomes
                ),

            nextStep:
                first(
                    source.next_step,
                    source.next_move,
                    source.suggested_next_move,
                    solution.next_step
                )
        };
    }


    /* ============================================================
       TEXT CORPUS
       ============================================================ */

    function buildCorpus(solution) {

        const parts = [

            solution.challenge,

            solution.interpretation,

            solution.perspective,

            solution.direction,

            solution.directionDescription,

            solution.nextStep

        ];

        solution.friction.forEach(item => {
            parts.push(itemText(item));
            parts.push(itemDescription(item));
        });

        solution.perspectivePoints.forEach(item => {
            parts.push(itemText(item));
            parts.push(itemDescription(item));
        });

        solution.howItWorks.forEach(item => {
            parts.push(itemText(item));
            parts.push(itemDescription(item));
        });

        solution.frameworks.forEach(item => {
            parts.push(itemText(item));
            parts.push(itemDescription(item));
        });

        solution.outcomes.forEach(item => {
            parts.push(itemText(item));
            parts.push(itemDescription(item));
        });

        return parts
            .map(clean)
            .filter(Boolean)
            .join(" ");
    }


    /* ============================================================
       CONCEPT DETECTION

       IMPORTANT:
       This is NOT industry logic.

       These are generic semantic signals used only to decide
       whether a concept may benefit from visualisation.
       ============================================================ */

    function containsAny(text, terms) {

        const source =
            clean(text).toLowerCase();

        return terms.some(
            term =>
                source.includes(
                    term.toLowerCase()
                )
        );
    }


    function detectSignals(solution) {

        const corpus =
            buildCorpus(solution);

        return {

            sequence:
                solution.howItWorks.length >= 2 ||
                containsAny(
                    corpus,
                    [
                        "step",
                        "stage",
                        "journey",
                        "process",
                        "from",
                        "through",
                        "then",
                        "before",
                        "after"
                    ]
                ),

            relationships:
                solution.friction.length >= 2 ||
                solution.frameworks.length >= 2 ||
                containsAny(
                    corpus,
                    [
                        "relationship",
                        "connected",
                        "interaction",
                        "reinforce",
                        "influence",
                        "drives",
                        "creates",
                        "depends"
                    ]
                ),

            tension:
                containsAny(
                    corpus,
                    [
                        "tension",
                        "gap",
                        "friction",
                        "barrier",
                        "resistance",
                        "conflict",
                        "disconnect",
                        "stuck",
                        "uncertainty"
                    ]
                ),

            transformation:
                containsAny(
                    corpus,
                    [
                        "change",
                        "transform",
                        "adopt",
                        "shift",
                        "move",
                        "redesign",
                        "improve",
                        "transition",
                        "behaviour"
                    ]
                ),

            comparison:
                containsAny(
                    corpus,
                    [
                        "versus",
                        "rather than",
                        "instead of",
                        "old",
                        "new",
                        "current",
                        "future",
                        "before",
                        "after"
                    ]
                ),

            stages:
                solution.howItWorks.length >= 3,

            multipleOutcomes:
                solution.outcomes.length >= 2
        };
    }


    /* ============================================================
       VISUAL SPEC FACTORIES
       ============================================================ */

    function flowVisual(solution) {

        const steps =
            solution.howItWorks
                .slice(0, 6)
                .map(item => ({
                    label: itemText(item),
                    description:
                        itemDescription(item)
                }))
                .filter(item => item.label);

        return {

            medium: "diagram",

            type: "flow",

            purpose:
                "Make the sequence of the intervention easier to understand.",

            title:
                "How the direction moves from insight to change.",

            data: {
                steps
            }
        };
    }


    function relationshipVisual(solution) {

        const nodes = unique([

            ...solution.friction
                .slice(0, 5)
                .map(itemText),

            ...solution.frameworks
                .slice(0, 4)
                .map(itemText),

            solution.direction

        ]);

        return {

            medium: "diagram",

            type: "relationship_map",

            purpose:
                "Show the important forces or elements connected to the challenge.",

            title:
                "The forces shaping the situation.",

            data: {
                nodes
            }
        };
    }


    function transformationVisual(solution) {

        return {

            medium: "diagram",

            type: "transformation",

            purpose:
                "Make the movement from the current condition toward the desired condition visible.",

            title:
                "From the current condition to meaningful change.",

            data: {

                current:
                    first(
                        solution.challenge,
                        solution.interpretation
                    ),

                intervention:
                    first(
                        solution.direction,
                        solution.directionDescription
                    ),

                desired:
                    solution.outcomes
                        .slice(0, 3)
                        .map(itemText)
                        .filter(Boolean)

            }
        };
    }


    function tensionVisual(solution) {

        return {

            medium: "diagram",

            type: "tension_map",

            purpose:
                "Make the gap between the visible symptom and the underlying issue easier to understand.",

            title:
                "Where the tension is being created.",

            data: {

                visible:
                    first(
                        solution.challenge,
                        "Visible business symptom"
                    ),

                underlying:
                    first(
                        solution.interpretation,
                        solution.perspective,
                        "Underlying business tension"
                    ),

                friction:
                    solution.friction
                        .slice(0, 4)
                        .map(itemText)
                        .filter(Boolean)

            }
        };
    }


    /* ============================================================
       CONCEPTUAL IMAGE SPEC
       ============================================================ */

    function conceptualImageVisual(
        solution
    ) {

        return {

            medium:
                "conceptual_image",

            type:
                "editorial_concept",

            purpose:
                "Provide a visual metaphor for the central idea when a conceptual image can communicate it better than a diagram.",

            title:
                first(
                    solution.perspective,
                    solution.direction,
                    "The Terragni perspective"
                ),

            promptContext: {

                challenge:
                    solution.challenge,

                interpretation:
                    solution.interpretation,

                perspective:
                    solution.perspective,

                direction:
                    solution.direction,

                outcomes:
                    solution.outcomes
                        .slice(0, 3)
                        .map(itemText)
                        .filter(Boolean)

            },

            visualRules: {

                style:
                    "premium editorial consulting",

                palette:
                    [
                        "Terragni cream",
                        "deep purple",
                        "soft lavender",
                        "restrained muted gold",
                        "dark ink"
                    ],

                composition:
                    "clean editorial composition with generous negative space",

                textInImage:
                    false,

                stockPhotography:
                    false,

                genericCorporatePhotography:
                    false,

                decorativeOnly:
                    false
            }
        };
    }


    /* ============================================================
       VISUAL SELECTION
       ============================================================ */

    function chooseVisuals(
        solution,
        signals
    ) {

        const visuals = [];


        /*
        Priority 1:
        If there is a strong tension between visible symptom
        and underlying issue, a tension visual is useful.
        */

        if (
            signals.tension &&
            solution.interpretation
        ) {

            visuals.push({
                id: "dynamic-tension",
                placement: "interpretation",
                priority: "high",
                ...tensionVisual(solution)
            });
        }


        /*
        Priority 2:
        A multi-step intervention naturally benefits from
        a process visual.
        */

        if (
            signals.sequence &&
            solution.howItWorks.length >= 2
        ) {

            visuals.push({
                id: "dynamic-flow",
                placement: "how_it_works",
                priority: "high",
                ...flowVisual(solution)
            });
        }


        /*
        Priority 3:
        Multiple forces/frameworks can benefit from a map.
        */

        if (
            signals.relationships &&
            solution.friction.length +
            solution.frameworks.length >= 2
        ) {

            visuals.push({
                id: "dynamic-relationship-map",
                placement: "challenge_anatomy",
                priority: "medium",
                ...relationshipVisual(solution)
            });
        }


        /*
        Priority 4:
        Transformation is useful when the solution describes
        meaningful movement from current to desired state.
        */

        if (
            signals.transformation &&
            solution.outcomes.length
        ) {

            visuals.push({
                id: "dynamic-transformation",
                placement: "outcomes",
                priority: "medium",
                ...transformationVisual(solution)
            });
        }


        /*
        Conceptual image:
        Use sparingly.

        It is deliberately not tied to industry or section.
        It is only considered when the solution contains
        a strong central perspective.
        */

        if (
            solution.perspective &&
            (
                signals.tension ||
                signals.transformation
            )
        ) {

            visuals.push({
                id: "dynamic-concept",
                placement: "direction",
                priority: "medium",
                ...conceptualImageVisual(solution)
            });
        }


        /*
        Prevent visual overload.

        The planner can theoretically generate many candidates,
        but the page should remain editorial.
        */

        return visuals.slice(0, 4);
    }


    /* ============================================================
       PUBLIC PLANNER
       ============================================================ */

    function createVisualPlan(
        response
    ) {

        const solution =
            normaliseSolution(response);

        const signals =
            detectSignals(solution);

        const visuals =
            chooseVisuals(
                solution,
                signals
            );

        return {

            version:
                "1.0",

            generated:
                true,

            visual_needed:
                visuals.length > 0,

            signals,

            visuals
        };
    }


    /* ============================================================
       PUBLIC API
       ============================================================ */

    window.TerragniVisualPlanner = {

        createVisualPlan,

        normaliseSolution,

        detectSignals

    };

})();