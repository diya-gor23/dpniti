(function () {
    // Use CONFIG.API_URL from config.js, or fallback to Python service
    const PYTHON_API_URL = typeof CONFIG !== 'undefined' ? (CONFIG.PYTHON_API_URL || 'http://localhost:5001') : 'http://localhost:5001';
    const SESSION_ID = 'dpniti_' + Math.random().toString(36).slice(2);

    function createMessage(text, who) {
        const msg = document.createElement('div');
        msg.className = 'dpniti-msg ' + who;
        msg.textContent = text;
        return msg;
    }

    async function botReply(userText, body) {
        const typing = createMessage('DPniti is thinking...', 'bot typing');
        body.appendChild(typing);
        body.scrollTop = body.scrollHeight;
        try {
            const res  = await fetch(API_URL + '/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userText, session_id: SESSION_ID })
            });
            const data = await res.json();
            typing.remove();
            body.appendChild(createMessage(data.reply, 'bot'));
        } catch (e) {
            typing.remove();
            body.appendChild(createMessage('Could not reach AI server. Make sure chatbot_api.py is running on port 5001.', 'bot'));
        }
        body.scrollTop = body.scrollHeight;
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
        body.appendChild(createMessage('Hii i am DPniti! Ask me anything about students, faculty, timetables or subjects.', 'bot'));

        const inputRow = document.createElement('div');
        inputRow.className = 'dpniti-chat-input';

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Type your message...';

        const send = document.createElement('button');
        send.type = 'button';
        send.className = 'dpniti-send-btn';
        send.innerHTML = '<span aria-hidden="true">&#8599;</span>';
        send.setAttribute('aria-label', 'Send message');

        inputRow.appendChild(input);
        inputRow.appendChild(send);

        panel.appendChild(header);
        panel.appendChild(body);
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

        function sendMessage() {
            const text = input.value.trim();
            if (!text) return;
            body.appendChild(createMessage(text, 'user'));
            input.value = '';
            body.scrollTop = body.scrollHeight;
            botReply(text, body);
        }

        resetBtn.addEventListener('click', async function () {
            await fetch(API_URL + '/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: SESSION_ID })
            }).catch(() => {});
            body.innerHTML = '';
            body.appendChild(createMessage('Chat reset! How can I help you?', 'bot'));
        });

        fab.addEventListener('click', openPanel);
        prompt.addEventListener('click', openPanel);
        close.addEventListener('click', closePanel);
        send.addEventListener('click', sendMessage);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') sendMessage();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initWidget);
    } else {
        initWidget();
    }
})();
