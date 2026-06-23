// frontend/config.js
// Automatically detects local vs production environment

const CONFIG = (() => {
  const isLocal = window.location.hostname === 'localhost' || 
                  window.location.hostname === '127.0.0.1';

  return {
    // Backend API (Node.js auth server)
    BACKEND_URL: isLocal
      ? 'http://localhost:5000'
      : '',            // empty = same origin (nginx proxies /api → backend)

    // Chatbot API (Python Flask)
    CHATBOT_URL: isLocal
      ? 'http://localhost:5001'
      : '',            // empty = same origin (nginx proxies /chat → chatbot)
    PYTHON_API_URL: isLocal
      ? 'http://localhost:5001'
      : '',
  };
})();