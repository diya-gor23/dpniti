# AGENTS.md — Repository guidance for AI coding agents

Purpose: provide minimal, actionable knowledge so an AI agent can be productive quickly.

Quick run commands
- Backend (login-system/backend):
  - Install: `cd DPniti dashboard/login-system/backend && npm install`
  - Start: `npm start` (server listens on http://localhost:5000 by convention)
- Frontend (static): open `DPniti dashboard/login-system/frontend/index.html` in a browser
  - Optional dev server: `cd DPniti dashboard/login-system/frontend && python -m http.server 8000`
- Python services / chatbot: `python app.py` (project root)
- Chatbot helper: `start_chatbot.bat` (project root)

Key files and locations
- `DPniti dashboard/login-system/backend/server.js` — Express server & API routes
- `DPniti dashboard/login-system/backend/db.js` — MySQL connection; update credentials here
- `DPniti dashboard/login-system/frontend/*` — Static pages and client JS
- `app.py` — Python entrypoint (chatbot / other services)

Conventions & assumptions
- Backend: Node + Express + mysql2; DB name: `auth_db` (see login README)
- Frontend: plain HTML/CSS/vanilla JS; files live under the `frontend` folder
- Port: backend uses port 5000; frontend expects backend on `http://localhost:5000`
- Secrets/credentials: stored in `db.js` (no .env currently). Do NOT commit production secrets.

Common pitfalls
- MySQL must be running and `auth_db` created before starting the backend
- Update DB credentials in `DPniti dashboard/login-system/backend/db.js` before `npm start`
- Run `npm install` in the backend before starting if dependencies are missing

Links to existing docs
- Login system README: `DPniti dashboard/login-system/README.md`

Suggested next customizations for agents
- Add a `.github/copilot-instructions.md` with brief tasks the agent may perform
- Add a small `skills/` or `agents/` directory describing common operations (run, test, lint)

If you'd like, I can add `.github/copilot-instructions.md` or split instructions per subproject.
