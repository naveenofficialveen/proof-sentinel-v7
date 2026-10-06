# Digital Proof Verification and Evidence Analysis System

URLs: user site `/` and admin site `/admin` (Next.js). API on :8000 (FastAPI).

Run (Docker Desktop must be running). Open a terminal INSIDE this folder (the one with docker-compose.yml):
    docker compose up --build
User site: http://localhost:3000     Admin site: http://localhost:3000/admin
Admin login: username `admin`, password = `ADMIN_PASSWORD` in `.env` (fresh local setup default `Admin@12345`, change it).
If you already have an old PostgreSQL Docker volume, changing `.env` does not change the existing admin password. After setting the new `ADMIN_PASSWORD`, reset the existing admin once with:
    docker compose exec backend python -c "from app.db import SessionLocal; from app.models import Admin; from app.config import settings; from app.security import hash_password; db=SessionLocal(); a=db.query(Admin).filter(Admin.username==settings.admin_username).first(); a.password_hash=hash_password(settings.admin_password); db.commit(); db.close(); print('Admin password reset')"

Forgot password sends a 6-digit code by e-mail (valid 10 minutes, 5 tries, 60 s resend wait).
Gmail setup: Google Account > Security > turn on 2-Step Verification > App passwords > create one.
Then in `.env` fill SMTP_USER (your Gmail), SMTP_PASSWORD (the 16-character app password), SMTP_FROM (your Gmail).
Restart with: docker compose down, then docker compose up
If SMTP_USER is empty and DEMO_SHOW_CODE=true (local testing only), forgot password skips the e-mail code:
you enter the email, then only a new password and confirm password.
The shortcut turns itself off when HTTPS cookies are on (hosted) or when a mail account is set up.
Test from a phone on the same Wi-Fi: open http://<this PC's IP>:3000 (allow ports 3000 and 8000 in Windows Firewall).

Other settings: MAX_UPLOAD_MB=100, COOKIE_SECURE=true when served over HTTPS.

Online hosting and GitHub: see HOSTING.md (uses docker-compose.prod.yml, Caddyfile and .env.production.example).

New in this version (user site, Metadata Viewer > Forensic checks): social-media trace with JPEG quantisation fingerprint, magic-bytes file type check,
ELA tamper heat-map, document OCR hash lock, location map with privacy score, quality gauge, size-vs-sensor check, file-name pattern engine and hex marker parser.
Metadata Remover now lists what the file contains so you can remove only the items you tick (or Select all), and cleans many files at once in the background with a live progress bar.
Admin Settings no longer has the "Send test e-mail" box.
