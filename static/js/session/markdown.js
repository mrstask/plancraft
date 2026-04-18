function sanitizeHtml(html) {
    if (window.DOMPurify) {
        return window.DOMPurify.sanitize(html);
    }
    console.error('DOMPurify is not loaded — HTML sanitization is disabled. Raw HTML will NOT be rendered.');
    return '';
}

export function renderMarkdown(text) {
    return sanitizeHtml(window.marked.parse(text));
}

export function renderMarkdownInto(el, text) {
    el.innerHTML = renderMarkdown(text);
}

export function renderHistoryMarkdown() {
    document.querySelectorAll('.history-md').forEach((el) => {
        renderMarkdownInto(el, el.textContent);
    });
}
