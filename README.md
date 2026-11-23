# DPniti Academic Portal

A full-stack academic dashboard and student portal built for a university environment. The project combines a secure authentication system, student/faculty information dashboards, document access, timetable viewing, and an AI-powered academic chatbot to support students and staff.

## Project Overview

This system helps users:
- Sign in securely with role-based access
- View academic dashboard and profile information
- Browse faculty and student records
- Access timetable and academic documents
- Ask academic questions through an AI chatbot connected to institutional data

## Tech Stack

- Frontend: HTML, CSS, JavaScript
- Backend: Node.js, Express.js
- Database: MySQL (authentication) and PostgreSQL (academic chatbot data)
- Chatbot: Python, FastAPI, OpenRouter / LLM integration
- Infrastructure: Docker, Docker Compose, Nginx

## Architecture

- `frontend/` — static web interface for login, dashboard, faculty pages, profile, timetable, and documents
- `backend/` — authentication API with JWT-based login/logout and session verification
- `chatbot/` — AI assistant for academic queries with SQL-based retrieval and observability
- `database/` — database schema for login and academic data
- `docker-compose.yml` — spins up the full application stack
- `nginx.conf` — serves the frontend and routes requests

## Key Features

- Role-based login and secure session handling
- Protected academic dashboard and user access flow
- Faculty directory and student-related information views
- Timetable and document accessibility
- AI-enabled chatbot for academic assistance
- Containerized deployment for easy setup and scalability

## Getting Started

1. Clone the repository.
2. Copy the root environment template if needed and set the required values:

```powershell
Copy-Item .env.example .env
```

At minimum, set `ACADEMIC_DB_PASSWORD`, `JWT_SECRET`, and `GEMINI_API_KEY`.
The PostgreSQL academic database uses the credentials in `docker-compose.yml`
and is exposed locally at `127.0.0.1:5433`.

3. Run the full stack:

```bash
docker compose up --build
```

On the first start, PostgreSQL creates the `faculty`, `student`, and
`timetable` tables and imports the data from
[`chatbot/postgres_init.sql`](chatbot/postgres_init.sql). The initialization
script runs only when the `academic_db_data` volume is created for the first
time.

If the database volume was created before this setup was added, recreate only
the academic database volume before starting again:

```powershell
docker compose down
docker volume rm dpniti_academic_db_data
docker compose up --build
```

To run the chatbot directly instead of through Docker, start PostgreSQL with
`docker compose up -d academic-db`, then run from the `chatbot` directory:

```powershell
python -m pip install -r requirements.txt
$env:ACADEMIC_DATABASE_URL = "postgresql+psycopg://dpniti_academic_user:<password>@127.0.0.1:5433/dpniti_academic"
uvicorn chatbot_api:app --host 127.0.0.1 --port 5001
```

For that direct run, use this PostgreSQL URL:

```text
postgresql+psycopg://dpniti_academic_user:<password>@127.0.0.1:5433/dpniti_academic
```

Do not commit `.env` files or real API keys.

4. Open the app in the browser:
- Frontend: http://localhost
- Backend API: http://localhost:5000
- Chatbot: http://localhost:5001

## Temporary public demo with Cloudflare Quick Tunnel

This option needs no cloud VM, Cloudflare account, or domain. Your computer
still runs the app and must remain on and connected to the internet. The
temporary URL changes each time the tunnel is started, and Cloudflare provides
no uptime guarantee for Quick Tunnels.

1. Install `cloudflared` using the official
   [Windows installer](https://developers.cloudflare.com/tunnel/downloads/).
2. In the project directory, start the app with its tunnel-specific port
   bindings:

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up --build -d
   ```

   Set `COOKIE_SECURE=true` in the root `.env` so login cookies are marked
   secure on the public HTTPS URL.
3. In a second PowerShell window, run:

   ```powershell
   cloudflared tunnel --url http://localhost:8080
   ```

4. Open the `https://...trycloudflare.com` URL printed in that window. Keep
   both Docker Desktop and the tunnel process running. The app's login and
   chatbot are public to anyone who obtains the URL; only share it with people
   you trust.
5. To stop the tunnel, press `Ctrl+C` in its window. Stop the containers with:

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.tunnel.yml down
   ```

## Free demo deployment on Render and Neon

The Render Blueprint runs Nginx, the Node.js login API, and the Python chatbot
in one web service. Neon provides the PostgreSQL database for both login and
academic data. The MySQL-based local Compose setup remains unchanged.

This is a low-traffic demo setup, not an always-on production service. Render's
free web services spin down after inactivity and have monthly usage limits.
Neon's free database scales to zero and has storage/compute limits. Check the
current [Render free-plan limits](https://render.com/docs/free) and
[Neon free-plan limits](https://neon.com/pricing) before proceeding.

1. Push the intended source changes to a private GitHub repository. Do not
   commit `.env` or secrets. The root `.dockerignore` keeps environment files
   out of the Render image build.
2. Create a Neon free project in a region near Render. In the Neon SQL Editor,
   run [`database/login_schema.postgres.sql`](database/login_schema.postgres.sql)
   and [`chatbot/postgres_init.sql`](chatbot/postgres_init.sql) once. The
   second script imports the academic dataset; only run it if you have
   permission to host those records. Keep the GitHub repository private.
3. In Render, create a Blueprint from the repository's `render.yaml`. When
   prompted, set both `AUTH_DATABASE_URL` and `ACADEMIC_DATABASE_URL` to the
   Neon connection URL. Also enter `GEMINI_API_KEY`,
   `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` in Render's environment
   settings. Never commit or share these values. The Blueprint generates
   `JWT_SECRET` and enables secure cookies.
4. Wait for the service health check to pass, then open its
   `https://...onrender.com` URL. Nginx keeps the existing login guard in front
   of protected pages and proxies chatbot requests to the Python API.

The PostgreSQL schema does not contain login accounts. There is no signup
route, so create or migrate authorized user rows in the Neon `users` table
before expecting users to log in. The free Render service can sleep after
inactivity, and Neon's free database scales to zero when idle. Free-tier limits
can change; keep backups of data you need.

## Public deployment on Oracle Cloud

The Oracle Compose overlay serves the app through Caddy with HTTPS and keeps
the application APIs and databases off public host ports. Oracle's free-tier
availability and eligibility can vary; check the estimated cost before
creating resources. This setup does not create an Oracle account or VM for you.

1. Create an Oracle Cloud account and an eligible free-tier Ubuntu VM. Keep the
   private SSH key on your computer. In the VM's network rules, allow TCP 22
   only from your own IP, and allow TCP 80 and 443 for public web access. Do
   not open ports 3306, 5432, 5000, or 5001.
2. Set up a free DNS hostname, such as DuckDNS, and point it to the VM's public
   IP. The hostname must resolve before Caddy can issue an HTTPS certificate.
3. Install Docker Engine and the Docker Compose plugin on the VM, then clone
   this repository there.
4. Copy `.env.example` to `.env` on the VM and replace the placeholders.
   Configure `APP_DOMAIN`, `ACME_EMAIL`, strong database passwords, a random
   `JWT_SECRET`, `GEMINI_API_KEY`, and Langfuse's public and secret keys.
   Generate URL-safe random secrets (for example, `openssl rand -hex 32`).
   Never commit or share `.env`; keep the Langfuse secret key server-side.
5. From the repository directory on the VM, start the production stack:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.oracle.yml up -d --build
   ```

   After DNS has updated, open `https://<your-hostname>`. Caddy obtains and
   renews the HTTPS certificate automatically. Change `LANGFUSE_HOST` if your
   Langfuse project uses a different region.

The app has no self-registration endpoint: users must already exist in the
MySQL `users` table. Confirm you are permitted to host the academic data and
send chatbot prompts/answers to Langfuse before using real student information.
Docker volumes persist database data on the VM, but they are not backups; set
up backups before relying on the deployment. Free-tier limits and charges can
change, so monitor the provider's billing page.

## Project Structure

```text
.
├── backend/
├── chatbot/
├── database/
├── frontend/
├── docker-compose.yml
├── nginx.conf
├── README.md
└── .env
```

## Role in the Project

This project demonstrates practical implementation of:
- Full-stack web development
- Authentication and authorization
- Database-driven application design
- Integration of AI into an academic workflow
- Deployment using modern container-based architecture

## Summary

DPniti is a complete academic support platform designed to improve student and faculty interaction through a modern dashboard and AI assistant. It reflects a strong combination of frontend development, backend services, database design, and intelligent system integration.
