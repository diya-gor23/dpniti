/* =====================================================
   EduPortal — Auth Script  |  script.js
   Panel toggle + Login + Signup
   ===================================================== */

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ── Helpers ────────────────────────────────────────────
function el(id)        { return document.getElementById(id); }
function setErr(id, msg) { const e = el(id); if (e) e.textContent = msg; }
function clearErr(...ids) { ids.forEach(id => setErr(id, '')); }

// ── Panel Toggle ───────────────────────────────────────
const wrapper    = el('authWrapper');
const signUpBtn  = el('signUpBtn');
const signInBtn  = el('signInBtn');

// Auto-open Sign Up panel if redirected from signup.html
if (wrapper && sessionStorage.getItem('openSignup') === '1') {
    sessionStorage.removeItem('openSignup');
    wrapper.classList.add('right-panel-active');
}

if (signUpBtn) {
    signUpBtn.addEventListener('click', () => {
        wrapper.classList.add('right-panel-active');
    });
}

if (signInBtn) {
    signInBtn.addEventListener('click', () => {
        wrapper.classList.remove('right-panel-active');
    });
}

// ── LOGIN form ─────────────────────────────────────────
const loginForm = el('loginForm');

if (loginForm) {
    const nameIn  = el('loginName');
    const emailIn = el('loginEmail');
    const passIn  = el('loginPassword');

    nameIn .addEventListener('input', () => clearErr('siNameErr',  'loginError'));
    emailIn.addEventListener('input', () => clearErr('siEmailErr', 'loginError'));
    passIn .addEventListener('input', () => clearErr('siPassErr',  'loginError'));

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearErr('siNameErr', 'siEmailErr', 'siPassErr', 'loginError');

        let valid = true;

        if (!nameIn.value.trim()) {
            setErr('siNameErr', 'Name is required'); valid = false;
        } else if (nameIn.value.trim().length < 2) {
            setErr('siNameErr', 'At least 2 characters'); valid = false;
        }

        if (!emailIn.value.trim()) {
            setErr('siEmailErr', 'Email is required'); valid = false;
        } else if (!emailRegex.test(emailIn.value)) {
            setErr('siEmailErr', 'Enter a valid email'); valid = false;
        }

        if (!passIn.value) {
            setErr('siPassErr', 'Password is required'); valid = false;
        } else if (passIn.value.length < 6) {
            setErr('siPassErr', 'At least 6 characters'); valid = false;
        }

        if (!valid) return;

        const btn = loginForm.querySelector('button[type="submit"]');
        btn.disabled    = true;
        btn.textContent = 'Signing in…';

        try {
            const res  = await fetch('http://localhost:5000/api/auth/login', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    name:     nameIn.value.trim(),
                    email:    emailIn.value.trim(),
                    password: passIn.value
                })
            });
            const data = await res.json();

            if (res.ok) {
                if (data.token)       localStorage.setItem('authToken',  data.token);
                if (data.user?.name)  localStorage.setItem('userName',   data.user.name);
                if (data.user?.email) localStorage.setItem('userEmail',  data.user.email);

                loginForm.reset();
                window.location.href = 'dashboard.html';
            } else {
                setErr('loginError', data.message || 'Login failed. Try again.');
            }
        } catch {
            setErr('loginError', 'Connection error. Make sure backend is running on port 5000.');
        }

        btn.disabled    = false;
        btn.textContent = 'SIGN IN';
    });
}

// ── SIGNUP form ────────────────────────────────────────
const signupForm = el('signupForm');

if (signupForm) {
    const nameIn  = el('signupName');
    const emailIn = el('signupEmail');
    const passIn  = el('signupPassword');

    nameIn .addEventListener('input', () => clearErr('suNameErr',  'signupError'));
    emailIn.addEventListener('input', () => clearErr('suEmailErr', 'signupError'));
    passIn .addEventListener('input', () => clearErr('suPassErr',  'signupError'));

    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearErr('suNameErr', 'suEmailErr', 'suPassErr', 'signupError');
        el('signupSuccess').classList.remove('show');

        let valid = true;

        if (!nameIn.value.trim()) {
            setErr('suNameErr', 'Name is required'); valid = false;
        } else if (nameIn.value.trim().length < 2) {
            setErr('suNameErr', 'At least 2 characters'); valid = false;
        }

        if (!emailIn.value.trim()) {
            setErr('suEmailErr', 'Email is required'); valid = false;
        } else if (!emailRegex.test(emailIn.value)) {
            setErr('suEmailErr', 'Enter a valid email'); valid = false;
        }

        if (!passIn.value) {
            setErr('suPassErr', 'Password is required'); valid = false;
        } else if (passIn.value.length < 6) {
            setErr('suPassErr', 'At least 6 characters'); valid = false;
        }

        if (!valid) return;

        const btn = signupForm.querySelector('button[type="submit"]');
        btn.disabled    = true;
        btn.textContent = 'Creating account…';

        try {
            const res  = await fetch('http://localhost:5000/api/auth/signup', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    name:     nameIn.value.trim(),
                    email:    emailIn.value.trim(),
                    password: passIn.value
                })
            });
            const data = await res.json();

            if (res.ok) {
                const s = el('signupSuccess');
                s.textContent = '✓ ' + (data.message || 'Account created!');
                s.classList.add('show');
                signupForm.reset();

                // Slide back to Sign In after 1.5s
                setTimeout(() => {
                    wrapper.classList.remove('right-panel-active');
                    s.classList.remove('show');
                }, 1500);
            } else {
                setErr('signupError', data.message || 'Signup failed. Try again.');
            }
        } catch {
            setErr('signupError', 'Connection error. Make sure backend is running on port 5000.');
        }

        btn.disabled    = false;
        btn.textContent = 'SIGN UP';
    });
}

