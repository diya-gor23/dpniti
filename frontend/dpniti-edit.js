(function () {
    // Faculty-only "Edit my data" view for the DPniti widget.
    // UI gating only — the server re-checks role, ownership and password.
    const BACKEND = typeof CONFIG !== 'undefined' ? CONFIG.BACKEND_URL : 'http://localhost:5000';
    const CHATBOT = typeof CONFIG !== 'undefined' ? (CONFIG.PYTHON_API_URL || '') : 'http://localhost:5001';
    const EDIT_API = CHATBOT + '/chat/faculty-edit';

    const LABELS = {
        name: 'Name', email: 'Email', phone: 'Phone', cabin: 'Cabin', designation: 'Designation',
        qualification: 'Qualification', phd_subject: 'PhD subject', college: 'College',
        research_interest: 'Research interest', day_of_week: 'Day', start_time: 'Start time',
        end_time: 'End time', subject: 'Subject', division: 'Division', group_name: 'Group',
        classroom: 'Room', semester: 'Semester'
    };
    const label = k => LABELS[k] || k;

    function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    }
    function btn(text, cls, onClick) {
        const b = el('button', 'dpniti-edit-btn ' + (cls || ''), text);
        b.type = 'button';
        b.addEventListener('click', onClick);
        return b;
    }

    function apiErrorMessage(data, status) {
        const detail = data && (data.detail !== undefined ? data.detail : data.message);
        if (typeof detail === 'string' && detail.trim()) return detail;
        if (Array.isArray(detail)) {
            const messages = detail.map(function (item) {
                if (typeof item === 'string') return item;
                if (item && typeof item.msg === 'string') return item.msg;
                return '';
            }).filter(Boolean);
            if (messages.length) return messages.join(' ');
        }
        if (detail && typeof detail === 'object') {
            const values = Object.values(detail).filter(function (value) {
                return typeof value === 'string' && value.trim();
            });
            if (values.length) return values.join(' ');
        }
        return 'Request failed (' + status + ').';
    }

    async function api(path, opts) {
        const res = await fetch(path, Object.assign({ credentials: 'include' }, opts));
        let data = {};
        try { data = await res.json(); } catch (e) { /* non-JSON error */ }
        if (!res.ok) throw new Error(apiErrorMessage(data, res.status));
        return data;
    }

    function init() {
        if (localStorage.getItem('role') !== 'faculty') return;
        const panel = document.querySelector('.dpniti-chat-panel');
        const btns = document.querySelector('.dpniti-header-btns');
        if (!panel || !btns || btns.querySelector('.dpniti-edit-open')) return;

        const openBtn = el('button', 'dpniti-edit-open', '✎');
        openBtn.title = 'Edit my data';
        openBtn.setAttribute('aria-label', 'Edit my data');
        btns.insertBefore(openBtn, btns.querySelector('.dpniti-reset-btn'));

        const view = el('div', 'dpniti-edit-view');
        view.hidden = true;
        panel.appendChild(view);

        let data = null;       // /me payload
        let current = null;    // { target, rowId, fields, original }

        function show() { view.hidden = false; }
        function hide() { view.hidden = true; view.replaceChildren(); }

        function shell(title, onBack) {
            view.replaceChildren();
            const bar = el('div', 'dpniti-edit-bar');
            if (onBack) bar.appendChild(btn('←', 'dpniti-edit-back', onBack));
            bar.appendChild(el('div', 'dpniti-edit-title', title));
            bar.appendChild(btn('×', 'dpniti-edit-back', hide));
            const content = el('div', 'dpniti-edit-content');
            view.append(bar, content);
            return content;
        }

        function message(parent, text, kind) {
            const m = el('div', 'dpniti-edit-msg ' + (kind || ''), text);
            parent.appendChild(m);
            return m;
        }

        async function menu() {
            const c = shell('What do you want to change?');
            show();
            message(c, 'Loading…');
            try {
                data = await api(EDIT_API + '/me');
            } catch (e) {
                c.replaceChildren();
                message(c, e.message, 'error');
                return;
            }
            c.replaceChildren();
            message(c, 'You can only edit your own details and your own timetable.');
            c.appendChild(btn('My profile details', 'primary', profileForm));
            c.appendChild(btn('My timetable (' + data.timetable.length + ' lectures)', 'primary', lectureList));
            c.appendChild(btn('Cancel', '', hide));
        }

        function lectureList() {
            const c = shell('Which lecture?', menu);
            if (!data.timetable.length) message(c, 'No lectures found in your timetable.');
            data.timetable.forEach(function (row) {
                const b = el('button', 'dpniti-edit-card');
                b.type = 'button';
                b.appendChild(el('strong', '', (row.day_of_week || '') + ' · ' + (row.start_time || '') + '–' + (row.end_time || '')));
                b.appendChild(el('span', '', [row.subject, row.division, row.group_name, row.classroom].filter(Boolean).join(' · ')));
                b.addEventListener('click', function () { form('timetable', row.id, data.timetable_fields, row, lectureList); });
                c.appendChild(b);
            });
        }

        function profileForm() {
            form('faculty', null, data.faculty_fields, data.faculty, menu);
        }

        function form(target, rowId, fields, original, back) {
            current = { target, rowId, fields, original };
            const c = shell(target === 'faculty' ? 'Edit profile' : 'Edit lecture', back);
            message(c, 'Change only what you need. Everything else stays as is.');
            const inputs = {};
            fields.forEach(function (k) {
                const wrap = el('label', 'dpniti-edit-field');
                wrap.appendChild(el('span', '', label(k)));
                const input = document.createElement('input');
                input.type = 'text';
                input.value = original[k] || '';
                input.maxLength = 255;
                if (k === 'start_time' || k === 'end_time') input.placeholder = 'HH:MM';
                inputs[k] = input;
                wrap.appendChild(input);
                c.appendChild(wrap);
            });
            const err = message(c, '', 'error');
            c.appendChild(btn('Review changes', 'primary', function () {
                const changes = {};
                fields.forEach(function (k) {
                    const v = inputs[k].value.trim();
                    if (v !== (original[k] || '')) changes[k] = v;
                });
                if (!Object.keys(changes).length) { err.textContent = 'Nothing changed.'; return; }
                if (Object.values(changes).some(v => !v)) { err.textContent = 'Fields cannot be empty.'; return; }
                confirmStep(changes, function () { form(target, rowId, fields, original, back); });
            }));
        }

        function confirmStep(changes, back) {
            const c = shell('Confirm changes', back);
            Object.keys(changes).forEach(function (k) {
                const row = el('div', 'dpniti-edit-diff');
                row.appendChild(el('span', 'k', label(k)));
                row.appendChild(el('span', 'old', current.original[k] || '—'));
                row.appendChild(el('span', 'arrow', '→'));
                row.appendChild(el('span', 'new', changes[k]));
                c.appendChild(row);
            });
            const wrap = el('label', 'dpniti-edit-field');
            wrap.appendChild(el('span', '', 'Enter your login password to save'));
            const pw = document.createElement('input');
            pw.type = 'password';
            pw.autocomplete = 'current-password';
            wrap.appendChild(pw);
            c.appendChild(wrap);
            const err = message(c, '', 'error');
            const save = btn('Save changes', 'primary', async function () {
                if (!pw.value) { err.textContent = 'Password is required.'; return; }
                save.disabled = true; err.textContent = '';
                try {
                    const conf = await api(BACKEND + '/api/auth/confirm-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ password: pw.value })
                    });
                    pw.value = '';
                    await api(EDIT_API + '/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-Edit-Token': conf.editToken },
                        body: JSON.stringify({
                            target: current.target,
                            row_id: current.rowId == null ? null : String(current.rowId),
                            changes
                        })
                    });
                    done();
                } catch (e) {
                    err.textContent = e.message;
                    save.disabled = false;
                }
            });
            c.appendChild(save);
        }

        function done() {
            const c = shell('Saved');
            message(c, 'Updated. DPniti will now answer using the new data.', 'ok');
            c.appendChild(btn('Edit something else', 'primary', menu));
            c.appendChild(btn('Back to chat', '', hide));
        }

        openBtn.addEventListener('click', menu);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
