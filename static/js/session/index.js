import { appendMessageToTab, createMessageWrapper, getActiveTabPane, scrollToBottom } from './dom.js';
import { renderHistoryMarkdown, renderMarkdownInto } from './markdown.js';
import { QUICK_ACTIONS } from './quick-actions.js';
import { addReviewChange, createReviewProgressCard, updateReviewStep } from './review-ui.js';

const bootstrap = window.PLANNING_SESSION_BOOTSTRAP;
const projectId = bootstrap.projectId;

function registerPlanningSession() {
    if (!window.Alpine || window.__planningSessionRegistered) {
        return;
    }

    window.Alpine.data('planningSession', () => ({
        activeTab: bootstrap.initialTab,
        sending: false,
        phases: bootstrap.phases,
        unlockedBanner: null,
        _bannerTimer: null,

        get quickActions() {
            return QUICK_ACTIONS[this.activeTab] || [];
        },

        switchTab(key) {
            this.activeTab = key;
            this.$nextTick(() => scrollToBottom());
        },

        updatePhases(newPhases) {
            const prevByKey = Object.fromEntries(this.phases.map((phase) => [phase.key, phase]));
            for (const phase of newPhases) {
                if (phase.unlocked && !prevByKey[phase.key]?.unlocked) {
                    this.showUnlockedBanner(`${phase.icon} ${phase.label} phase unlocked!`);
                }
            }
            this.phases = newPhases;
        },

        showUnlockedBanner(msg) {
            clearTimeout(this._bannerTimer);
            this.unlockedBanner = msg;
            this._bannerTimer = setTimeout(() => {
                this.unlockedBanner = null;
            }, 4000);
        },

        async submitMessage(preset = null) {
            if (this.sending) {
                return;
            }
            const input = document.getElementById('message-input');
            const content = preset ?? input.value.trim();
            if (!content) {
                return;
            }

            if (content === '__FULL_REVIEW__') {
                await this.triggerFullReview();
                return;
            }

            document.querySelectorAll('.suggestion-chips').forEach((el) => el.remove());

            this.sending = true;
            input.value = '';
            input.style.height = 'auto';

            appendMessageToTab('user', content, this.activeTab);
            document.getElementById('typing-indicator').classList.remove('hidden');
            scrollToBottom();

            try {
                await this.streamChat(content);
            } catch (err) {
                console.error('Chat error:', err);
                appendMessageToTab('assistant', '⚠️ Something went wrong. Please try again.', this.activeTab);
            } finally {
                this.sending = false;
                document.getElementById('typing-indicator').classList.add('hidden');

                const bubble = document.getElementById('streaming-bubble');
                if (bubble && bubble.dataset.raw) {
                    renderMarkdownInto(bubble, bubble.dataset.raw);
                    bubble.classList.add('prose-content');
                    delete bubble.dataset.raw;
                }
                if (bubble) {
                    bubble.removeAttribute('id');
                }

                const prevThinking = document.getElementById('thinking-content');
                if (prevThinking) {
                    prevThinking.removeAttribute('id');
                }
                const prevWrapper = document.getElementById('thinking-wrapper');
                if (prevWrapper) {
                    prevWrapper.removeAttribute('id');
                }
            }
        },

        async streamChat(content) {
            const response = await fetch(`/projects/${projectId}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `content=${encodeURIComponent(content)}&role_tab=${encodeURIComponent(this.activeTab)}`,
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n\n');
                buffer = parts.pop();
                for (const part of parts) {
                    this.handleSseBlock(part);
                }
            }
            if (buffer.trim()) {
                this.handleSseBlock(buffer);
            }
        },

        handleSseBlock(block) {
            let eventName = 'message';
            let dataStr = '';
            for (const line of block.split('\n')) {
                if (line.startsWith('event: ')) {
                    eventName = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    dataStr = line.slice(6).trim();
                }
            }
            if (!dataStr) {
                return;
            }

            let data = {};
            try {
                data = JSON.parse(dataStr);
            } catch {
                return;
            }

            switch (eventName) {
                case 'thinking':
                    this.appendThinking(data.content || '');
                    break;
                case 'token':
                    this.appendToken(data.content || '');
                    break;
                case 'tool_used':
                    htmx.ajax('GET', `/projects/${projectId}/knowledge-panel`, {
                        target: '#knowledge-panel',
                        swap: 'innerHTML',
                    });
                    htmx.ajax('GET', `/projects/${projectId}/doc-tree`, {
                        target: '#doc-sidebar-content',
                        swap: 'innerHTML',
                    });
                    this.refreshPhaseStatus();
                    break;
                case 'done':
                    document.getElementById('typing-indicator').classList.add('hidden');
                    if (data.phases) {
                        this.updatePhases(data.phases);
                    }
                    if (data.suggestions?.length) {
                        this.showSuggestions(data.suggestions);
                    }
                    break;
                case 'error':
                    appendMessageToTab('assistant', `⚠️ ${data.message || 'Unknown error'}`, this.activeTab);
                    break;
            }
        },

        async refreshPhaseStatus() {
            try {
                const resp = await fetch(`/projects/${projectId}/phase-status`);
                if (resp.ok) {
                    this.updatePhases(await resp.json());
                }
            } catch {
                // non-critical
            }
        },

        appendThinking(text) {
            let content = document.getElementById('thinking-content');
            if (!content) {
                const wrapper = document.createElement('div');
                wrapper.id = 'thinking-wrapper';
                wrapper.className = 'flex gap-3';
                wrapper.innerHTML = `
                    <div class="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-xs shrink-0 mt-0.5">💭</div>
                    <div class="flex-1 max-w-xl min-w-0">
                        <details open class="group">
                            <summary class="text-xs text-gray-400 cursor-pointer select-none list-none flex items-center gap-1 mb-1">
                                <span class="group-open:rotate-90 transition-transform inline-block">▶</span>
                                <span>Thinking…</span>
                            </summary>
                            <div id="thinking-content"
                                 class="bg-gray-50 border border-gray-100 rounded-xl px-3 py-2 text-xs text-gray-500 font-mono whitespace-pre-wrap max-h-52 overflow-y-auto leading-relaxed"></div>
                        </details>
                    </div>`;
                getActiveTabPane().appendChild(wrapper);
                document.getElementById('typing-indicator').classList.add('hidden');
                content = document.getElementById('thinking-content');
            }
            content.textContent += text;
            scrollToBottom();
        },

        appendToken(text) {
            const thinkingWrapper = document.getElementById('thinking-wrapper');
            if (thinkingWrapper && !document.getElementById('streaming-bubble')) {
                const details = thinkingWrapper.querySelector('details');
                if (details) {
                    details.removeAttribute('open');
                }
            }

            let bubble = document.getElementById('streaming-bubble');
            if (!bubble) {
                const wrapper = createMessageWrapper('assistant');
                bubble = wrapper.querySelector('.message-content');
                bubble.id = 'streaming-bubble';
                bubble.dataset.raw = '';
                getActiveTabPane().appendChild(wrapper);
                document.getElementById('typing-indicator').classList.add('hidden');
            }
            bubble.dataset.raw += text;
            bubble.textContent = bubble.dataset.raw;
            scrollToBottom();
        },

        showSuggestions(suggestions) {
            const chips = document.createElement('div');
            chips.className = 'suggestion-chips flex flex-wrap gap-2 pl-10 pt-1 pb-2';
            suggestions.forEach((text) => {
                const btn = document.createElement('button');
                btn.className = [
                    'text-xs px-3 py-1.5 rounded-full',
                    'border border-blue-200 text-blue-600 bg-white',
                    'hover:bg-blue-50 hover:border-blue-400',
                    'transition-colors cursor-pointer select-none',
                ].join(' ');
                btn.textContent = text;
                btn.addEventListener('click', () => this.submitMessage(text));
                chips.appendChild(btn);
            });
            getActiveTabPane().appendChild(chips);
            scrollToBottom();
        },

        async triggerFullReview() {
            if (this.sending) {
                return;
            }
            this.sending = true;

            const card = createReviewProgressCard();
            const pane = document.getElementById('tab-pane-review');
            if (pane) {
                pane.appendChild(card);
            }
            scrollToBottom();

            try {
                const response = await fetch(`/projects/${projectId}/review/full`, {
                    method: 'POST',
                });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) {
                        break;
                    }
                    buffer += decoder.decode(value, { stream: true });
                    const parts = buffer.split('\n\n');
                    buffer = parts.pop();
                    for (const part of parts) {
                        this.handleReviewSse(part, card);
                    }
                }
                if (buffer.trim()) {
                    this.handleReviewSse(buffer, card);
                }
            } catch (err) {
                console.error('Full review error:', err);
                const errEl = card.querySelector('.review-error');
                if (errEl) {
                    errEl.textContent = `⚠️ Review failed: ${err.message}`;
                    errEl.classList.remove('hidden');
                }
            } finally {
                this.sending = false;
                htmx.ajax('GET', `/projects/${projectId}/knowledge-panel`, {
                    target: '#knowledge-panel',
                    swap: 'innerHTML',
                });
                htmx.ajax('GET', `/projects/${projectId}/doc-tree`, {
                    target: '#doc-sidebar-content',
                    swap: 'innerHTML',
                });
            }
        },

        handleReviewSse(block, card) {
            let eventName = 'message';
            let dataStr = '';
            for (const line of block.split('\n')) {
                if (line.startsWith('event: ')) {
                    eventName = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    dataStr = line.slice(6).trim();
                }
            }
            if (!dataStr) {
                return;
            }

            let data = {};
            try {
                data = JSON.parse(dataStr);
            } catch {
                return;
            }

            if (eventName === 'review_progress') {
                updateReviewStep(card, data.step, data.status);
            } else if (eventName === 'tool_used') {
                addReviewChange(card, data.name, data.result);
                htmx.ajax('GET', `/projects/${projectId}/knowledge-panel`, {
                    target: '#knowledge-panel',
                    swap: 'innerHTML',
                });
            } else if (eventName === 'done') {
                if (data.phases) {
                    this.updatePhases(data.phases);
                }
                const summary = card.querySelector('.review-summary');
                const changes = card.querySelectorAll('.review-change').length;
                if (summary) {
                    summary.textContent = changes > 0
                        ? `✓ Review complete — ${changes} change${changes !== 1 ? 's' : ''} made`
                        : '✓ Review complete — no changes needed';
                }
            }
        },

        autoResize(el) {
            el.style.height = 'auto';
            el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
        },
    }));

    window.__planningSessionRegistered = true;
}

registerPlanningSession();
document.addEventListener('alpine:init', registerPlanningSession, { once: true });
document.addEventListener('DOMContentLoaded', () => {
    renderHistoryMarkdown();
    scrollToBottom();
});
