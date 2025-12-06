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
    soundToggle: document.getElementById('soundToggle'),
    reactionPicker: document.getElementById('reactionPicker'),
    notificationSound: document.getElementById('notificationSound'),
    themeOptions: document.getElementById('themeOptions'),
};

// Dynamically create and inject search filters
const searchFiltersContainer = document.createElement('div');
searchFiltersContainer.className = 'search-filters';
searchFiltersContainer.style.display = 'none'; // Initially hidden
searchFiltersContainer.innerHTML = `
    <label for="startDate">Từ:</label>
    <input type="date" id="startDate">
    <label for="endDate">Đến:</label>
    <input type="date" id="endDate">
`;
elements.searchBar.parentNode.insertBefore(searchFiltersContainer, elements.searchBar.nextSibling);

// Add newly created elements to the elements object
elements.searchFilters = searchFiltersContainer;
elements.startDateInput = document.getElementById('startDate');
elements.endDateInput = document.getElementById('endDate');

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
    
    // Set initial theme and sound state from loaded settings
    state.currentTheme = state.settings.theme || 'default';
    applySoundSetting(state.settings.sound_enabled !== 'false', false); // Don't save on init
    
    // Fetch themes and then apply the loaded theme
    fetchThemes().then(() => {
        applyTheme(state.currentTheme);
    });

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

    // Show Notification if app is in background
    if (document.hidden && Notification.permission === "granted" && data.role === 'assistant') {
        const notification = new Notification(data.sender_name, {
            body: data.content,
            icon: AVATAR_URL
        });
        notification.onclick = () => {
            window.focus();
            notification.close();
        };
    }
});

socket.on('reaction_updated', data => {
    const message = state.messages.find(m => m.id === data.message_id);
    if (message) message.reactions = JSON.stringify(data.reactions);
    renderMessages(state.messages);
});

socket.on('messages_seen', () => {
    let changed = false;
    // Mark all user messages as seen (since AI reads everything up to now)
    state.messages.forEach(m => {
        if (m.role === 'user' && !m.is_seen) {
            m.is_seen = 1;
            changed = true;
        }
    });
    if (changed) renderMessages(state.messages);
});

socket.on('message_updated', data => {
    const updatedMsg = data.message;
    if (!updatedMsg) return;

    const msgIndex = state.messages.findIndex(m => m.id === updatedMsg.id);
    if (msgIndex > -1) {
        // Create a new object to ensure reactivity if using a framework
        state.messages[msgIndex] = { ...state.messages[msgIndex], ...updatedMsg };
        renderMessages(state.messages);
    }
});

socket.on('search_results', data => {
    renderSearchResults(data.results, data.query);
});

socket.on('setting_updated', data => {
    state.settings[data.key] = data.value;
    if (data.key === 'theme') {
        applyTheme(data.value);
    } else if (data.key === 'sound_enabled') {
        applySoundSetting(data.value === 'true', false); // Don't re-save
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
    const time = formatTime(msg.timestamp);
    const group = msg.groupType;

    if (msg.is_retracted) {
        return `
            <div class="message ${type} ${group}" data-id="${msg.id}">
                <div class="message-wrapper">
                    <div class="msg-avatar-placeholder"></div>
                    <div class="message-content">
                        <div class="message-bubble retracted">
                            <p class="message-text">${escapeHtml(msg.content)}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    const reactions = parseReactions(msg.reactions);

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
                    ${msg.is_edited ? '<span class="edited-label">(đã chỉnh sửa)</span>' : ''}
                    ${seenHTML}
                </div>
            `
            : '';
    
    const actionsHTML = 
        type === 'sent' 
        ? `
            <div class="message-actions">
                <button class="btn-icon action-btn-more">
                    <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2_0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z" /></svg>
                </button>
                <div class="actions-menu">
                    <button class="menu-item edit-btn">Chỉnh sửa</button>
                    <button class="menu-item retract-btn danger">Thu hồi</button>
                </div>
            </div>
        ` 
        : '';

    return `
        <div class="message ${type} ${group}" data-id="${msg.id}">
            <div class="message-wrapper">
                ${avatarHTML}
                ${actionsHTML}
                <div class="message-content">
                    ${replyHTML}
                    <div class="message-bubble">
                        <p class="message-text">${escapeHtml(msg.content)}</p>
                    </div>
                    <div class="message-edit-form">
                        <textarea>${escapeHtml(msg.content)}</textarea>
                        <div class="edit-actions">
                            <button class="edit-btn-cancel">Hủy</button>
                            <button class="edit-btn-save">Lưu</button>
                        </div>
                    </div>
                    ${reactionsHTML}
                    ${metaHTML}
                </div>
            </div>
        </div>
    `;
}

// ========== MESSAGE HANDLERS ==========
function attachMessageHandlers() {
    document.querySelectorAll('.message-bubble').forEach(bubble => {
        // Xử lý thả cảm xúc (Double click)
        bubble.addEventListener('dblclick', e => {
            showReactionPicker(bubble.closest('.message'), e);
        });

        let pressTimer;

        // Xử lý trả lời tin nhắn trên Mobile (Nhấn giữ)
        bubble.addEventListener(
            'touchstart',
            () => {
                pressTimer = setTimeout(() => startReply(bubble.closest('.message')), 500);
            },
            { passive: true }
        );

        bubble.addEventListener('touchend', () => clearTimeout(pressTimer));

        // Xử lý trả lời tin nhắn trên Desktop (Chuột phải)
        bubble.addEventListener('contextmenu', e => {
            e.preventDefault();
            startReply(bubble.closest('.message'));
        });
    });

    // Handle actions menu toggle
    document.querySelectorAll('.action-btn-more').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const menu = button.nextElementSibling;
            // Close all other menus before opening a new one
            document.querySelectorAll('.actions-menu.visible').forEach(m => {
                if (m !== menu) m.classList.remove('visible');
            });
            menu.classList.toggle('visible');
        });
    });

    // Handle retract button click
    document.querySelectorAll('.retract-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const messageEl = button.closest('.message');
            const msgId = parseInt(messageEl.dataset.id);

            if (confirm('Bạn có chắc muốn thu hồi tin nhắn này không?')) {
                socket.emit('retract_message', { message_id: msgId });
            }
        });
    });

    // Global listener to close menus
    document.addEventListener('click', (e) => {
        const openMenus = document.querySelectorAll('.actions-menu.visible');
        if (openMenus.length > 0 && !e.target.closest('.message-actions')) {
            openMenus.forEach(menu => menu.classList.remove('visible'));
        }
    }, true); // Use capture phase to catch click first

    // Handle Edit button click
    document.querySelectorAll('.edit-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const messageEl = button.closest('.message');
            messageEl.classList.add('editing');

            const bubble = messageEl.querySelector('.message-bubble');
            const editForm = messageEl.querySelector('.message-edit-form');
            
            bubble.style.display = 'none';
            editForm.style.display = 'flex';
            
            // Hide the menu
            button.closest('.actions-menu').classList.remove('visible');
        });
    });

    // Handle Edit Cancel
    document.querySelectorAll('.edit-btn-cancel').forEach(button => {
        button.addEventListener('click', (e) => {
            const messageEl = button.closest('.message');
            messageEl.classList.remove('editing');

            const bubble = messageEl.querySelector('.message-bubble');
            const editForm = messageEl.querySelector('.message-edit-form');

            editForm.style.display = 'none';
            bubble.style.display = 'block';
        });
    });

    // Handle Edit Save
    document.querySelectorAll('.edit-btn-save').forEach(button => {
        button.addEventListener('click', (e) => {
            const messageEl = button.closest('.message');
            const msgId = parseInt(messageEl.dataset.id);
            const newContent = messageEl.querySelector('textarea').value.trim();

            if (newContent) {
                socket.emit('edit_message', {
                    message_id: msgId,
                    new_content: newContent
                });
            }

            // The UI will update automatically via the 'message_updated' event
            // so we just need to exit the edit mode visually
            messageEl.classList.remove('editing');
            const bubble = messageEl.querySelector('.message-bubble');
            const editForm = messageEl.querySelector('.message-edit-form');
            editForm.style.display = 'none';
            bubble.style.display = 'block';
        });
    });
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

// Image handling functions
function clearImageSelection() {
    state.selectedImage = null;
    elements.imageInput.value = ''; // Reset input
    elements.previewImg.src = '';
    elements.imagePreview.classList.remove('active');
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

// Refactored Theme and Sound functions
function applySoundSetting(enabled, save = true) {
    state.soundEnabled = enabled;
    document.body.dataset.sound = enabled.toString();
    if (save) {
        socket.emit('update_setting', { key: 'sound_enabled', value: enabled.toString() });
    }
}

function playNotificationSound() {
    if (state.soundEnabled && elements.notificationSound) {
        elements.notificationSound.currentTime = 0;
        elements.notificationSound.play().catch(() => {});
    }
}

function applyTheme(themeName) {
    if (!themeName) return;

    const existingLink = document.getElementById('dynamic-theme-style');
    if (existingLink) {
        existingLink.remove();
    }

    document.body.className = ''; // Clear all classes
    document.body.classList.add(`${themeName}-theme`);

    if (themeName !== 'default' && themeName !== 'light') {
        const link = document.createElement('link');
        link.id = 'dynamic-theme-style';
        link.rel = 'stylesheet';
        link.href = `/duongdev/minhthy/static/themes/${themeName}.css`;
        document.head.appendChild(link);
    }
    
    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === themeName);
    });

    state.currentTheme = themeName;
    console.log(`🎨 Theme applied: ${themeName}`);
}

function renderThemeButtons(themes) {
    const container = document.getElementById('themeOptions');
    if (!container) return;

    container.innerHTML = themes.map(theme => `
        <button 
            class="theme-btn" 
            data-theme="${escapeHtml(theme.name)}" 
            style="background: ${escapeHtml(theme.preview_color)}; border: 1px solid var(--border-color);"
            title="${escapeHtml(theme.name)}">
        </button>
    `).join('');

    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const themeName = btn.dataset.theme;
            applyTheme(themeName);
            socket.emit('update_setting', { key: 'theme', value: themeName });
        });
    });
}

async function fetchThemes() {
    try {
        const response = await fetch('/duongdev/minhthy/themes');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const themes = await response.json();
        renderThemeButtons(themes);
    } catch (error) {
        console.error("Could not fetch themes:", error);
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
    }, 200); // Increased delay for better rendering
}

function closeSidebar() {
    elements.sidebar.classList.remove('open');
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// ========== EVENT LISTENERS ========== 
document.addEventListener('DOMContentLoaded', () => {
    // Socket connection will trigger init_data, which then triggers theme loading
    if ("Notification" in window && Notification.permission !== "granted") {
        Notification.requestPermission();
    }
});

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
    const isActive = elements.searchBar.classList.toggle('active');
    if (isActive) {
        elements.searchInput.focus();
        elements.searchFilters.style.display = 'flex';
    } else {
        elements.searchResults.classList.remove('active');
        elements.searchFilters.style.display = 'none';
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
    const startDate = elements.startDateInput.value;
    const endDate = elements.endDateInput.value;

    if (query.length < 2) {
        elements.searchResults.classList.remove('active');
        return;
    }

    searchTimeout = setTimeout(() => {
        socket.emit('search_messages', {
            conversation_id: state.currentConversationId,
            query: query,
            start_date: startDate,
            end_date: endDate
        });
    }, 300);
});

elements.menuToggle.addEventListener('click', () => {
    if (window.innerWidth > 900) {
        elements.sidebar.classList.toggle('collapsed');
    } else {
        elements.sidebar.classList.toggle('open');
    }
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

elements.soundToggle.addEventListener('click', () => {
    applySoundSetting(!state.soundEnabled);
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