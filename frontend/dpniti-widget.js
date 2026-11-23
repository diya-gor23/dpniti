(function () {
    // Use CONFIG.API_URL from config.js, or fallback to Python service
    const PYTHON_API_URL = typeof CONFIG !== 'undefined' ? CONFIG.PYTHON_API_URL : 'http://localhost:5001';
    const SESSION_ID = 'dpniti_' + Math.random().toString(36).slice(2);
    const CHAT_STORAGE_KEY = 'dpniti_chat_messages';
    let conversationVersion = 0;
    let mediaRecorder, audioChunks = [], isRecording = false;
    let activeRequest = null;
    let pendingCancellation = null;

    function formatISTTime(timestamp) {
        return new Intl.DateTimeFormat('en-IN', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
            timeZone: 'Asia/Kolkata'
        }).format(new Date(timestamp));
    }

    function createMessage(text, who, timestamp) {
        const msg = document.createElement('div');
        msg.className = 'dpniti-msg ' + who;
        msg.dataset.messageText = text;
        msg.dataset.timestamp = timestamp || new Date().toISOString();

        const content = document.createElement('span');
        content.className = 'dpniti-msg-content';
        content.textContent = text;
        msg.appendChild(content);

        if (!who.includes('typing')) {
            const time = document.createElement('span');
            time.className = 'dpniti-msg-time';
            time.textContent = formatISTTime(msg.dataset.timestamp);
            msg.appendChild(time);
        }

        if (who === 'bot') addResponseActions(msg, text);
        if (who === 'user') addUserCopyAction(msg, text);
        return msg;
    }

    function addUserCopyAction(msgEl, text) {
        const actions = document.createElement('div');
        actions.className = 'dpniti-user-actions';

        const copyBtn = document.createElement('button');
        copyBtn.className = 'dpniti-action-btn';
        copyBtn.textContent = '⧉';
        copyBtn.setAttribute('aria-label', 'Copy question');
        copyBtn.title = 'Copy';
        copyBtn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(text);
                copyBtn.textContent = '✓';
                copyBtn.classList.add('selected');
                setTimeout(() => {
                    copyBtn.textContent = '⧉';
                    copyBtn.classList.remove('selected');
                }, 1200);
            } catch (error) {
                copyBtn.title = 'Copy failed';
            }
        });

        actions.appendChild(copyBtn);
        msgEl.appendChild(actions);
    }

    async function botReply(userText, body, onGeneratingChange = function () {}, userMessage = null) {
    const replyVersion = conversationVersion;
    const controller = new AbortController();
    const requestId = crypto.randomUUID();
    activeRequest = { controller, body, userMessage, requestId, onGeneratingChange };
    onGeneratingChange(true);
    const typing = createMessage('DPniti is thinking...', 'bot typing');
    body.appendChild(typing);
    body.scrollTop = body.scrollHeight;
    try {
        const res  = await fetch(PYTHON_API_URL + '/chat', {
            method: 'POST',
            credentials: 'include', // sends the httpOnly auth cookie; no token in JS anymore
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                message: userText, 
                session_id: SESSION_ID,
                request_id: requestId,
                user_name: localStorage.getItem('userName') || null,
                role: localStorage.getItem('role') || null,
                batch: localStorage.getItem('batch') || null,
                allowed_sem: localStorage.getItem('allowedSem') ? Number(localStorage.getItem('allowedSem')) : null
            })
        });
        const data = await res.json();
        if (replyVersion !== conversationVersion || controller.signal.aborted) {
            typing.remove();
            return;
        }
                typing.remove();
        const botMsg = createMessage(data.reply, 'bot');
        botMsg.dataset.traceId = data.trace_id || '';
        body.appendChild(botMsg);
        saveConversation(body);
    } catch (e) {
        typing.remove();
        if (replyVersion !== conversationVersion || controller.signal.aborted) return;
        body.appendChild(createMessage('Could not reach AI server. Make sure chatbot_api.py is running on port 5001.', 'bot'));
        saveConversation(body);
    } finally {
        if (activeRequest && activeRequest.controller === controller) {
            activeRequest = null;
            onGeneratingChange(false);
        }
    }
    body.scrollTop = body.scrollHeight;
}

        let currentUtterance = null;
    let currentSpeakBtn = null;

    function addResponseActions(msgEl, text) {
        const actions = document.createElement('div');
        actions.className = 'dpniti-response-actions';

        const copyBtn = document.createElement('button');
        copyBtn.className = 'dpniti-action-btn';
        copyBtn.textContent = '⧉';
        copyBtn.setAttribute('aria-label', 'Copy answer');
        copyBtn.title = 'Copy';
        copyBtn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(text);
                copyBtn.textContent = '✓';
                copyBtn.classList.add('selected');
                setTimeout(() => {
                    copyBtn.textContent = '⧉';
                    copyBtn.classList.remove('selected');
                }, 1200);
            } catch (error) {
                copyBtn.title = 'Copy failed';
            }
        });

        const ratingWrap = document.createElement('div');
        ratingWrap.className = 'dpniti-rating-wrap';

        const ratingBtn = document.createElement('button');
        ratingBtn.className = 'dpniti-action-btn';
        ratingBtn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2h3zm2 10h8.6a2 2 0 0 0 1.9-1.4l2.1-6.3A2 2 0 0 0 19.7 10H15l.7-4.2A3.2 3.2 0 0 0 12.6 2L9 10v10z"/></svg>';
        ratingBtn.setAttribute('aria-label', 'Rate answer');
        ratingBtn.title = 'Rate answer';

        const ratingMenu = document.createElement('div');
        ratingMenu.className = 'dpniti-rating-menu';

        function addRatingOption(icon, label, selectedClass) {
            const option = document.createElement('button');
            option.className = 'dpniti-rating-option';
            option.innerHTML = `<span aria-hidden="true">${icon}</span><span>${label}</span>`;
            option.addEventListener('click', () => {
                ratingBtn.classList.add('selected');
                ratingBtn.innerHTML = icon;
                ratingBtn.setAttribute('aria-label', label);
                ratingBtn.title = label;
                ratingMenu.classList.remove('open');
                option.classList.add(selectedClass);
                if (msgEl.dataset.traceId) {
                    fetch(PYTHON_API_URL + '/feedback', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            trace_id: msgEl.dataset.traceId,
                            rating: selectedClass === 'good' ? 'good' : 'bad'
                        })
                    }).catch(() => {});
                }
            });
            ratingMenu.appendChild(option);
        }

        addRatingOption('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2h3zm2 10h8.6a2 2 0 0 0 1.9-1.4l2.1-6.3A2 2 0 0 0 19.7 10H15l.7-4.2A3.2 3.2 0 0 0 12.6 2L9 10v10z"/></svg>', 'Good response', 'good');
        addRatingOption('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14V4H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3zm2-10h8.6a2 2 0 0 1 1.9 1.4l2.1 6.3A2 2 0 0 1 19.7 14H15l.7 4.2a3.2 3.2 0 0 1-3.1 3.8L9 14V4z"/></svg>', 'Bad response', 'bad');
        ratingBtn.addEventListener('click', event => {
            event.stopPropagation();
            ratingMenu.classList.toggle('open');
        });
        ratingWrap.append(ratingBtn, ratingMenu);

        const speakBtn = document.createElement('button');
        speakBtn.className = 'dpniti-action-btn dpniti-speak-btn';
        speakBtn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 0 0-2.1-3.8v7.6a4.5 4.5 0 0 0 2.1-3.8zm0-8.5v2.1a8 8 0 0 1 0 12.8v2.1a10 10 0 0 0 0-17z"/></svg>';
        speakBtn.setAttribute('aria-label', 'Play answer as speech');
        speakBtn.title = 'Speaker';
        speakBtn.addEventListener('click', () => toggleSpeech(speakBtn, text));

        actions.append(copyBtn, ratingWrap, speakBtn);
        msgEl.appendChild(actions);
    }

    function resetSpeakBtn(btn) {
        btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 0 0-2.1-3.8v7.6a4.5 4.5 0 0 0 2.1-3.8zm0-8.5v2.1a8 8 0 0 1 0 12.8v2.1a10 10 0 0 0 0-17z"/></svg>';
        btn.classList.remove('speaking', 'paused');
    }

    function toggleSpeech(btn, text) {
        // A different message is mid-speech — stop it before starting this one
        if (currentSpeakBtn && currentSpeakBtn !== btn) {
            speechSynthesis.cancel();
            resetSpeakBtn(currentSpeakBtn);
            currentSpeakBtn = null;
            currentUtterance = null;
        }

        if (currentSpeakBtn !== btn) {
            // Fresh start for this message
            currentUtterance = new SpeechSynthesisUtterance(text);
            currentSpeakBtn = btn;
            currentUtterance.onend = () => {
                resetSpeakBtn(btn);
                currentUtterance = null;
                currentSpeakBtn = null;
            };
            speechSynthesis.speak(currentUtterance);
            btn.textContent = '⏸';
            btn.classList.add('speaking');
        } else if (speechSynthesis.speaking && !speechSynthesis.paused) {
            // Pause where it is
            speechSynthesis.pause();
            btn.textContent = '▶';
            btn.classList.replace('speaking', 'paused');
        } else if (speechSynthesis.paused) {
            // Resume from the same point
            speechSynthesis.resume();
            btn.textContent = '⏸';
            btn.classList.replace('paused', 'speaking');
        }
    }

        function createVoiceMessage(audioUrl, who, timestamp) {
        const msg = document.createElement('div');
        msg.className = 'dpniti-msg dpniti-voice-msg ' + who;
        msg.dataset.timestamp = timestamp || new Date().toISOString();

        msg.innerHTML = `
            <button class="dpniti-play-btn" aria-label="Play voice message">▶</button>
            <div class="dpniti-waveform"></div>
            <audio src="${audioUrl}" style="display:none"></audio>
            <div class="dpniti-msg-transcript">Transcribing…</div>
            <span class="dpniti-msg-time"></span>
        `;
        msg.querySelector('.dpniti-msg-time').textContent = formatISTTime(msg.dataset.timestamp);

        const audioEl = msg.querySelector('audio');
        const playBtn = msg.querySelector('.dpniti-play-btn');

        playBtn.addEventListener('click', () => {
            if (audioEl.paused) {
                document.querySelectorAll('.dpniti-voice-msg audio').forEach(a => {
                    if (a !== audioEl && !a.paused) {
                        a.pause();
                        a.closest('.dpniti-voice-msg').querySelector('.dpniti-play-btn').textContent = '▶';
                    }
                });
                audioEl.play();
                playBtn.textContent = '⏸';
            } else {
                audioEl.pause();
                playBtn.textContent = '▶';
            }
        });
        audioEl.addEventListener('ended', () => { playBtn.textContent = '▶'; });

        const waveform = msg.querySelector('.dpniti-waveform');
        for (let i = 0; i < 24; i++) {
            const bar = document.createElement('span');
            bar.style.height = (6 + Math.random() * 14) + 'px';
            waveform.appendChild(bar);
        }
        return msg;
    }

    async function startRecording(body) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = () => handleRecordingStop(body, stream);
        mediaRecorder.start();
    }

    async function handleRecordingStop(body, stream) {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        const audioUrl = URL.createObjectURL(blob);

        const voiceMsg = createVoiceMessage(audioUrl, 'user');
        body.appendChild(voiceMsg);
        body.scrollTop = body.scrollHeight;

        try {
            const form = new FormData();
            form.append('audio', blob, 'voice.webm');
            const res = await fetch(PYTHON_API_URL + '/transcribe', {
                method: 'POST',
                credentials: 'include',
                body: form
            });
            const { text } = await res.json();
            voiceMsg.dataset.messageText = text;
            voiceMsg.querySelector('.dpniti-msg-transcript').textContent = text;
            saveConversation(body);
            botReply(text, body);
        } catch (e) {
            voiceMsg.querySelector('.dpniti-msg-transcript').textContent = 'Could not transcribe. Try again.';
        }
    }

    function saveConversation(body) {
        const messages = Array.from(body.querySelectorAll('.dpniti-msg:not(.typing)')).map(function (message) {
            return {
                text: message.dataset.messageText,
                who: message.classList.contains('user') ? 'user' : 'bot',
                timestamp: message.dataset.timestamp,
                traceId: message.dataset.traceId || ''
            };
        });
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
    }

    function loadConversation() {
        try {
            const messages = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '[]');
            return Array.isArray(messages) ? messages : [];
        } catch (e) {
            return [];
        }
    }

    function initWidget() {
        if (document.querySelector('.dpniti-widget-root')) return;

        const root = document.createElement('div');
        root.className = 'dpniti-widget-root';

        const fabWrap = document.createElement('div');
        fabWrap.className = 'dpniti-fab-wrap';

        const prompt = document.createElement('div');
        prompt.className = 'dpniti-prompt';
        prompt.textContent = 'Hii i am DPniti how may i help you ?';

        const fab = document.createElement('button');
        fab.className = 'dpniti-fab';
        fab.setAttribute('aria-label', 'Open DPniti assistant');

        const fabImg = document.createElement('img');
        fabImg.src = 'images/extra/dp.jpeg';
        fabImg.alt = 'DPniti assistant';
        fab.appendChild(fabImg);

        fabWrap.appendChild(prompt);
        fabWrap.appendChild(fab);
        root.appendChild(fabWrap);

        const panel = document.createElement('section');
        panel.className = 'dpniti-chat-panel';

        const header = document.createElement('div');
        header.className = 'dpniti-chat-header';

        const avatar = document.createElement('img');
        avatar.src = 'images/extra/dp.jpeg';
        avatar.className = 'dpniti-header-avatar';
        avatar.alt = 'DPniti';

        const headerInfo = document.createElement('div');
        headerInfo.className = 'dpniti-header-info';

        const title = document.createElement('div');
        title.className = 'dpniti-chat-title';
        title.textContent = 'DPniti';

        const status = document.createElement('div');
        status.className = 'dpniti-header-status';
        status.textContent = '● Online';

        headerInfo.appendChild(title);
        headerInfo.appendChild(status);

        const headerBtns = document.createElement('div');
        headerBtns.className = 'dpniti-header-btns';

        const resetBtn = document.createElement('button');
        resetBtn.className = 'dpniti-reset-btn';
        resetBtn.textContent = '↺';
        resetBtn.title = 'Reset chat';

        const close = document.createElement('button');
        close.className = 'dpniti-minimize';
        close.textContent = '×';
        close.setAttribute('aria-label', 'Minimize chat');

        headerBtns.appendChild(resetBtn);
        headerBtns.appendChild(close);

        header.appendChild(avatar);
        header.appendChild(headerInfo);
        header.appendChild(headerBtns);

        const body = document.createElement('div');
        body.className = 'dpniti-chat-body';
        const savedMessages = loadConversation();
        if (savedMessages.length) {
            savedMessages.forEach(function (message) {
                const messageElement = createMessage(message.text, message.who, message.timestamp);
                messageElement.dataset.traceId = message.traceId || '';
                body.appendChild(messageElement);
            });
        } else {
            body.appendChild(createMessage('Hii i am DPniti! Ask me anything about students, faculty, timetables or subjects.', 'bot'));
            saveConversation(body);
        }

        const disclaimer = document.createElement('div');
        disclaimer.className = 'dpniti-disclaimer';
        disclaimer.textContent = 'DPniti can make mistakes. Check important info.';

        const inputRow = document.createElement('div');
        inputRow.className = 'dpniti-chat-input';

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Type your message...';

                const micBtn = document.createElement('button');
        micBtn.type = 'button';
        micBtn.className = 'dpniti-mic-btn';
        micBtn.innerHTML = `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
        <line x1="12" y1="19" x2="12" y2="23"></line>
        <line x1="8" y1="23" x2="16" y2="23"></line>
    </svg>`;
        micBtn.setAttribute('aria-label', 'Record voice message');
        micBtn.title = 'Microphone';

        const send = document.createElement('button');
        send.type = 'button';
        send.className = 'dpniti-send-btn';
        send.innerHTML = '<span aria-hidden="true">&#10148;</span>';
        send.setAttribute('aria-label', 'Send message');
        send.title = 'Send';

        function setGenerating(generating) {
            send.classList.toggle('generating', generating);
            send.innerHTML = generating
                ? '<span aria-hidden="true">&#9632;</span>'
                : '<span aria-hidden="true">&#10148;</span>';
            send.setAttribute('aria-label', generating ? 'Stop generating response' : 'Send message');
            send.title = generating ? 'Stop generating response' : 'Send';
        }

        inputRow.appendChild(input);
        inputRow.appendChild(micBtn);
        inputRow.appendChild(send);

        panel.appendChild(header);
        panel.appendChild(body);
        panel.appendChild(disclaimer);
        panel.appendChild(inputRow);

        root.appendChild(panel);
        document.body.appendChild(root);

        function openPanel() {
            panel.classList.add('open');
            fabWrap.style.display = 'none';
            input.focus();
        }

        function closePanel() {
            panel.classList.remove('open');
            fabWrap.style.display = 'flex';
        }

        async function sendMessage() {
            const text = input.value.trim();
            if (!text) return;
            if (pendingCancellation) {
                await pendingCancellation;
                pendingCancellation = null;
            }
            body.appendChild(createMessage(text, 'user'));
            const userMessage = body.lastElementChild;
            input.value = '';
            body.scrollTop = body.scrollHeight;
            saveConversation(body);
            botReply(text, body, setGenerating, userMessage);
        }

        function cancelActiveRequest() {
            if (!activeRequest) return;
            const request = activeRequest;
            conversationVersion += 1;
            pendingCancellation = fetch(PYTHON_API_URL + '/cancel', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: SESSION_ID,
                    request_id: request.requestId
                }),
                keepalive: true
            }).catch(() => {});
            request.controller.abort();
            activeRequest = null;
            request.onGeneratingChange(false);
            return pendingCancellation;
        }

                micBtn.addEventListener('click', async () => {
            if (!isRecording) {
                try {
                    await startRecording(body);
                    isRecording = true;
                    micBtn.classList.add('recording');
                    micBtn.innerHTML = '<span aria-hidden="true">⏹</span>';
                } catch (e) {
                    alert('Microphone access denied or unavailable.');
                }
            } else {
                mediaRecorder.stop();
                isRecording = false;
                micBtn.classList.remove('recording');
                micBtn.innerHTML = `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
            </svg>`;
            }
        });

        resetBtn.addEventListener('click', async function () {
            conversationVersion += 1;
            if (activeRequest) {
                await cancelActiveRequest();
                setGenerating(false);
            }
            if (pendingCancellation) {
                await pendingCancellation;
                pendingCancellation = null;
            }
            await fetch(PYTHON_API_URL + '/reset', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: SESSION_ID })
            }).catch(() => {});
            body.innerHTML = '';
            body.appendChild(createMessage('Chat reset! How can I help you?', 'bot'));
            saveConversation(body);
        });

        fab.addEventListener('click', openPanel);
        prompt.addEventListener('click', openPanel);
        close.addEventListener('click', closePanel);
        send.addEventListener('click', function () {
            if (activeRequest) {
                cancelActiveRequest();
                return;
            }
            void sendMessage();
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') void sendMessage();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initWidget);
    } else {
        initWidget();
    }
})();