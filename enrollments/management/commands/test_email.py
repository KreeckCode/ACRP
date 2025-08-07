# enrollments/management/commands/test_email.py
"""
Django management command to test email configuration.

Usage:
    python manage.py test_email --to recipient@example.com
    python manage.py test_email --to recipient@example.com --subject "Custom Subject"
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings
import socket


class Command(BaseCommand):
    """
    Management command to test Django email configuration.
    
    This command sends a test email to verify that your SMTP settings
    are correctly configured and working.
    """
    
    help = 'Send a test email to verify email configuration'
    
    def add_arguments(self, parser):
        """
        Define command line arguments for the test email command.
        
        Arguments:
            --to: Email address to send test email to (required)
            --subject: Custom subject line (optional)
        """
        parser.add_argument(
            '--to',
            type=str,
            required=True,
            help='Email address to send test email to'
        )
        
        parser.add_argument(
            '--subject',
            type=str,
            default='ACRP Email Configuration Test',
            help='Subject line for the test email'
        )
    
    def handle(self, *args, **options):
        """
        Main command logic - sends the test email and reports results.
        
        This method:
        1. Validates the email configuration
        2. Attempts to send a test email
        3. Provides detailed feedback on success/failure
        """
        
        to_email = options['to']
        subject = options['subject']
        
        # Display current email configuration
        self.stdout.write(
            self.style.HTTP_INFO('📧 Current Email Configuration:')
        )
        self.stdout.write(f"  Backend: {settings.EMAIL_BACKEND}")
        
        if hasattr(settings, 'EMAIL_HOST'):
            self.stdout.write(f"  Host: {settings.EMAIL_HOST}")
            self.stdout.write(f"  Port: {settings.EMAIL_PORT}")
            self.stdout.write(f"  TLS: {getattr(settings, 'EMAIL_USE_TLS', False)}")
            self.stdout.write(f"  SSL: {getattr(settings, 'EMAIL_USE_SSL', False)}")
            self.stdout.write(f"  User: {getattr(settings, 'EMAIL_HOST_USER', 'Not set')}")
        
        self.stdout.write(f"  From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write('')
        
        # Create email content
        message_body = f"""
Hello!

This is a test email from your ACRP Django application.

Email Configuration Details:
- Backend: {settings.EMAIL_BACKEND}
- From Address: {settings.DEFAULT_FROM_EMAIL}
- Timestamp: {socket.gethostname()} at {__import__('datetime').datetime.now()}

If you received this email, your Django email configuration is working correctly! 🎉

Best regards,
ACRP System
        """.strip()
        
        try:
            # Attempt to send the email
            self.stdout.write(f"📤 Attempting to send test email to: {to_email}")
            
            send_mail(
                subject=subject,
                message=message_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                fail_silently=False,  # Raise exceptions on error
            )
            
            # Success message
            self.stdout.write(
                self.style.SUCCESS(f'✅ Email sent successfully to {to_email}!')
            )
            self.stdout.write(
                self.style.SUCCESS('🎉 Your email configuration is working correctly.')
            )
            
        except Exception as e:
            # Detailed error reporting
            self.stdout.write(
                self.style.ERROR(f'❌ Email sending failed: {str(e)}')
            )
            
            # Provide troubleshooting hints based on error type
            error_str = str(e).lower()
            
            if 'connection refused' in error_str or 'network' in error_str:
                self.stdout.write(
                    self.style.WARNING('💡 Possible causes:')
                )
                self.stdout.write('   • Wrong EMAIL_HOST or EMAIL_PORT')
                self.stdout.write('   • Firewall blocking SMTP ports')
                self.stdout.write('   • SMTP server not accessible')
                
            elif 'authentication' in error_str or 'login' in error_str:
                self.stdout.write(
                    self.style.WARNING('💡 Possible causes:')
                )
                self.stdout.write('   • Wrong EMAIL_HOST_USER or EMAIL_HOST_PASSWORD')
                self.stdout.write('   • Need to use App Password (Gmail/Google Workspace)')
                self.stdout.write('   • Two-factor authentication blocking access')
                
            elif 'tls' in error_str or 'ssl' in error_str:
                self.stdout.write(
                    self.style.WARNING('💡 Possible causes:')
                )
                self.stdout.write('   • Wrong TLS/SSL configuration')
                self.stdout.write('   • Try EMAIL_USE_TLS=True, EMAIL_USE_SSL=False for port 587')
                self.stdout.write('   • Try EMAIL_USE_TLS=False, EMAIL_USE_SSL=True for port 465')
            
            raise CommandError(f'Email test failed: {e}')
