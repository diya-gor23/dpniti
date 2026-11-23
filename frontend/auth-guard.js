(() => {
  const currentPage = (window.location.pathname.split('/').pop() || '').toLowerCase();
  const publicPages = new Set([
    'about-us.html',
    'contact-us.html',
    'faculty.html',
    'faculty-detail.html',
    'index.html',
  ]);
  const protectedPages = new Set([
    'dashboard.html',
    'students.html',
    'profile.html',
    'timetable-viewer.html',
    'extract-pdf-page.html',
  ]);

  function isProtectedPage() {
    return protectedPages.has(currentPage);
  }

  function isPublicPage() {
    return publicPages.has(currentPage) || currentPage === '' || currentPage === 'login';
  }

  function redirectToLogin() {
    window.location.replace('login/index.html');
  }

  window.DPnitiAuth = {
    role: localStorage.getItem('role') || '',
    allowedSem: Number(localStorage.getItem('allowedSem')) || null,
    name: localStorage.getItem('userName') || '',
    async logout() {
      try {
        await fetch(`${getBackendUrl()}/api/auth/logout`, {
          method: 'POST',
          credentials: 'include',
        });
      } catch (e) {
        // Even if the network call fails, still clear local UI state and
        // send the user to login — the cookie will simply expire naturally.
      }
      localStorage.clear();
      redirectToLogin();
    },
  };

  function getBackendUrl() {
    if (typeof CONFIG !== 'undefined') return CONFIG.BACKEND_URL;
    const isLocal = window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1';
    return isLocal ? 'http://localhost:5000' : '';
  }

  // Only enforce login on protected pages. Public pages such as About Us,
  // Contact Us, and Faculty pages should remain accessible without authentication.
  fetch(`${getBackendUrl()}/api/auth/verify`, {
    credentials: 'include',
  })
    .then((res) => (res.ok ? res.json() : Promise.reject()))
    .then((data) => {
      const user = data?.user;
      if (!user) {
        if (isProtectedPage()) {
          redirectToLogin();
        }
        return;
      }

      window.DPnitiAuth.role = user.role || window.DPnitiAuth.role;
      window.DPnitiAuth.allowedSem = user.allowed_sem ?? window.DPnitiAuth.allowedSem;
      window.DPnitiAuth.name = user.name || window.DPnitiAuth.name;
      localStorage.setItem('role', window.DPnitiAuth.role);
      localStorage.setItem('userName', window.DPnitiAuth.name);
      localStorage.setItem('userEmail', user.username || localStorage.getItem('userEmail') || '');
      localStorage.setItem('allowedSem', window.DPnitiAuth.allowedSem ?? '');
      applyRoleVisibility();
      window.dispatchEvent(new Event('dpniti-auth-updated'));
    })
    .catch(() => {
      if (isProtectedPage()) {
        // Verify failed — session cookie is missing/expired. Only redirect for
        // protected pages; public pages stay viewable without a login.
        redirectToLogin();
      }
    });

  function applyRoleVisibility() {
    if (window.DPnitiAuth.role === 'student') {
      document.querySelectorAll('[data-staff-only]').forEach((element) => element.remove());
    }
  }

  if (isPublicPage()) {
    window.addEventListener('DOMContentLoaded', applyRoleVisibility);
    return;
  }

  window.addEventListener('DOMContentLoaded', applyRoleVisibility);
})();
