/*
 * Terragni Solution Mapper - visuals.
 *
 * Draws diagrams from the real answer data (no placeholder content):
 *   - icon(name)            small inline SVG icons
 *   - mapDiagram(spec)      radial "Terragni map": the visitor's problem or
 *                           question in the centre, connected to the
 *                           services, methods and banking examples returned
 *   - flowDiagram(steps)    left-to-right "from symptom to solution" flow
 *   - howItWorks()          illustrated four-step strip for the home page
 *
 * Every function returns an HTML/SVG string; app.js decides where it goes.
 */
(function () {
    "use strict";

    const escapeHtml = value =>
        String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");

    /* ------------------------------------------------------------
       ICONS (24x24, stroke-based, inherit currentColor)
       ------------------------------------------------------------ */

    const ICON_PATHS = {
        person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/>',
        paths: '<path d="M12 21v-7"/><path d="M12 14 6 8"/><path d="m12 14 6-6"/><path d="M6 8V4h4"/><path d="M18 8V4h-4"/>',
        search: '<rect x="3" y="3" width="11" height="14" rx="2"/><path d="M6 7h5M6 10h5M6 13h3"/><circle cx="16.5" cy="15.5" r="3.5"/><path d="m19 18 2.5 2.5"/>',
        page: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/><path d="m14 16 1.5 1.5L19 14"/>',
        spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6.3 6.3 2.1 2.1M15.6 15.6l2.1 2.1M6.3 17.7l2.1-2.1M15.6 8.4l2.1-2.1"/><circle cx="12" cy="12" r="2.5"/>',
        layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
        bank: '<path d="M3 10 12 4l9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3 20h18"/>',
        doc: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>',
        target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
        alert: '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/>',
        bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.4 1 1.1 1 1.8V16h5v-.3c0-.7.4-1.4 1-1.8A6 6 0 0 0 12 3Z"/>',
        chat: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
        shield: '<path d="M12 3 4 6v6c0 5 3.4 8.3 8 9 4.6-.7 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/>',
        arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>'
    };

    function icon(name, className = "tv-icon") {
        const paths = ICON_PATHS[name] || ICON_PATHS.spark;
        return `
            <svg class="${escapeHtml(className)}" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
                 stroke-linejoin="round" aria-hidden="true">${paths}</svg>
        `;
    }

    /* ------------------------------------------------------------
       TEXT WRAPPING FOR SVG LABELS
       ------------------------------------------------------------ */

    function wrapLabel(text, maxChars, maxLines) {
        const words = String(text || "").replace(/\s+/g, " ").trim().split(" ");
        const lines = [];
        let line = "";

        words.forEach(word => {
            const candidate = line ? `${line} ${word}` : word;
            if (candidate.length > maxChars && line) {
                lines.push(line);
                line = word;
            } else {
                line = candidate;
            }
        });

        if (line) lines.push(line);

        if (lines.length > maxLines) {
            const kept = lines.slice(0, maxLines);
            kept[maxLines - 1] = kept[maxLines - 1].replace(/\s*\S*$/, "") + "…";
            return kept;
        }

        return lines;
    }

    /* ------------------------------------------------------------
       TERRAGNI MAP (radial diagram)
       spec = {
         centerLabel: "Your challenge",
         centerText: "Customers prefer branches over the app",
         groups: [
           { key: "service", label: "Terragni services", items: ["JUMP", ...] },
           { key: "method",  label: "Methods",           items: [...] },
           { key: "example", label: "Banking examples",  items: [...] }
         ]
       }
       ------------------------------------------------------------ */

    const GROUP_STYLE = {
        service: { color: "#5f4a9e", soft: "#eee9fa", icon: "spark" },
        method: { color: "#c69b45", soft: "#f6ecd6", icon: "layers" },
        example: { color: "#2f8f83", soft: "#dff2ef", icon: "bank" },
        outcome: { color: "#c0563f", soft: "#f8e3dd", icon: "target" }
    };

    function mapDiagram(spec) {
        const groups = (spec.groups || [])
            .map(group => ({
                ...group,
                items: (group.items || []).filter(Boolean).slice(0, 3)
            }))
            .filter(group => group.items.length);

        const nodes = [];
        groups.forEach(group => {
            group.items.forEach(item => nodes.push({ group, text: item }));
        });

        if (!nodes.length) return "";

        const W = 860;
        const H = 500;
        const cx = W / 2;
        const cy = H / 2;
        const rx = 300;
        const ry = 185;
        const nodeW = 196;
        const nodeH = 58;

        // Spread nodes around an ellipse, starting top-left, grouped by type.
        const start = -Math.PI * 0.80;
        const step = (Math.PI * 2) / nodes.length;

        const placed = nodes.map((node, index) => {
            const angle = start + step * index;
            return {
                ...node,
                x: cx + rx * Math.cos(angle),
                y: cy + ry * Math.sin(angle),
                style: GROUP_STYLE[node.group.key] || GROUP_STYLE.service
            };
        });

        const links = placed.map((node, index) => {
            const mx = (cx + node.x) / 2 + (node.y - cy) * 0.12;
            const my = (cy + node.y) / 2 - (node.x - cx) * 0.12;
            return `
                <path class="tv-map-link" style="--d:${index * 120}ms"
                      d="M${cx},${cy} Q${mx.toFixed(1)},${my.toFixed(1)} ${node.x.toFixed(1)},${node.y.toFixed(1)}"
                      stroke="${node.style.color}" />
            `;
        }).join("");

        const nodeSvg = placed.map((node, index) => {
            const lines = wrapLabel(node.text, 22, 2);
            const x = node.x - nodeW / 2;
            const y = node.y - nodeH / 2;
            const textY = node.y - (lines.length - 1) * 8 + 4;
            return `
                <g class="tv-map-node" style="--d:${200 + index * 120}ms">
                    <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${nodeW}" height="${nodeH}" rx="14"
                          fill="${node.style.soft}" stroke="${node.style.color}" stroke-width="1.4"/>
                    <rect x="${x.toFixed(1)}" y="${(y + 10).toFixed(1)}" width="5" height="${nodeH - 20}" rx="2.5" fill="${node.style.color}"/>
                    ${lines.map((line, i) => `
                        <text x="${node.x.toFixed(1)}" y="${(textY + i * 16).toFixed(1)}"
                              text-anchor="middle" class="tv-map-node-text">${escapeHtml(line)}</text>
                    `).join("")}
                    <title>${escapeHtml(node.group.label)}: ${escapeHtml(node.text)}</title>
                </g>
            `;
        }).join("");

        // Keep the centre text inside the circle: short lines, at most four.
        const centerLines = wrapLabel(spec.centerText || "", 17, 4);
        const centerTextY = cy + 14 - (centerLines.length - 1) * 8;

        const legend = groups.map(group => {
            const style = GROUP_STYLE[group.key] || GROUP_STYLE.service;
            return `
                <span class="tv-legend-item">
                    <span class="tv-legend-dot" style="background:${style.color}"></span>
                    ${escapeHtml(group.label)}
                </span>
            `;
        }).join("");

        return `
            <figure class="tv-map" aria-label="${escapeHtml(spec.ariaLabel || "Terragni map")}">
                <svg viewBox="0 0 ${W} ${H}" role="img" preserveAspectRatio="xMidYMid meet">
                    <defs>
                        <radialGradient id="tvCenterGlow" cx="50%" cy="50%" r="50%">
                            <stop offset="0%" stop-color="#5f4a9e" stop-opacity="0.22"/>
                            <stop offset="100%" stop-color="#5f4a9e" stop-opacity="0"/>
                        </radialGradient>
                    </defs>
                    <ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" class="tv-map-orbit"/>
                    <ellipse cx="${cx}" cy="${cy}" rx="${rx * 0.55}" ry="${ry * 0.55}" class="tv-map-orbit tv-map-orbit-inner"/>
                    <circle cx="${cx}" cy="${cy}" r="140" fill="url(#tvCenterGlow)"/>
                    ${links}
                    <g class="tv-map-center">
                        <circle cx="${cx}" cy="${cy}" r="100" fill="#3f316e"/>
                        <circle cx="${cx}" cy="${cy}" r="100" fill="none" stroke="#c69b45" stroke-width="2" stroke-dasharray="4 6"/>
                        <text x="${cx}" y="${cy - 44}" text-anchor="middle" class="tv-map-center-kicker">${escapeHtml((spec.centerLabel || "").toUpperCase())}</text>
                        ${centerLines.map((line, i) => `
                            <text x="${cx}" y="${(centerTextY + i * 17).toFixed(1)}" text-anchor="middle" class="tv-map-center-text">${escapeHtml(line)}</text>
                        `).join("")}
                    </g>
                    ${nodeSvg}
                </svg>
                <figcaption class="tv-legend">${legend}</figcaption>
            </figure>
        `;
    }

    /* ------------------------------------------------------------
       FLOW (symptom -> real problem -> Terragni answer -> outcome)
       steps = [{ kicker, title, text, icon, tone }]
       ------------------------------------------------------------ */

    function flowDiagram(steps) {
        const items = (steps || []).filter(step => step && (step.title || step.text));
        if (!items.length) return "";

        return `
            <div class="tv-flow" style="--tv-steps:${items.length}">
                ${items.map((step, index) => `
                    <div class="tv-flow-step tv-tone-${escapeHtml(step.tone || "default")}" style="--d:${index * 140}ms">
                        <div class="tv-flow-icon">${icon(step.icon || "spark")}</div>
                        <span class="tv-flow-kicker">${String(index + 1).padStart(2, "0")} · ${escapeHtml(step.kicker || "")}</span>
                        <strong class="tv-flow-title">${escapeHtml(step.title || "")}</strong>
                        ${step.text ? `<p class="tv-flow-text">${escapeHtml(step.text)}</p>` : ""}
                    </div>
                    ${index < items.length - 1 ? `<div class="tv-flow-arrow" aria-hidden="true">${icon("arrow")}</div>` : ""}
                `).join("")}
            </div>
        `;
    }

    /* ------------------------------------------------------------
       HOME PAGE: HOW IT WORKS
       ------------------------------------------------------------ */

    function howItWorks() {
        const steps = [
            { icon: "person", title: "Tell us who you are", text: "Your role and industry shape every answer." },
            { icon: "paths", title: "Choose your path", text: "Bring a challenge, or ask about Terragni." },
            { icon: "search", title: "AI reads Terragni's work", text: "It searches real case studies and brochures by meaning." },
            { icon: "page", title: "Get your page", text: "A personalised answer with proof and sources." }
        ];

        return `
            <div class="tv-how">
                <div class="tv-how-head">
                    <span class="tv-how-kicker">HOW IT WORKS</span>
                    <h2>From your words to Terragni's proven work, in seconds.</h2>
                </div>
                <ol class="tv-how-steps">
                    ${steps.map((step, index) => `
                        <li class="tv-how-step">
                            <div class="tv-how-icon">${icon(step.icon)}</div>
                            <span class="tv-how-number">${String(index + 1).padStart(2, "0")}</span>
                            <strong>${escapeHtml(step.title)}</strong>
                            <p>${escapeHtml(step.text)}</p>
                        </li>
                    `).join("")}
                </ol>
                <div class="tv-how-trust">
                    ${icon("shield")}
                    <span>Answers use only Terragni's own material. No invented clients or results, and client names are never shown.</span>
                </div>
            </div>
        `;
    }

    window.TerragniVisuals = {
        icon,
        mapDiagram,
        flowDiagram,
        howItWorks,
        escapeHtml
    };
})();
