
import base64
import secrets
from datetime import timedelta
from io import BytesIO
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.core.mail import EmailMessage
from mailjet_rest import Client
import logging

# Image processing imports
from PIL import Image, ImageDraw, ImageFont
import qrcode

# PDF generation imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors

logger = logging.getLogger(__name__)


def get_mailjet_client():
    """
    Initialize and return Mailjet client.
    
    Requires MAILJET_API_KEY and MAILJET_SECRET_KEY in settings.
    """
    try:
        api_key = getattr(settings, 'MAILJET_API_KEY', None)
        secret_key = getattr(settings, 'MAILJET_SECRET_KEY', None)
        
        if not api_key or not secret_key:
            raise Exception("Mailjet API credentials not configured in settings")
        
        return Client(auth=(api_key, secret_key), version='v3.1')
    except Exception as e:
        logger.error(f"Failed to initialize Mailjet client: {e}")
        raise


def create_card_delivery(card, delivery_method, recipient_email, recipient_name, **kwargs):
    """
    Create and process card delivery with enhanced error handling.
    """
    delivery = None
    try:
        # Import here to avoid circular imports
        from .models import CardDelivery
        
        logger.info(f"DEBUG: Creating delivery record for {card.card_number}")
        logger.info(f"DEBUG: Delivery data - method: {delivery_method}, email: {recipient_email}, format: {kwargs.get('file_format', 'pdf')}")
        
        # Create delivery record with initial status
        try:
            delivery = CardDelivery.objects.create(
                card=card,
                delivery_type=delivery_method,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                initiated_by=kwargs.get('initiated_by'),
                file_format=kwargs.get('file_format', 'pdf'),
                status='processing',  # Make sure this is 'processing'
                email_subject=kwargs.get('email_subject', ''),
                email_message=kwargs.get('email_message', ''),
                max_downloads=kwargs.get('max_downloads', 5),
            )
            logger.info(f"DEBUG: CardDelivery.objects.create() completed successfully")
        except Exception as create_error:
            logger.error(f"DEBUG: Failed to create CardDelivery object: {create_error}", exc_info=True)
            raise
        
        logger.info(f"DEBUG: Created delivery record {delivery.id} with status: {delivery.status}")
        
        # Refresh from database to ensure we have the latest status
        delivery.refresh_from_db()
        logger.info(f"DEBUG: After refresh_from_db, delivery status: {delivery.status}")
        
        # Process delivery based on method
        logger.info(f"DEBUG: About to process delivery method: {delivery_method}")
        
        try:
            if delivery_method == 'email_pdf':
                logger.info(f"DEBUG: Calling process_email_pdf_delivery")
                process_email_pdf_delivery(delivery, kwargs)
                logger.info(f"DEBUG: process_email_pdf_delivery completed")
            elif delivery_method == 'email_link':
                logger.info(f"DEBUG: Calling process_email_link_delivery")
                process_email_link_delivery(delivery, kwargs)
                logger.info(f"DEBUG: process_email_link_delivery completed")
            elif delivery_method == 'direct_download':
                logger.info(f"DEBUG: Calling process_direct_download_delivery")
                result = process_direct_download_delivery(delivery, kwargs)
                logger.info(f"DEBUG: process_direct_download_delivery completed")
                return result
            else:
                raise ValueError(f"Unsupported delivery method: {delivery_method}")
        except Exception as processing_error:
            logger.error(f"DEBUG: Processing failed with error: {processing_error}", exc_info=True)
            delivery.status = 'failed'
            delivery.failure_reason = str(processing_error)
            delivery.save()
            logger.info(f"DEBUG: Set delivery status to failed: {delivery.status}")
            raise
        
        # Refresh delivery from database to get updated status
        delivery.refresh_from_db()
        logger.info(f"DEBUG: Final delivery status: {delivery.status}")
        
        return delivery
        
    except Exception as e:
        logger.error(f"DEBUG: create_card_delivery failed: {e}", exc_info=True)
        if delivery:
            delivery.status = 'failed'
            delivery.failure_reason = str(e)
            delivery.save()
        raise





    


def process_email_pdf_delivery(delivery, kwargs):
    """
    Process email delivery with PDF attachment using Mailjet.
    """
    logger.info(f"DEBUG: process_email_pdf_delivery started for delivery {delivery.id}")
    
    try:
        card = delivery.card
        logger.info(f"DEBUG: Processing PDF email for card {card.card_number}")
        
        # Generate PDF file
        logger.info(f"DEBUG: About to generate card file")
        file_content, filename, content_type = generate_card_file(card, 'pdf')
        logger.info(f"DEBUG: Generated card file: {filename}, size: {len(file_content)}")
        
        # Set email backend to console for testing
        logger.info(f"DEBUG: Using console email backend for testing")
        
        # For now, let's just simulate successful email sending
        # Comment out the actual email sending and just mark as completed
        
        delivery.status = 'completed'
        delivery.completed_at = timezone.now()
        delivery.delivery_notes = f"PDF attachment would be sent to {delivery.recipient_email} (console mode)"
        delivery.save()
        
        logger.info(f"DEBUG: Set delivery status to completed")
        
        # Print the "email" to console
        print(f"""
        === EMAIL WOULD BE SENT ===
        To: {delivery.recipient_email}
        Subject: Your ACRP Digital Card - {card.card_number}
        Attachment: {filename} ({len(file_content)} bytes)
        ===========================
        """)
        
    except Exception as e:
        logger.error(f"DEBUG: process_email_pdf_delivery failed: {e}", exc_info=True)
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.save()
        raise






def process_email_link_delivery(delivery, kwargs):
    """
    Process email delivery with secure download link.
    
    This function sends an email containing a secure download link
    that allows the recipient to download their card.
    
    Args:
        delivery: CardDelivery instance
        kwargs: Additional parameters from delivery creation
    """
    try:
        card = delivery.card
        request = kwargs.get('request')
        
        logger.info(f"Processing link email delivery for card {card.card_number}")
        
        # Generate secure download token (this is handled in model save method too, but ensure it's set)
        if not delivery.download_token:
            delivery.download_token = secrets.token_urlsafe(32)
            delivery.download_expires_at = timezone.now() + timedelta(days=30)
            delivery.max_downloads = kwargs.get('max_downloads', 5)
            delivery.save()
        
        # Build download URL
        download_path = reverse('affiliationcard:download_card', args=[delivery.download_token])
        if request:
            download_url = request.build_absolute_uri(download_path)
        else:
            # Fallback to settings-based URL construction
            base_url = getattr(settings, 'BASE_URL', 'https://your-domain.com')
            download_url = f"{base_url.rstrip('/')}{download_path}"
        
        # Prepare email context
        context = {
            'card': card,
            'delivery': delivery,
            'recipient_name': delivery.recipient_name,
            'card_number': card.card_number,
            'download_url': download_url,
            'expiry_date': delivery.download_expires_at,
            'max_downloads': delivery.max_downloads,
            'council_name': getattr(card, 'council_name', 'N/A'),
            'affiliation_type': getattr(card, 'affiliation_type', 'N/A').title() if hasattr(card, 'affiliation_type') else 'N/A',
            'current_year': timezone.now().year,
            'system_name': 'ACRP AMS',
        }
        
        # Try to use templates, fallback to simple message if templates don't exist
        try:
            html_content = render_to_string('email_templates/affiliationcard/card_link_delivery.html', context)
            text_content = render_to_string('email_templates/affiliationcard/card_link_delivery.txt', context)
        except:
            # Fallback to simple email content
            html_content = f"""
            <h2>Download Your ACRP Digital Card - {card.card_number}</h2>
            <p>Dear {delivery.recipient_name},</p>
            <p>Your ACRP digital affiliation card is ready for download.</p>
            <p><a href="{download_url}" style="background-color: #1e40af; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Download Your Card</a></p>
            <p><strong>Important:</strong> This download link will expire on {delivery.download_expires_at.strftime('%B %d, %Y')} and can be used up to {delivery.max_downloads} times.</p>
            <p><strong>Card Details:</strong></p>
            <ul>
                <li>Card Number: {card.card_number}</li>
                <li>Council: {context['council_name']}</li>
                <li>Affiliation Type: {context['affiliation_type']}</li>
            </ul>
            <p>If the button doesn't work, copy this link: {download_url}</p>
            <p>Best regards,<br>ACRP Digital Cards Team</p>
            """
            
            text_content = f"""
Download Your ACRP Digital Card - {card.card_number}

Dear {delivery.recipient_name},

Your ACRP digital affiliation card is ready for download.

Download Link: {download_url}

Important: This download link will expire on {delivery.download_expires_at.strftime('%B %d, %Y')} and can be used up to {delivery.max_downloads} times.

Card Details:
- Card Number: {card.card_number}
- Council: {context['council_name']}
- Affiliation Type: {context['affiliation_type']}

Best regards,
ACRP Digital Cards Team
            """
        
        # Send email (try Mailjet first, fallback to Django email)
        try:
            # Try Mailjet first
            mailjet_client = get_mailjet_client()
            
            email_data = {
                'Messages': [{
                    'From': {
                        'Email': getattr(settings, 'DEFAULT_FROM_EMAIL', 'dave@kreeck.com'),
                        'Name': 'ACRP Digital Cards'
                    },
                    'To': [{
                        'Email': delivery.recipient_email,
                        'Name': delivery.recipient_name
                    }],
                    'Subject': kwargs.get('email_subject', f'Download Your ACRP Digital Card - {card.card_number}'),
                    'TextPart': text_content,
                    'HTMLPart': html_content
                }]
            }
            
            result = mailjet_client.send.create(data=email_data)
            
            if result.status_code == 200:
                delivery.status = 'completed'
                delivery.completed_at = timezone.now()
                delivery.delivery_notes = f"Download link sent successfully via Mailjet to {delivery.recipient_email}"
                delivery.mailjet_message_id = result.json()['Messages'][0]['MessageID']
                delivery.save()
                
                logger.info(f"Link email delivery completed via Mailjet for card {card.card_number}")
            else:
                raise Exception(f"Mailjet API error: {result.status_code}")
                
        except Exception as mailjet_error:
            # Fallback to Django email
            logger.warning(f"Mailjet delivery failed, falling back to Django email: {mailjet_error}")
            
            email = EmailMessage(
                subject=kwargs.get('email_subject', f'Download Your ACRP Digital Card - {card.card_number}'),
                body=text_content,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'dave@kreeck.com'),
                to=[delivery.recipient_email]
            )
            
            email.attach_alternative(html_content, "text/html")
            email.send()
            
            delivery.status = 'completed'
            delivery.completed_at = timezone.now()
            delivery.delivery_notes = f"Download link sent successfully via Django email to {delivery.recipient_email}"
            delivery.save()
            
            logger.info(f"Link email delivery completed via Django email for card {card.card_number}")
        
    except Exception as e:
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.error_message = str(e)
        delivery.save()
        
        logger.error(f"Link email delivery failed for card {card.card_number}: {e}")
        raise


def process_direct_download_delivery(delivery, kwargs):
    """
    Process direct download generation with proper error handling.
    """
    try:
        card = delivery.card
        
        logger.info(f"Processing direct download for card {card.card_number}")
        
        # Generate download token for tracking
        if not delivery.download_token:
            delivery.download_token = secrets.token_urlsafe(32)
            delivery.download_expires_at = timezone.now() + timedelta(hours=24)
            delivery.max_downloads = 1
            delivery.save()
        
        # Update delivery status to ready
        delivery.status = 'ready_for_download'
        delivery.completed_at = timezone.now()
        delivery.delivery_notes = f"Direct download prepared for {card.card_number}"
        delivery.save()
        
        logger.info(f"Direct download delivery prepared for card {card.card_number}, token: {delivery.download_token}")
        
        return delivery
        
    except Exception as e:
        logger.error(f"Direct download delivery failed for card {card.card_number}: {e}", exc_info=True)
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.save()
        raise





def generate_card_file(card, file_format):
    """Generate card file in specified format with proper error handling."""
    logger.info(f"DEBUG: generate_card_file called with format: {file_format}")
    
    try:
        if file_format.lower() == 'pdf':
            logger.info("DEBUG: Calling generate_card_pdf")
            # Import the updated function from views
            from .views import generate_card_pdf as views_generate_card_pdf
            return views_generate_card_pdf(card)
        elif file_format.lower() in ['png', 'PNG']:
            logger.info("DEBUG: Calling generate_card_image for PNG")
            from .views import generate_card_image as views_generate_card_image
            return views_generate_card_image(card, 'PNG')
        elif file_format.lower() in ['jpg', 'jpeg', 'JPG', 'JPEG']:
            logger.info("DEBUG: Calling generate_card_image for JPEG")
            from .views import generate_card_image as views_generate_card_image
            return views_generate_card_image(card, 'JPEG')
        else:
            raise ValueError(f"Unsupported file format: {file_format}")
    except Exception as e:
        logger.error(f"ERROR in generate_card_file: {e}", exc_info=True)
       