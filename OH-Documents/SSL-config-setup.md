# SSL Certificate Setup for ACRP Nginx Configuration

# Step 1: Create the SSL directory structure for nginx
sudo mkdir -p /etc/nginx/ssl/kreeck.com

# Step 2: Copy the private key to the correct location
sudo cp /home/django/ssl_certs/kreeck.key /etc/nginx/ssl/kreeck.com/private.key

# Step 3: Create the fullchain certificate by combining certificate + CA bundle
# This combines your domain certificate with the intermediate certificates
sudo cat /home/django/ssl_certs/kreeck_com.crt /home/django/ssl_certs/kreeck_com.ca-bundle > /tmp/fullchain.crt
sudo mv /tmp/fullchain.crt /etc/nginx/ssl/kreeck.com/fullchain.crt

# Step 4: Set proper ownership and permissions for security
# Nginx needs to read these files, but they should be secure
sudo chown root:root /etc/nginx/ssl/kreeck.com/private.key
sudo chown root:root /etc/nginx/ssl/kreeck.com/fullchain.crt

# Set restrictive permissions (read-only for root on private key, readable by nginx group on certificate)
sudo chmod 600 /etc/nginx/ssl/kreeck.com/private.key  # Only root can read the private key
sudo chmod 644 /etc/nginx/ssl/kreeck.com/fullchain.crt  # Nginx can read the certificate

# Step 5: Verify the certificate files are in the right place and have correct permissions
echo "=== SSL Certificate Files ==="
sudo ls -la /etc/nginx/ssl/kreeck.com/

# Step 6: Test the SSL certificate validity (optional but recommended)
echo "=== Testing Certificate Validity ==="
sudo openssl x509 -in /etc/nginx/ssl/kreeck.com/fullchain.crt -text -noout | grep -E "(Subject:|Issuer:|Not After)"

# Step 7: Test nginx configuration to ensure SSL setup is correct
echo "=== Testing Nginx Configuration ==="
sudo nginx -t

# Step 8: If nginx test passes, reload nginx to apply the SSL certificates
if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration test passed. Reloading nginx..."
    sudo systemctl reload nginx
    echo "✅ Nginx reloaded successfully!"
    
    # Test SSL connection
    echo "=== Testing SSL Connection ==="
    echo "Testing SSL certificate on your domains..."
    curl -I https://kreeck.com 2>/dev/null | head -1
    curl -I https://acrp.org.za 2>/dev/null | head -1
else
    echo "❌ Nginx configuration test failed. Please check the error messages above."
    echo "SSL certificates were copied but nginx configuration has issues."
fi

# Step 9: Check nginx SSL status
echo "=== Nginx SSL Status ==="
sudo systemctl status nginx --no-pager -l