/*
 * Terragni Solution Mapper - contact form.
 *
 * Reads the journey context saved by app.js (role, industry, question,
 * diagnosed problem) and sends it with the visitor's details to /api/lead,
 * so Terragni's team is prepared for the first call.
 */
document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    const form = document.getElementById("lead-form");
    if (!form) return;

    const contextBox = document.getElementById("lead-context");
    const result = document.getElementById("lead-result");
    const submit = document.getElementById("lead-submit");

    const escapeHtml = value =>
        String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");

    let context = {};

    try {
        context = JSON.parse(
            window.sessionStorage.getItem("terragniContactContext") || "{}"
        ) || {};
    } catch (error) {
        context = {};
    }

    if (context.role || context.industry || context.question) {
        const pathLabel = {
            challenge: "Your challenge",
            knowledge: "Your question",
            out_of_scope: "Your challenge"
        }[context.path] || "Your question";

        contextBox.innerHTML = `
            <strong>We will include this from your visit:</strong><br>
            ${escapeHtml(context.role)}${context.role && context.industry ? ", " : ""}${escapeHtml(context.industry)}<br>
            ${context.question ? `${pathLabel}: “${escapeHtml(context.question)}”` : ""}
        `;
        contextBox.hidden = false;
    }

    function showResult(message, isError) {
        result.textContent = message;
        result.className = `lead-message ${isError ? "is-error" : "is-success"}`;
        result.hidden = false;
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const data = {
            name: form.name.value.trim(),
            email: form.email.value.trim(),
            organisation: form.organisation.value.trim(),
            phone: form.phone.value.trim(),
            message: form.message.value.trim(),
            consent: form.consent.checked,
            context
        };

        if (!data.name || !data.email) {
            showResult("Please enter your name and work email.", true);
            return;
        }

        if (!data.consent) {
            showResult("Please agree that Terragni may contact you.", true);
            return;
        }

        submit.disabled = true;

        try {
            const response = await fetch("/api/lead", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                body: JSON.stringify(data)
            });

            const body = await response.json().catch(() => ({}));

            if (!response.ok || body.ok === false) {
                throw new Error(body.error || "We could not send your details.");
            }

            form.reset();
            contextBox.hidden = true;
            showResult(
                body.email_sent
                    ? `Thank you. Your reference is ${body.reference}. We have emailed a confirmation to ${body.email}, and a Terragni consultant will be in touch within 2 working days.`
                    : `Thank you. Your reference is ${body.reference}. A Terragni consultant will be in touch within 2 working days. Please note the reference; you can also write to engage@terragni.co.`,
                false
            );

            try {
                window.sessionStorage.removeItem("terragniContactContext");
            } catch (error) {
                /* ignore */
            }
        } catch (error) {
            showResult(error.message, true);
        } finally {
            submit.disabled = false;
        }
    });
});
