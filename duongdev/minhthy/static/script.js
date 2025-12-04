// ========== SOCKET CONNECTION ==========
const socket = io(window.location.origin, {
    path: '/duongdev/minhthy/socket.io'
});

// ========== DOM ELEMENTS ==========
const elements = {
    sidebar: document.getElementById('sidebar'),
    conversationList: document.getElementById('conversationList'),
    newChatBtn: document.getElementById('newChatBtn'),
    menuToggle: document.getElementById('menuToggle'),
    aiNickname: document.getElementById('aiNickname'),
    onlineDot: document.querySelector('.online-dot'),
    statusText: document.getElementById('statusText'),
    startName: document.getElementById('startName'),
    searchBtn: document.getElementById('searchBtn'),
    searchBar: document.getElementById('searchBar'),
    searchInput: document.getElementById('searchInput'),
    closeSearch: document.getElementById('closeSearch'),
    searchResults: document.getElementById('searchResults'),
    appContainer: document.getElementById('appContainer'),
    chatArea: document.getElementById('chatArea'),
    scrollBottomBtn: document.getElementById('scrollBottomBtn'),
    typingIndicator: document.getElementById('typingIndicator'),
    replyPreview: document.getElementById('replyPreview'),
    replySender: document.getElementById('replySender'),
    replyText: document.getElementById('replyText'),
    cancelReply: document.getElementById('cancelReply'),
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    emojiBtn: document.getElementById('emojiBtn'),
    emojiPicker: document.getElementById('emojiPicker'),
    moreBtn: document.getElementById('moreBtn'),
    settingsPanel: document.getElementById('settingsPanel'),
    closeSettingsBtn: document.getElementById('closeSettingsBtn'),
    saveSettings: document.getElementById('saveSettings'),
    exportBtn: document.getElementById('exportBtn'),
    exportModal: document.getElementById('exportModal'),
    closeExport: document.getElementById('closeExport'),
    exportTxt: document.getElementById('exportTxt'),
    exportJson: document.getElementById('exportJson'),
    convNameInput: document.getElementById('convNameInput'),
    aiNameInput: document.getElementById('aiNameInput'),
    userNameInput: document.getElementById('userNameInput'),
    userGirlfriendNameInput: document.getElementById('userGirlfriendNameInput'),
    moodSlider: document.getElementById('moodSlider'),
    moodValue: document.getElementById('moodValue'),
    messageCount: document.getElementById('messageCount'),
    deleteConvBtn: document.getElementById('deleteConvBtn'),
    themeToggle: document.getElementById('themeToggle'),
    soundToggle: document.getElementById('soundToggle'),
    reactionPicker: document.getElementById('reactionPicker'),
    notificationSound: document.getElementById('notificationSound'),
    themeOptions: document.querySelector('.theme-options'),
    themeButtons: document.querySelectorAll('.theme-btn')
};

// ========== STATE & CONFIG ==========
const AVATAR_URL = document.body.dataset.avatarUrl;

let state = {
    currentConversationId: null,
    conversations: [],
    messages: [],
    settings: {},
    replyToMessage: null,
    soundEnabled: true,
    isConnected: false,
    currentTheme: 'default',
    currentDefaultMode: 'dark'
};

// ========== SOCKET EVENTS ==========
socket.on('connect', () => {
    state.isConnected = true;
    console.log('✅ Connected');
});

socket.on('disconnect', () => {
    state.isConnected = false;
    elements.statusText.textContent = 'Mất kết nối...';
    elements.statusText.style.color = 'var(--danger)';
});

socket.on('init_data', data => {
    state.settings = data.settings;
    state.conversations = data.conversations;
    state.messages = data.messages;

    socket.emit('join', { room: data.current_conversation.id });

    if (data.current_conversation) {
        state.currentConversationId = data.current_conversation.id;
        updateHeader(data.current_conversation);
        updateSettingsModal(data.current_conversation);
    }

    elements.messageCount.textContent = data.message_count;

    state.currentTheme = state.settings.theme || 'default';
    state.currentDefaultMode = state.settings.default_mode || 'dark';

    applyTheme(state.currentTheme, state.currentDefaultMode);
    applySoundSetting(state.settings.sound_enabled !== 'false');

    renderConversations();
    renderMessages(state.messages);
    scrollToBottom(false);
});

socket.on('conversation_switched', data => {
    socket.emit('join', { room: data.conversation.id });

    state.currentConversationId = data.conversation.id;
    state.messages = data.messages;

    updateHeader(data.conversation);
    updateSettingsModal(data.conversation);
    elements.messageCount.textContent = data.message_count;

    renderMessages(state.messages);
    scrollToBottom(false);
    closeSidebar();
});

socket.on('conversation_created', data => {
    state.conversations = data.conversations;
    state.currentConversationId = data.conversation.id;
    state.messages = [];

    renderConversations();
    updateHeader(data.conversation);
    updateSettingsModal(data.conversation);
    renderMessages(state.messages);
    closeSidebar();
});

socket.on('conversation_deleted', data => {
    state.conversations = data.conversations;
    state.currentConversationId = data.switch_to.id;
    state.messages = data.messages;

    renderConversations();
    updateHeader(data.switch_to);
    updateSettingsModal(data.switch_to);
    renderMessages(state.messages);
    closeSidebar();
});

socket.on('conversation_updated', data => {
    state.conversations = data.conversations;
    updateHeader(data.conversation);
    renderConversations();
});

socket.on('conversations_updated', data => {
    state.conversations = data.conversations;
    renderConversations();
});

socket.on('message_sent', data => {
    const tempMessage = state.messages.find(m => m.id === data.temp_id);
    if (tempMessage) tempMessage.id = data.id;
    renderMessages(state.messages);
});

socket.on('typing_start', () => {
    elements.typingIndicator.classList.add('active');
    scrollToBottom();
});

socket.on('typing_stop', () => {
    elements.typingIndicator.classList.remove('active');
});

socket.on('new_message', data => {
    state.messages.push(data);
    renderMessages(state.messages);
    scrollToBottom();
    playNotificationSound();
    elements.messageCount.textContent = (parseInt(elements.messageCount.textContent) || 0) + 1;
});

socket.on('reaction_updated', data => {
    const message = state.messages.find(m => m.id === data.message_id);
    if (message) message.reactions = JSON.stringify(data.reactions);
    renderMessages(state.messages);
});

socket.on('search_results', data => {
    renderSearchResults(data.results, data.query);
});

socket.on('setting_updated', data => {
    state.settings[data.key] = data.value;

    if (data.key === 'theme') {
        state.currentTheme = data.value;
        applyTheme(state.currentTheme, state.currentDefaultMode);
    } else if (data.key === 'sound_enabled') {
        applySoundSetting(data.value === 'true');
    } else if (data.key === 'default_mode') {
        state.currentDefaultMode = data.value;
        if (state.currentTheme === 'default') applyTheme('default', state.currentDefaultMode);
    }
});

socket.on('ai_presence_updated', data => {
    if (data.status === 'online') {
        elements.statusText.textContent = 'Đang hoạt động';
        elements.statusText.style.color = 'var(--success)';
        if (elements.onlineDot) elements.onlineDot.style.display = 'block';
    } else {
        const minutes = data.minutes_ago || 0;
        if (minutes < 60) {
            elements.statusText.textContent = `Hoạt động ${minutes} phút trước`;
        } else {
            elements.statusText.textContent = `Hoạt động ${Math.floor(minutes / 60)} giờ trước`;
        }
        elements.statusText.style.color = 'var(--text-muted)';
        if (elements.onlineDot) elements.onlineDot.style.display = 'none';
    }
});

// ========== RENDER FUNCTIONS ==========
function renderConversations() {
    elements.conversationList.innerHTML = state.conversations
        .map(conv => `
            <div class="conversation-item ${conv.id === state.currentConversationId ? 'active' : ''}" data-id="${conv.id}">
                <div class="conv-avatar">
                    <img src="${AVATAR_URL}" class="avatar-image" alt="Avatar">
                </div>
                <div class="conv-info">
                    <div class="conv-name">${escapeHtml(conv.name)}</div>
                    <div class="conv-preview">${escapeHtml(conv.last_message || 'Chưa có tin nhắn')}</div>
                </div>
                ${conv.unread_count > 0 ? `<div class="unread-badge">${conv.unread_count}</div>` : ''}
            </div>
        `)
        .join('');

    document.querySelectorAll('.conversation-item').forEach(item => {
        item.addEventListener('click', () => {
            const newConvId = parseInt(item.dataset.id);
            if (newConvId !== state.currentConversationId) {
                elements.appContainer.classList.remove('settings-open');
                socket.emit('switch_conversation', { conversation_id: newConvId });
            }
        });
    });
}

function renderMessages(messages) {
    if (!messages || messages.length === 0) {
        elements.chatArea.innerHTML = `
            <div class="chat-start-message">
                <div class="start-avatar">
                    <img src="${AVATAR_URL}" class="avatar-image" alt="Avatar">
                </div>
                <p>Bắt đầu cuộc trò chuyện với <strong id="startName">${elements.aiNickname.textContent}</strong></p>
                <span class="start-hint">Lịch sử chat được lưu tự động</span>
            </div>
        `;
        return;
    }

    const groupedMessages = messages.map((msg, index, arr) => {
        const prevMsg = arr[index - 1];
        const nextMsg = arr[index + 1];

        const currentTimestamp = msg.timestamp
            ? new Date(
                  msg.timestamp.includes(' ') && !msg.timestamp.includes('T')
                      ? msg.timestamp.replace(' ', 'T') + '+07:00'
                      : msg.timestamp
              ).getTime()
            : Date.now();

        const isSameSenderAsPrev = prevMsg && prevMsg.sender_name === msg.sender_name;
        const isSameSenderAsNext = nextMsg && nextMsg.sender_name === msg.sender_name;

        const timeDiffPrev = prevMsg?.timestamp
            ? (currentTimestamp -
                  new Date(
                      prevMsg.timestamp.includes(' ') && !prevMsg.timestamp.includes('T')
                          ? prevMsg.timestamp.replace(' ', 'T') + '+07:00'
                          : prevMsg.timestamp
                  ).getTime()) /
              (1000 * 60)
            : Infinity;

        const timeDiffNext = nextMsg?.timestamp
            ? (new Date(
                  nextMsg.timestamp.includes(' ') && !nextMsg.timestamp.includes('T')
                      ? nextMsg.timestamp.replace(' ', 'T') + '+07:00'
                      : nextMsg.timestamp
              ).getTime() -
                  currentTimestamp) /
              (1000 * 60)
            : Infinity;

        const closePrev = timeDiffPrev < 5;
        const closeNext = timeDiffNext < 5;

        let groupType;

        if (arr.length === 1) groupType = 'group-single';
        else if (!isSameSenderAsPrev || !closePrev) groupType = closeNext && isSameSenderAsNext ? 'group-start' : 'group-single';
        else if (isSameSenderAsPrev && closePrev) groupType = closeNext && isSameSenderAsNext ? 'group-middle' : 'group-end';
        else groupType = 'group-single';

        return { ...msg, groupType };
    });

    elements.chatArea.innerHTML = groupedMessages.map(createMessageHTML).join('');
    attachMessageHandlers();
}

function createMessageHTML(msg) {
    const type = msg.role === 'user' ? 'sent' : 'received';
    const reactions = parseReactions(msg.reactions);
    const time = formatTime(msg.timestamp);
    const group = msg.groupType;

    let replyHTML = '';
    if (msg.reply_content) {
        replyHTML = `
            <div class="msg-reply">
                <div class="msg-reply-sender">${escapeHtml(msg.reply_sender)}</div>
                <div class="msg-reply-text">${escapeHtml(msg.reply_content)}</div>
            </div>
        `;
    }

    let avatarHTML = '';
    if (type === 'received') {
        avatarHTML =
            group === 'group-end' || group === 'group-single'
                ? `<div class="msg-avatar"><img src="${AVATAR_URL}" class="avatar-image" alt="Avatar"></div>`
                : `<div class="msg-avatar msg-avatar-placeholder"></div>`;
    }

    const reactionsHTML =
        group === 'group-end' || group === 'group-single'
            ? reactions.length > 0
                ? `<div class="message-reactions">${reactions
                      .map(r => `<span class="reaction-badge">${r}</span>`)
                      .join('')}</div>`
                : ''
            : '';

    const seenHTML =
        type === 'sent' && msg.is_seen
            ? `<img src="${AVATAR_URL}" class="message-seen-avatar" alt="Seen">`
            : '';

    const metaHTML =
        group === 'group-end' || group === 'group-single'
            ? `
                <div class="message-meta">
                    <span class="message-time">${time}</span>
                    ${seenHTML}
                </div>
            `
            : '';

    return `
        <div class="message ${type} ${group}" data-id="${msg.id}">
            <div class="message-wrapper">
                ${avatarHTML}
                <div class="message-content">
                    ${replyHTML}
                    <div class="message-bubble">
                        <p class="message-text">${escapeHtml(msg.content)}</p>
                    </div>
                    ${reactionsHTML}
                    ${metaHTML}
                </div>
            </div>
        </div>
    `;
}

// ========== MESSAGE SENDING ==========
function sendMessage() {
    const content = elements.messageInput.value.trim();
    if (!content || !state.isConnected || !state.currentConversationId) return;

    const tempId = `temp_${Date.now()}`;
    const now = new Date().toISOString();

    const tempMessage = {
        id: tempId,
        role: 'user',
        sender_name: state.settings.userName || 'Bạn',
        content,
        timestamp: now,
        reply_to_id: state.replyToMessage?.id,
        reply_content: state.replyToMessage?.content,
        reply_sender: state.replyToMessage?.sender,
        reactions: '[]',
        is_seen: 0
    };

    state.messages.push(tempMessage);
    renderMessages(state.messages);
    scrollToBottom();

    socket.emit('send_message', {
        conversation_id: state.currentConversationId,
        message: content,
        reply_to_id: state.replyToMessage?.id,
        temp_id: tempId
    });

    clearReply();
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
    elements.messageInput.focus();
}

// ========== MESSAGE HANDLERS ==========
function attachMessageHandlers() {
    document.querySelectorAll('.message-bubble').forEach(bubble => {
        bubble.addEventListener('dblclick', e => {
            showReactionPicker(bubble.closest('.message'), e);
        });

        let pressTimer;

        bubble.addEventListener(
            'touchstart',
            () => {
                pressTimer = setTimeout(() => startReply(bubble.closest('.message')), 500);
            },
            { passive: true }
        );

        bubble.addEventListener('touchend', () => clearTimeout(pressTimer));

        bubble.addEventListener('contextmenu', e => {
            e.preventDefault();
            startReply(bubble.closest('.message'));
        });
    });
}

// ========== SEARCH ==========
function renderSearchResults(results, query) {
    if (results.length === 0) {
        elements.searchResults.innerHTML = `<div class="no-results">Không tìm thấy kết quả cho "${escapeHtml(query)}"</div>`;
    } else {
        elements.searchResults.innerHTML = results
            .map(msg => {
                const highlighted = msg.content.replace(
                    new RegExp(`(${escapeRegex(query)})`, 'gi'),
                    '<mark>$1</mark>'
                );
                return `
                    <div class="search-result-item" data-id="${msg.id}">
                        <div class="result-sender">${escapeHtml(msg.sender_name)}</div>
                        <div class="result-content">${highlighted}</div>
                    </div>
                `;
            })
            .join('');

        document.querySelectorAll('.search-result-item').forEach(item => {
            item.addEventListener('click', () => {
                navigateToMessage(parseInt(item.dataset.id));
                elements.searchResults.classList.remove('active');
                elements.searchBar.classList.remove('active');
                elements.searchInput.value = '';
            });
        });
    }

    elements.searchResults.classList.add('active');
}

function navigateToMessage(messageId) {
    const el = document.querySelector(`.message[data-id="${messageId}"]`);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('highlighted');
        setTimeout(() => el.classList.remove('highlighted'), 3000);
    }
}

// ========== UI HELPERS ==========
function updateHeader(conv) {
    elements.aiNickname.textContent = conv.ai_name;
    const startName = document.getElementById('startName');
    if (startName) startName.textContent = conv.ai_name;

    if (elements.appContainer) {
        if (state.currentConversationId === conv.id) {
            elements.appContainer.classList.add('active-chat');
        } else {
            elements.appContainer.classList.remove('active-chat');
        }
    }
}

function updateSettingsModal(conv) {
    elements.convNameInput.value = conv.name;
    elements.aiNameInput.value = conv.ai_name;
    elements.userNameInput.value = conv.user_name;
    elements.userGirlfriendNameInput.value = conv.user_girlfriend_name || '';
    elements.moodSlider.value = conv.mood;
    elements.moodValue.textContent = conv.mood;
}

function startReply(msgEl) {
    const id = parseInt(msgEl.dataset.id);
    const content = msgEl.querySelector('.message-text').textContent;

    state.replyToMessage = {
        id,
        content,
        sender: msgEl.classList.contains('sent') ? 'Bạn' : elements.aiNickname.textContent
    };

    elements.replySender.textContent = state.replyToMessage.sender;
    elements.replyText.textContent = content.length > 50 ? content.slice(0, 50) + '...' : content;
    elements.replyPreview.classList.add('active');
    elements.messageInput.focus();
}

function clearReply() {
    state.replyToMessage = null;
    elements.replyPreview.classList.remove('active');
}

function showReactionPicker(msgEl) {
    const picker = elements.reactionPicker;
    const rect = msgEl.getBoundingClientRect();
    picker.style.left = `${rect.left}px`;
    picker.style.top = `${rect.top - 50}px`;
    picker.classList.add('active');
    picker.dataset.messageId = msgEl.dataset.id;

    setTimeout(() => {
        document.addEventListener('click', closeReactionPicker, { once: true });
    }, 10);
}

function closeReactionPicker() {
    elements.reactionPicker.classList.remove('active');
}

function updateMessageReactions(msgId, reactions) {
    const msg = state.messages.find(m => m.id === msgId);
    if (msg) msg.reactions = JSON.stringify(reactions);
    renderMessages(state.messages);
}

function applyTheme(theme) {
    document.body.className = `${theme}-theme`;
}

function applySoundSetting(enabled) {
    state.soundEnabled = enabled;
    document.body.dataset.sound = enabled.toString();
}

function playNotificationSound() {
    if (state.soundEnabled && elements.notificationSound) {
        elements.notificationSound.currentTime = 0;
        elements.notificationSound.play().catch(() => {});
    }
}

function formatTime(timestamp) {
    if (!timestamp) return '';

    try {
        let date = new Date(
            timestamp.includes(' ') && !timestamp.includes('T')
                ? timestamp.replace(' ', 'T') + '+07:00'
                : timestamp
        );

        if (isNaN(date.getTime())) return timestamp;

        const diffMins = Math.floor((Date.now() - date.getTime()) / 60000);

        if (diffMins < 1) return 'Vừa xong';
        if (diffMins < 60) return `${diffMins} phút trước`;
        if (diffMins < 1440) return `${Math.floor(diffMins / 60)} giờ trước`;

        return date.toLocaleString('vi-VN', { day: '2-digit', month: '2-digit' });
    } catch {
        return timestamp;
    }
}

function parseReactions(reactions) {
    try {
        return JSON.parse(reactions || '[]');
    } catch {
        return [];
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function scrollToBottom(smooth = true) {
    setTimeout(() => {
        elements.chatArea.scrollTo({
            top: elements.chatArea.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
    }, 50);
}

function closeSidebar() {
    elements.sidebar.classList.remove('open');
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// ========== EVENT LISTENERS ==========
elements.sendBtn.addEventListener('click', sendMessage);

elements.messageInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

elements.messageInput.addEventListener('input', () => autoResize(elements.messageInput));
elements.cancelReply.addEventListener('click', clearReply);

elements.emojiBtn.addEventListener('click', e => {
    e.stopPropagation();
    elements.emojiPicker.classList.toggle('active');
});

document.addEventListener('click', e => {
    if (!elements.emojiPicker.contains(e.target) && e.target !== elements.emojiBtn) {
        elements.emojiPicker.classList.remove('active');
    }
});

document.querySelectorAll('.emoji-grid span').forEach(emoji => {
    emoji.addEventListener('click', () => {
        elements.messageInput.value += emoji.textContent;
        elements.emojiPicker.classList.remove('active');
        elements.messageInput.focus();
    });
});

document.querySelectorAll('.reaction-picker span').forEach(emoji => {
    emoji.addEventListener('click', e => {
        e.stopPropagation();
        socket.emit('add_reaction', {
            message_id: parseInt(elements.reactionPicker.dataset.messageId),
            emoji: emoji.dataset.emoji
        });
        closeReactionPicker();
    });
});

elements.chatArea.addEventListener('scroll', () => {
    const show =
        elements.chatArea.scrollHeight - elements.chatArea.scrollTop - elements.chatArea.clientHeight > 200;
    elements.scrollBottomBtn.classList.toggle('visible', show);
});

elements.scrollBottomBtn.addEventListener('click', () => scrollToBottom());

elements.searchBtn.addEventListener('click', () => {
    elements.searchBar.classList.toggle('active');
    if (elements.searchBar.classList.contains('active')) {
        elements.searchInput.focus();
    } else {
        elements.searchResults.classList.remove('active');
    }
});

elements.closeSearch.addEventListener('click', () => {
    elements.searchBar.classList.remove('active');
    elements.searchResults.classList.remove('active');
    elements.searchInput.value = '';
});

let searchTimeout;

elements.searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);

    const query = elements.searchInput.value.trim();

    if (query.length < 2) {
        elements.searchResults.classList.remove('active');
        return;
    }

    searchTimeout = setTimeout(() => {
        socket.emit('search_messages', {
            conversation_id: state.currentConversationId,
            query
        });
    }, 300);
});

elements.menuToggle.addEventListener('click', () => {
    elements.sidebar.classList.toggle('open');
});

elements.newChatBtn.addEventListener('click', () => {
    socket.emit('create_conversation', { name: 'Minh Thy 🌸' });
    closeSidebar();
});

elements.moreBtn.addEventListener('click', () =>
    elements.appContainer.classList.toggle('settings-open')
);

elements.closeSettingsBtn.addEventListener('click', () =>
    elements.appContainer.classList.remove('settings-open')
);

elements.themeToggle.addEventListener('click', () => {
    const newTheme = document.body.classList.contains('dark-theme') ? 'light' : 'dark';
    applyTheme(newTheme);
    socket.emit('update_setting', { key: 'theme', value: newTheme });
});

elements.soundToggle.addEventListener('click', () => {
    const newSound = !state.soundEnabled;
    applySoundSetting(newSound);
    socket.emit('update_setting', {
        key: 'sound_enabled',
        value: newSound.toString()
    });
});

elements.exportBtn.addEventListener('click', () => {
    elements.exportModal.classList.add('active');
});

elements.closeExport.addEventListener('click', () => {
    elements.exportModal.classList.remove('active');
});

elements.exportTxt.addEventListener('click', () => {
    window.location.href = `/duongdev/minhthy/export/${state.currentConversationId}/txt`;
    elements.exportModal.classList.remove('active');
});

elements.exportJson.addEventListener('click', () => {
    window.location.href = `/duongdev/minhthy/export/${state.currentConversationId}/json`;
    elements.exportModal.classList.remove('active');
});

elements.moodSlider.addEventListener('input', () => {
    elements.moodValue.textContent = elements.moodSlider.value;
});

elements.saveSettings.addEventListener('click', () => {
    socket.emit('update_conversation', {
        conversation_id: state.currentConversationId,
        name: elements.convNameInput.value.trim(),
        ai_name: elements.aiNameInput.value.trim(),
        user_name: elements.userNameInput.value.trim(),
        user_girlfriend_name: elements.userGirlfriendNameInput.value.trim(),
        mood: parseInt(elements.moodSlider.value)
    });

    elements.appContainer.classList.remove('settings-open');
});

elements.deleteConvBtn.addEventListener('click', () => {
    if (confirm('Xoá cuộc trò chuyện này? Không thể hoàn tác!')) {
        socket.emit('delete_conversation', { conversation_id: state.currentConversationId });
        elements.appContainer.classList.remove('settings-open');
    }
});

// close modal on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
        if (e.target === overlay) overlay.classList.remove('active');
    });
});

// auto close sidebar on mobile
document.addEventListener('click', e => {
    if (
        window.innerWidth <= 900 &&
        elements.sidebar.classList.contains('open') &&
        !elements.sidebar.contains(e.target) &&
        e.target !== elements.menuToggle
    ) {
        closeSidebar();
    }
});

// ========== INIT ==========
elements.messageInput.focus();
console.log('🌸 Minh Thy Chat v2.0 initialized');
