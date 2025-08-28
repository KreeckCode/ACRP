# ACRP CI/CD Pipeline Setup Guide

This guide walks you through setting up a complete CI/CD pipeline for your ACRP Django application on Digital Ocean using GitHub Actions.

## Overview
We'll create a pipeline that:
- Runs tests on every push and pull request
- Automatically deploys to production when code is pushed to the main branch
- Uses SSH for secure server communication
- Handles Django-specific tasks (migrations, static files, service restarts)

---

## Step 1: Generate SSH Keys on Your MacBook M4

### 1.1 Open Terminal and Navigate to Your Project
```bash
cd ~/path/to/your/acrp/project
```

### 1.2 Generate SSH Key Pair
```bash
# Generate a new SSH key specifically for deployment
# -t ed25519: Use modern Ed25519 algorithm (more secure and faster)
# -C: Add a comment to identify the key
ssh-keygen -t ed25519 -C "acrp-github-deploy-key" -f ~/.ssh/acrp_deploy_key

# When prompted for passphrase, press Enter twice (no passphrase for automation)
```

**Why Ed25519?** It's more secure than RSA, has smaller key sizes, and better performance - perfect for automated deployments.

### 1.3 Verify Key Generation
```bash
# Check if keys were created successfully
ls -la ~/.ssh/acrp_deploy_key*

# You should see:
# ~/.ssh/acrp_deploy_key     (private key - keep this secret!)
# ~/.ssh/acrp_deploy_key.pub (public key - this goes on the server)
```

### 1.4 Display the Public Key (for server setup)
```bash
# Display the public key - you'll need this for the server
cat ~/.ssh/acrp_deploy_key.pub
```

**Save this output!** You'll need to add this public key to your Digital Ocean server.

---

## Step 2: Configure Your Digital Ocean Server

### 2.1 Connect to Your Digital Ocean Droplet
```bash
# Replace YOUR_SERVER_IP with your actual server IP
ssh root@YOUR_SERVER_IP
```

### 2.2 Create a Deployment User (Recommended Security Practice)
```bash
# Create a dedicated user for deployments (better than using root)
adduser acrp-deploy

# Add user to sudo group for system commands
usermod -aG sudo acrp-deploy

# Switch to the new user
su - acrp-deploy
```

**Why create a separate user?** It follows the principle of least privilege - the deployment process only gets the permissions it needs.

### 2.3 Set Up SSH Key Authentication
```bash
# Create SSH directory for the deployment user
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Create authorized_keys file and add your public key
nano ~/.ssh/authorized_keys
```

**In the nano editor:**
1. Paste the public key you copied from `cat ~/.ssh/acrp_deploy_key.pub`
2. Press `Ctrl + X`, then `Y`, then `Enter` to save

```bash
# Set proper permissions
chmod 600 ~/.ssh/authorized_keys
```

### 2.4 Configure Your Django Project Directory
```bash
# Navigate to where your app should be located
cd /var/www

# If ACRP directory doesn't exist, create it
sudo mkdir -p acrp
sudo chown acrp-deploy:acrp-deploy acrp
cd acrp

# If your code isn't already here, clone it
git clone https://github.com/YOUR_USERNAME/acrp.git .

# Set up Python virtual environment
python3 -m venv env
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2.5 Test SSH Connection from Your Mac
```bash
# From your MacBook, test the connection
ssh -i ~/.ssh/acrp_deploy_key acrp-deploy@YOUR_SERVER_IP

# If successful, you should connect without password
# Exit the connection
exit
```

---

## Step 3: Create GitHub Actions Workflow

### 3.1 Create Workflow Directory in Your ACRP Project
```bash
# From your MacBook, in your ACRP project root
mkdir -p .github/workflows
```

### 3.2 Create the CI/CD Workflow File
Create `.github/workflows/deploy.yml` with the following content:

```yaml
name: ACRP CI/CD Pipeline

# Trigger conditions
on:
  push:
    branches: [ main ]  # Deploy on push to main
  pull_request:
    branches: [ main ]  # Run tests on PRs

# Environment variables
env:
  PYTHON_VERSION: 3.11

jobs:
  # Test Job - runs on all pushes and PRs
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}
        cache: 'pip'  # Cache pip dependencies for faster builds
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run Django system checks
      run: |
        python manage.py check --deploy
      env:
        # Django Core Settings
        SECRET_KEY: test-secret-key-for-github-actions-very-long-and-secure
        DEBUG: False
        ENVIRONMENT: testing
        
        # Database Configuration (mock values for testing)
        DB_NAME: test_db
        DB_USER: test_user
        DB_PASS: test_password
        DB_PASSWORD: test_password
        DB_HOST: localhost
        DB_PORT: 5432
        DB_SSLMODE: disable
        DB_CONN_MAX_AGE: 0
        DB_CONN_HEALTH_CHECKS: False
        DB_ATOMIC_REQUESTS: False
        
        # Email Configuration (mock values for CI)
        EMAIL_HOST: localhost
        EMAIL_HOST_USER: test@example.com
        EMAIL_HOST_PASSWORD: test_password
        EMAIL_PORT: 587
        DEFAULT_FROM_EMAIL: test@example.com
        EMAIL_USE_SSL: False
        EMAIL_USE_TLS: False
        
        # AWS Configuration (mock values)
        AWS_ACCESS_KEY_ID: test_key
        AWS_SECRET_ACCESS_KEY: test_secret
        AWS_STORAGE_BUCKET_NAME: test_bucket
        AWS_S3_REGION_NAME: us-east-1
        
        # Digital Ocean Spaces (mock values)
        DO_SPACES_ACCESS_KEY_ID: test_key
        DO_SPACES_SECRET_ACCESS_KEY: test_secret
        DO_SPACES_BUCKET_NAME: test_bucket
        DO_SPACES_REGION: nyc3
        DO_SPACES_ENDPOINT_URL: https://test.digitaloceanspaces.com
        DO_SPACES_CDN_DOMAIN: test.cdn.digitaloceanspaces.com
        
        # Security Settings
        SECURE_SSL_REDIRECT: False
        ALLOWED_HOSTS: localhost,127.0.0.1
        
        # Other Configuration
        NGINX_CONF: nginx.test.conf
    
    - name: Run Django Tests
      run: |
        python manage.py test --verbosity=2
      env:
        # Reuse the same environment variables from system checks
        SECRET_KEY: test-secret-key-for-github-actions-very-long-and-secure
        DEBUG: False
        ENVIRONMENT: testing
        DB_NAME: test_db
        DB_USER: test_user
        DB_PASS: test_password
        DB_PASSWORD: test_password
        DB_HOST: localhost
        DB_PORT: 5432
        DB_SSLMODE: disable
        DB_CONN_MAX_AGE: 0
        DB_CONN_HEALTH_CHECKS: False
        DB_ATOMIC_REQUESTS: False
        EMAIL_HOST: localhost
        EMAIL_HOST_USER: test@example.com
        EMAIL_HOST_PASSWORD: test_password
        EMAIL_PORT: 587
        DEFAULT_FROM_EMAIL: test@example.com
        EMAIL_USE_SSL: False
        EMAIL_USE_TLS: False
        AWS_ACCESS_KEY_ID: test_key
        AWS_SECRET_ACCESS_KEY: test_secret
        AWS_STORAGE_BUCKET_NAME: test_bucket
        AWS_S3_REGION_NAME: us-east-1
        DO_SPACES_ACCESS_KEY_ID: test_key
        DO_SPACES_SECRET_ACCESS_KEY: test_secret
        DO_SPACES_BUCKET_NAME: test_bucket
        DO_SPACES_REGION: nyc3
        DO_SPACES_ENDPOINT_URL: https://test.digitaloceanspaces.com
        DO_SPACES_CDN_DOMAIN: test.cdn.digitaloceanspaces.com
        SECURE_SSL_REDIRECT: False
        ALLOWED_HOSTS: localhost,127.0.0.1
        NGINX_CONF: nginx.test.conf

  # Deploy Job - only runs on successful push to main
  deploy:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: test  # Only deploy if tests pass
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Setup SSH Agent
      run: |
        # Start SSH agent and add our deployment key
        eval $(ssh-agent -s)
        mkdir -p ~/.ssh
        echo "${{ secrets.DEPLOY_SSH_KEY }}" > ~/.ssh/deploy_key
        chmod 600 ~/.ssh/deploy_key
        ssh-add ~/.ssh/deploy_key
        
        # Add server to known hosts to prevent interactive prompts
        ssh-keyscan -H ${{ secrets.DEPLOY_HOST }} >> ~/.ssh/known_hosts
    
    - name: Deploy to Digital Ocean Server
      run: |
        ssh -i ~/.ssh/deploy_key ${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }} '
          # Navigate to project directory
          cd /var/www/acrp &&
          
          # Pull latest code from main branch
          git pull origin main &&
          
          # Activate virtual environment
          source env/bin/activate &&
          
          # Install/update Python dependencies
          pip install -r requirements.txt &&
          
          # Run Django database migrations
          python manage.py migrate --noinput &&
          
          # Collect static files for production
          python manage.py collectstatic --noinput &&
          
          # Restart the Django application service
          sudo systemctl restart acrp &&
          
          # Reload Nginx to pick up any configuration changes
          sudo systemctl reload nginx
        '
    
    - name: Deployment Status Notification
      if: always()  # Run whether deployment succeeded or failed
      run: |
        if [ ${{ job.status }} = "success" ]; then
          echo "✅ ACRP deployment successful!"
        else
          echo "❌ ACRP deployment failed!"
          exit 1
        fi
```

---

## Step 4: Configure GitHub Repository Secrets

### 4.1 Add SSH Private Key to GitHub Secrets
1. Go to your GitHub repository: `https://github.com/YOUR_USERNAME/acrp`
2. Click on **Settings** tab
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**

**Add these secrets:**

#### DEPLOY_SSH_KEY
```bash
# From your MacBook, copy the private key content
cat ~/.ssh/acrp_deploy_key
```
- Name: `DEPLOY_SSH_KEY`
- Value: Paste the entire private key content (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)

#### DEPLOY_HOST
- Name: `DEPLOY_HOST`
- Value: Your Digital Ocean server IP address (e.g., `64.225.123.456`)

#### DEPLOY_USER
- Name: `DEPLOY_USER`
- Value: `acrp-deploy`

---

## Step 5: Configure Your Digital Ocean Server for CI/CD

### 5.1 Set Up Systemd Service for Your Django App

SSH into your server and create a systemd service file:

```bash
# Connect to your server
ssh -i ~/.ssh/acrp_deploy_key acrp-deploy@YOUR_SERVER_IP

# Create systemd service file
sudo nano /etc/systemd/system/acrp.service
```

**Add this content to the service file:**

```ini
[Unit]
Description=ACRP Django Application
After=network.target

[Service]
Type=notify
User=acrp-deploy
Group=acrp-deploy
WorkingDirectory=/var/www/acrp
Environment=PATH=/var/www/acrp/env/bin
ExecStart=/var/www/acrp/env/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 acrp.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**Why this configuration?**
- `Type=notify`: Allows systemd to know when the service is ready
- `User/Group=acrp-deploy`: Runs as our deployment user for security
- `WorkingDirectory`: Sets the correct project directory
- `Environment=PATH`: Ensures the virtual environment Python is used
- `ExecStart`: Runs Gunicorn with 3 workers on localhost:8000
- `Restart=always`: Automatically restarts if the service crashes

### 5.2 Enable and Start the Service
```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable acrp

# Start the service
sudo systemctl start acrp

# Check service status
sudo systemctl status acrp
```

### 5.3 Configure Nginx for Your ACRP Application
```bash
# Create Nginx configuration for ACRP
sudo nano /etc/nginx/sites-available/acrp
```

**Add this Nginx configuration:**

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN.com www.YOUR_DOMAIN.com;  # Replace with your actual domain
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Static files - served directly by Nginx for better performance
    location /static/ {
        alias /var/www/acrp/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files - user-uploaded content
    location /media/ {
        alias /var/www/acrp/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
    
    # Proxy all other requests to Django via Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 5.4 Enable the Nginx Site
```bash
# Create symbolic link to enable the site
sudo ln -s /etc/nginx/sites-available/acrp /etc/nginx/sites-enabled/

# Test Nginx configuration
sudo nginx -t

# If test passes, reload Nginx
sudo systemctl reload nginx
```

### 5.5 Configure Django Settings for Production

Ensure your Django `settings.py` can handle environment variables:

```python
# In your settings.py, add/modify these sections:

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-fallback-secret-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')

# Database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'acrp_db'),
        'USER': os.environ.get('DB_USER', 'acrp_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'your_db_password'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media files configuration  
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

---

## Step 6: Set Up Environment Variables on Server

### 6.1 Create Environment File
```bash
# SSH into your server
ssh -i ~/.ssh/acrp_deploy_key acrp-deploy@YOUR_SERVER_IP

# Create environment file for production
sudo nano /var/www/acrp/.env
```

**Add your production environment variables:**

```bash
# Django Core Configuration
SECRET_KEY=your-super-secret-production-key-here
DEBUG=False
ENVIRONMENT=production
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,YOUR_SERVER_IP

# Database Configuration
DB_NAME=acrp_production_db
DB_USER=acrp_db_user
DB_PASSWORD=your-secure-db-password
DB_HOST=localhost
DB_PORT=5432

# Email Configuration (configure with your email provider)
EMAIL_HOST=smtp.your-email-provider.com
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-email-password
EMAIL_PORT=587
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@your-domain.com

# Additional configurations as needed...
```

### 6.2 Load Environment Variables in Systemd Service

Update your systemd service to load environment variables:

```bash
sudo nano /etc/systemd/system/acrp.service
```

**Modify the service file to include:**

```ini
[Unit]
Description=ACRP Django Application
After=network.target

[Service]
Type=notify
User=acrp-deploy
Group=acrp-deploy
WorkingDirectory=/var/www/acrp
Environment=PATH=/var/www/acrp/env/bin
EnvironmentFile=/var/www/acrp/.env
ExecStart=/var/www/acrp/env/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 acrp.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
# Reload and restart the service
sudo systemctl daemon-reload
sudo systemctl restart acrp
sudo systemctl status acrp
```

---

## Step 7: Grant Deployment User Necessary Permissions

### 7.1 Configure Sudo Permissions for Deployment
```bash
# Edit sudoers file safely
sudo visudo
```

**Add this line at the end:**
```bash
# Allow acrp-deploy to restart services without password
acrp-deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart acrp, /bin/systemctl reload nginx, /bin/systemctl status acrp
```

**Why this approach?** It allows GitHub Actions to restart services without needing a password, while limiting permissions to only the necessary commands.

---

## Step 8: Test Your CI/CD Pipeline

### 8.1 Commit and Push Your Workflow
```bash
# From your MacBook, in your ACRP project
git add .github/workflows/deploy.yml
git commit -m "Add CI/CD pipeline with GitHub Actions"
git push origin main
```

### 8.2 Monitor the Deployment
1. Go to your GitHub repository
2. Click on the **Actions** tab
3. You should see your workflow running
4. Click on the workflow run to see detailed logs

### 8.3 Verify Deployment on Server
```bash
# Check if your application is running
curl http://YOUR_SERVER_IP

# Check service status
ssh -i ~/.ssh/acrp_deploy_key acrp-deploy@YOUR_SERVER_IP 'sudo systemctl status acrp'
```

---

## Step 9: Security Best Practices & Troubleshooting

### 9.1 Security Recommendations
- **Firewall Configuration**: Only allow necessary ports (22 for SSH, 80/443 for HTTP/HTTPS)
- **SSH Key Rotation**: Regularly rotate your SSH keys
- **Environment Variables**: Never commit sensitive data to your repository
- **User Permissions**: The deployment user should have minimal necessary permissions

### 9.2 Common Issues and Solutions

**Issue: Permission Denied when restarting services**
```bash
# Solution: Check sudoers configuration
sudo visudo
# Ensure the acrp-deploy user has the correct permissions
```

**Issue: SSH connection fails**
```bash
# Debug SSH connection
ssh -v -i ~/.ssh/acrp_deploy_key acrp-deploy@YOUR_SERVER_IP
# The -v flag provides verbose output to help diagnose issues
```

**Issue: Django tests fail in CI**
```bash
# Ensure your Django app can run with the test environment variables
# Check that all required environment variables are set in the workflow
```

### 9.3 Monitoring and Logs
```bash
# View Django application logs
sudo journalctl -u acrp -f

# View Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

---

## Step 10: Next Steps and Enhancements

Once your basic CI/CD pipeline is working, consider these improvements:

### 10.1 Add Database Backups to Deployment
```yaml
# Add this step before migrations in your GitHub workflow
- name: Backup Database
  run: |
    ssh -i ~/.ssh/deploy_key ${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }} '
      cd /var/www/acrp &&
      source env/bin/activate &&
      python manage.py dbbackup
    '
```

### 10.2 Add Health Checks
```yaml
# Add this step after deployment
- name: Health Check
  run: |
    sleep 10  # Wait for service to restart
    curl -f http://${{ secrets.DEPLOY_HOST }} || exit 1
```

### 10.3 Add Slack/Discord Notifications
```yaml
# Add notification step at the end
- name: Notify Deployment Status
  if: always()
  # Configure with your preferred notification service
```

---

## Summary

You now have a complete CI/CD pipeline that:

1. **Automatically tests** your Django application on every push and PR
2. **Securely deploys** to your Digital Ocean server when code is pushed to main
3. **Handles Django-specific tasks** like migrations and static file collection
4. **Follows security best practices** with dedicated deployment user and SSH keys
5. **Provides monitoring** and error handling

The pipeline ensures that only tested, working code reaches your production server, and automates the entire deployment process for faster, more reliable releases.

**Key Files Created:**
- `.github/workflows/deploy.yml` - GitHub Actions workflow
- `/etc/systemd/system/acrp.service` - Systemd service file
- `/etc/nginx/sites-available/acrp` - Nginx configuration
- `~/.ssh/acrp_deploy_key` - SSH deployment keys

**Remember:** Always test your pipeline with a small, non-critical change first to ensure everything works correctly before deploying important updates.