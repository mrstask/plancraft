import { scrollToBottom } from './dom.js';

export function createReviewProgressCard() {
    const steps = [
        { key: 'stories', label: 'Stories' },
        { key: 'components', label: 'Components' },
        { key: 'decisions', label: 'Decisions' },
        { key: 'specs', label: 'Test Specs' },
        { key: 'tasks', label: 'Tasks' },
        { key: 'holistic', label: 'Consistency check' },
    ];
    const wrapper = document.createElement('div');
    wrapper.className = 'flex gap-3';
    wrapper.innerHTML = `
        <div class="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center text-white text-xs shrink-0 mt-0.5 select-none">🔎</div>
        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl w-full text-sm">
            <p class="font-medium text-gray-700 mb-2">Running full review…</p>
            <div class="review-steps space-y-1 mb-3">
                ${steps.map((step) => `
                    <div class="review-step flex items-center gap-2 text-xs text-gray-400" data-step="${step.key}">
                        <span class="step-icon w-4 text-center">○</span>
                        <span>${step.label}</span>
                    </div>`).join('')}
            </div>
            <div class="review-changes space-y-1 hidden"></div>
            <div class="review-summary mt-2 text-xs text-green-600 font-medium hidden"></div>
            <div class="review-error mt-2 text-xs text-red-500 hidden"></div>
        </div>`;
    return wrapper;
}

export function updateReviewStep(card, stepKey, status) {
    const el = card.querySelector(`[data-step="${stepKey}"]`);
    if (!el) {
        return;
    }
    const icon = el.querySelector('.step-icon');
    if (status === 'running') {
        el.classList.remove('text-gray-400');
        el.classList.add('text-blue-600');
        icon.textContent = '⟳';
    } else if (status === 'done') {
        el.classList.remove('text-blue-600', 'text-gray-400');
        el.classList.add('text-green-600');
        icon.textContent = '✓';
    }
    scrollToBottom();
}

export function addReviewChange(card, toolName, result) {
    const container = card.querySelector('.review-changes');
    if (!container) {
        return;
    }
    container.classList.remove('hidden');
    const icons = {
        delete_story: '🗑️',
        delete_component: '🗑️',
        delete_decision: '🗑️',
        delete_test_spec: '🗑️',
        delete_task: '🗑️',
        update_component: '✏️',
        update_decision: '✏️',
        update_test_spec: '✏️',
        update_task: '✏️',
        update_user_story: '✏️',
    };
    const div = document.createElement('div');
    div.className = 'review-change flex items-start gap-1.5 text-xs text-gray-500';
    const iconSpan = document.createElement('span');
    iconSpan.textContent = icons[toolName] || '•';
    const resultSpan = document.createElement('span');
    resultSpan.textContent = result;
    div.appendChild(iconSpan);
    div.appendChild(resultSpan);
    container.appendChild(div);
    const summary = card.querySelector('.review-summary');
    if (summary) {
        summary.classList.remove('hidden');
    }
    scrollToBottom();
}
