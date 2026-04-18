export function getActiveTabPane() {
    const panes = document.querySelectorAll('[id^="tab-pane-"]');
    for (const pane of panes) {
        if (pane.style.display !== 'none') {
            return pane;
        }
    }
    return document.getElementById('messages');
}

export function createMessageWrapper(role) {
    const isUser = role === 'user';
    const div = document.createElement('div');
    div.className = 'flex gap-3' + (isUser ? ' justify-end' : '');
    div.innerHTML = isUser
        ? '<div class="bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-xl text-sm leading-relaxed message-content"></div>'
        : '<div class="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs shrink-0 mt-0.5 select-none">AI</div><div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl text-sm leading-relaxed message-content"></div>';
    return div;
}

export function appendMessageToTab(role, content, tabKey) {
    const pane = document.getElementById(`tab-pane-${tabKey}`);
    if (!pane) {
        return;
    }
    const wrapper = createMessageWrapper(role);
    wrapper.querySelector('.message-content').textContent = content;
    pane.appendChild(wrapper);
    scrollToBottom();
}

export function scrollToBottom() {
    const msgs = document.getElementById('messages');
    if (msgs) {
        msgs.scrollTop = msgs.scrollHeight;
    }
}
