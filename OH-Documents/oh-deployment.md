
# Operational Handbook: Deploying Django with Gunicorn and Nginx

This handbook explains how to deploy your Django project using Gunicorn and Nginx, as well as how to configure your Namecheap domain and automate deployment.

---

1. Setting Up Gunicorn as a Systemd Service

## - Create the service file:
    '''bash
    sudo nano /etc/systemd/system/gunicorn.service

  Example content:
    '''bash
    [Unit]
    Description=gunicorn daemon for YourDjangoApp
    After=network.target

    [Service]
    User=root
    Group=www-data
    WorkingDirectory=/root/graceerp
    ExecStart=/root/graceerp/env/bin/gunicorn --workers 3 --bind unix:/root/graceerp/gunicorn.sock graceerp.wsgi:application

    [Install]
    WantedBy=multi-user.target

## - Reload systemd and start the service:
    '''bash
    sudo systemctl daemon-reload
    sudo systemctl start gunicorn
    sudo systemctl enable gunicorn
    sudo systemctl restart gunicorn

---

2. Configuring Nginx as a Reverse Proxy

## - Create an Nginx config file:
    '''bash
    sudo nano /etc/nginx/sites-available/graceerp

  Example configuration:
    '''bash
    server {
        listen 80;
        server_name yourdomain.com www.yourdomain.com;

        location /static/ {
            alias /root/graceerp/static/;
        }

        location / {
            proxy_pass http://unix:/root/graceerp/gunicorn.sock;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }

## - Enable the config and restart Nginx:
    '''bash
    sudo ln -s /etc/nginx/sites-available/graceerp /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl restart nginx

---

3. Updating Namecheap Domain DNS Records

## - Log in to Namecheap and go to Advanced DNS for your domain.
## - Add the following A Records:
  - Host: @ → IP: your server IP
  - Host: www → IP: your server IP

---

4. Creating a Deployment Script and Alias

## - Create a script called deploy.sh:
    '''bash
    #!/bin/bash
    sudo systemctl daemon-reload
    sudo systemctl start gunicorn
    sudo systemctl enable gunicorn
    sudo systemctl restart gunicorn
    sudo systemctl restart nginx

## - Make it executable:
    '''bash
    chmod +x deploy.sh

## - Add an alias to `.bashrc` or `.zshrc`:
    '''bash
    alias deploy='/root/deploy.sh'

  Then run:
    '''bash
    source ~/.bashrc

Now you can just run deploy to start and restart services.

---

5. Viewing Logs and Debugging

## - Gunicorn logs:
    '''bash
    sudo journalctl -u gunicorn -f

## - Nginx error logs:
    '''bash
    sudo tail -f /var/log/nginx/error.log

