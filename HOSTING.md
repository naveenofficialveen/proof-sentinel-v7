# Put the project on GitHub and host it online (user site `/` and admin site `/admin`)

GitHub only STORES the code. GitHub Pages cannot run this project (it needs Python, a database and Docker),
so the site runs on a rented Linux server (VPS). Both URLs live on one domain:
  https://yourdomain.com          (user site)
  https://yourdomain.com/admin    (admin site)

## Part A. Upload the code to GitHub (from your Windows PC)
1. Install Git for Windows (git-scm.com) and create a free account on github.com.
2. On GitHub: New repository, name `proof-sentinel`, choose **Private**, do NOT add a README, click Create.
3. In the project folder open `cmd` and run (replace YOURNAME):
     git init
     git add .
     git commit -m "first version"
     git branch -M main
     git remote add origin https://github.com/YOURNAME/proof-sentinel.git
     git push -u origin main
   The `.gitignore` file keeps your `.env` (passwords) OUT of GitHub. After pushing, open the repo and confirm there is no `.env` file.
   If a password ever reaches GitHub, change that password immediately.

## Part B. Get a server and a domain
1. Rent an Ubuntu 24.04 VPS with at least 2 CPU and 4 GB RAM (the image build uses OpenCV and ffmpeg). Note its public IP address.
2. Buy a domain. In its DNS settings add an **A record**: name `@` (and optionally `www`) pointing to the server IP. Wait until it resolves.

## Part C. Set up the server (connect with: ssh root@SERVER_IP)
1. Install Docker:   curl -fsSL https://get.docker.com | sh
2. Firewall:         ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable
3. Get the code:     git clone https://github.com/YOURNAME/proof-sentinel.git && cd proof-sentinel
                     (a private repo asks for a GitHub username and a Personal Access Token as the password)
4. Create the settings file:   cp .env.production.example .env   then   nano .env
   Fill DOMAIN, DB_PASSWORD (letters and numbers only), JWT_SECRET (run `openssl rand -hex 32`), ADMIN_PASSWORD and the Gmail lines. Save with Ctrl+O, Enter, Ctrl+X.
5. Start:            docker compose -f docker-compose.prod.yml up -d --build
   The first build takes 10 to 20 minutes. Caddy gets the HTTPS certificate by itself when the domain points at the server.
6. Open https://yourdomain.com and https://yourdomain.com/admin. To check Gmail, use "Forgot password" on the user site: the 6-digit code must arrive in the inbox (also look in spam).

## No domain yet? (free option)
Caddy needs a real domain name to get HTTPS, and the hosted site needs HTTPS for its login cookies. A free name works:
1. Create a free sub-domain at duckdns.org (for example `proofsentinel.duckdns.org`) and point it to the server IP.
2. Use that name as DOMAIN in `.env`. Everything else is the same.

## Part D. Daily use
- Update after you push new code:   cd proof-sentinel && git pull && docker compose -f docker-compose.prod.yml up -d --build
- See problems:                     docker compose -f docker-compose.prod.yml logs --tail 100 backend
- Backup the database:              docker compose -f docker-compose.prod.yml exec db pg_dump -U proof proof > backup.sql
- Uploaded evidence lives in the Docker volume `evidence`. Back it up too.

## Admin password
- ADMIN_PASSWORD in `.env` is used ONLY to create the first admin account. After you sign in at /admin, open Settings and use "Change admin password".
  Changing `.env` later does not change the password.
- Forgot the admin password? Run on the server:
    docker compose -f docker-compose.prod.yml exec db psql -U proof -d proof -c "DELETE FROM admins;"
    docker compose -f docker-compose.prod.yml restart backend
  The admin account is created again from ADMIN_PASSWORD in `.env`. Then change it in Settings.

## Forgot password when hosted
- The hosted site always uses the real e-mail code (docker-compose.prod.yml forces DEMO_SHOW_CODE=false and COOKIE_SECURE=true).
- Reset with only an email and a new password would let anyone take over any account, so it is never allowed online.
- Fill the SMTP_ lines in `.env`, restart, and test with "Forgot password" on the user site. Admin Settings shows whether the mail account is configured.

## Checklist before real users
- Strong ADMIN_PASSWORD and a random JWT_SECRET. Port 8000, the database and Redis are NOT exposed in the production file.
- Keep the server updated (apt update && apt upgrade). Turn on provider snapshots or backups.
- Gmail allows only a limited number of mails per day. For many users use a mail service built for it and change the SMTP_ lines.
- New in this version: the bulk cleaner, ELA heat-map, map lookup. Map tiles and the place-name button use OpenStreetMap, so the browser and the backend need internet access (normal on a VPS).
- This production setup was written but not tested on a live server. Fix anything the logs show, then re-run the start command.
