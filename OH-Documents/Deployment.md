# Django Deployment Operational Handbook

This handbook explains how to deploy a simple Django application on a production server (e.g., a DigitalOcean Droplet). It covers the entire process from cloning your Git repository to configuring Gunicorn and Nginx for production.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Cloning the Repository](#cloning-the-repository)
- [Python Virtual Environment & Dependencies](#python-virtual-environment--dependencies)
- [Django Configuration](#django-configuration)
- [Database Setup (SQLite3)](#database-setup-sqlite3)
- [Static Files Collection](#static-files-collection)
- [Gunicorn Setup](#gunicorn-setup)
- [Systemd Service for Gunicorn](#systemd-service-for-gunicorn)
- [Nginx Configuration](#nginx-configuration)
- [Permissions and Ownership](#permissions-and-ownership)
- [Starting and Managing Services](#starting-and-managing-services)
- [Logging and Troubleshooting](#logging-and-troubleshooting)
- [Final Notes](#final-notes)

---

## Prerequisites

Before beginning the deployment process, ensure you have:

- A production server (e.g., DigitalOcean Droplet) with a supported Linux distribution.
- A domain name (optional, but recommended) and proper DNS settings.
- `git`, `python3`, and `python3-venv` installed on the server.
- `nginx` installed for serving static files and proxying requests.
- Basic familiarity with Linux command-line operations.
- Sudo privileges on the server.

---

## Initial Setup

1. **Update your server:**

   ```bash
   sudo apt update && sudo apt upgrade -y


2. **Install required packages:**
    '''bash
    sudo apt install git python3 python3-venv python3-pip nginx -y

## Cloning the Repository
1. **Navigate to the directory where you want your project:**
    '''bash
    cd /home/django

2. **Clone your repo**
    '''bash
    git clone https://github.com/yourusername/your-django-app.git graceerp

3. **cd graceerp**
    '''bash
    cd graceerp
    
## Python Virtual Environment & Dependencies

1. **Create a Virtual Env:**
    '''bash
    python3 -m venv env

2. **Activate the virtual environment:**
    '''bash
    source env/bin/activate

3. **install your dependencies**
    '''bash
    pip install -r requirements.txt


## Django Configuration

1. **Update settings for production:**
    - In `settings.py` (or your settings module), set:\
    '''bash
    DEBUG = False
    ALLOWED_HOSTS = ['206.189.21.247', 'kreeck.com', 'www.kreeck.com',]

2. **Configure static and media settings:**
    - Ensure your `STATIC_ROOT` and `MEDIA_ROOT` are defined in `settings.py`, for example:
    '''bash
    STATIC_URL = '/static/'
    STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


## Database Setup (SQLite3)
1. **Ensure your SQLite database file (e.g., `db.sqlite3`) is located in the project root, if not make migrations**

2. **Set proper permissions:**
    '''bash
    sudo chown django:django /home/django/graceerp/db.sqlite3
    sudo chmod 664 /home/django/graceerp/db.sqlite3
    sudo chown django:django /home/django/graceerp
    sudo chmod 775 /home/django/graceerp

3. **Run Migrations:**
    '''bash
    python manage.py makemigrations migrate

## Static Files Collection
    '''bash
    python manage.py collectstatic --noinput

## Gunicorn Setup
- Test Gunicorn manually before setting up systemd:

    '''bash
    ./env/bin/gunicorn --bind unix:/home/django/gunicorn.socket graceerp.wsgi:application

- You should see output indicating that Gunicorn is listening on the Unix socket. Press `Ctrl+C` to stop the manual run.

## Systemd Service for Gunicor
- Create or update the service file `/etc/systemd/system/gunicorn.service` with the following content:
    '''bash
    [Unit]
    Description=Gunicorn daemon for graceerp
    After=network.target
    Before=nginx.service

    [Service]
    User=django
    Group=www-data
    WorkingDirectory=/home/django/graceerp
    Environment="PATH=/home/django/graceerp/env/bin"
    ExecStart=/home/django/graceerp/env/bin/gunicorn \
        --name=graceerp \
        --pythonpath=/home/django/graceerp \
        --bind unix:/home/django/gunicorn.socket \
        graceerp.wsgi:application
    Restart=always
    SyslogIdentifier=gunicorn

    [Install]
    WantedBy=multi-user.target

1. **Reload systemd and start the service:**
    '''bash
    sudo systemctl daemon-reload
    sudo systemctl start gunicorn
    sudo systemctl enable gunicorn
    sudo systemctl restart gunicorn
    sudo systemctl restart nginx


2. **Check the status:**
    '''bash
    sudo systemctl status gunicorn


## Nginx Configuration
- Create an Nginx configuration file (e.g., `/etc/nginx/sites-available/graceerp`) with the following content:
    '''bash
    upstream app_server {
        server unix:/home/django/gunicorn.socket fail_timeout=0;
    }

    server {
        listen 80;
        listen [::]:80;
        server_name your_domain.com;  # Replace with your domain or server IP

        client_max_body_size 4G;
        keepalive_timeout 5;

        location /media/ {
            alias /home/django/graceerp/media;
        }

        location /static/ {
            alias /home/django/graceerp/staticfiles;
        }

        location / {
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header Host $host;
            proxy_redirect off;
            proxy_buffering off;
            proxy_pass http://app_server;
        }
    }

1. **Enable the site:**
    '''bash
    sudo ln -s /etc/nginx/sites-available/graceerp /etc/nginx/sites-enabled/

2. **Test and reload NGINX:**
    '''bash
    sudo nginx -t
    sudo systemctl restart nginx


## Permissions and Ownership
- Ensure the Django project and associated files are owned by the appropriate user (e.g., `django`):
    '''bash
    sudo chown -R django:django /home/django/graceerp

- If Nginx (usually running as `www-data`) needs access to static and media files, make sure group permissions are set correctly

## Starting and managing Service
1. **To start/restart gunicorn:**
    '''bash
    sudo systemctl restart gunicorn

2. **To check Gunicorn logs:**
    '''bash
    sudo journalctl -u gunicorn -f

3. **To restart nginx:**
    '''bash
    sudo systemctl restart nginx

## Logging and Troubleshooting
**Django Logging:**
Consider setting up logging in your Django settings to capture errors to a file.

**Gunicorn Logging:**
You can adjust Gunicorn logging options via command-line flags or configuration file if needed.

**Common Errors:**

- **"Attempt to write a readonly database":** Ensure proper file permissions.

- **"502 Bad Gateway":** Check Gunicorn and Nginx configuration, ensure the socket file exists.

- **500 Internal Server Error:** Check Django logs, enable temporary DEBUG mode if safe.

**Manual Testing:**
- You can always run Gunicorn manually to capture errors in real-time:
    '''bash
    cd /home/django/graceerp
    ./env/bin/gunicorn --bind 127.0.0.1:8000 graceerp.wsgi:application

##Final Notes
- **Security:**

- - Disable DEBUG in production.

- - Consider setting up HTTPS using Certbot and Let's Encrypt.

- - Regularly update your server and application dependencies.

**Backups:**
- Regularly backup your database and critical project files.

**Monitoring:**
- Use tools like supervisor, systemd, or external monitoring services to track uptime and performance.