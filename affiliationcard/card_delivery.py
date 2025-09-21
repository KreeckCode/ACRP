# Card_delivery.py


import base64
import secrets
from datetime import timedelta
from io import BytesIO
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.core.mail import EmailMessage, EmailMultiAlternatives
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


def create_card_delivery(card, delivery_method, recipient_email, recipient_name, **kwargs):
    """
    Create and process card delivery with enhanced error handling and debugging.
    
    Args:
        card: AffiliationCard instance
        delivery_method: String - 'email_pdf', 'email_link', or 'direct_download'
        recipient_email: String - recipient's email address
        recipient_name: String - recipient's full name
        **kwargs: Additional parameters
    
    Returns:
        CardDelivery instance
    """
    delivery = None
    try:
        # Import here to avoid circular imports
        from .models import CardDelivery
        
        logger.info(f"=== STARTING CARD DELIVERY CREATION ===")
        logger.info(f"Card: {card.card_number}")
        logger.info(f"Method: {delivery_method}")
        logger.info(f"Recipient: {recipient_email}")
        logger.info(f"Format: {kwargs.get('file_format', 'pdf')}")
        
        # Create delivery record
        delivery = CardDelivery.objects.create(
            card=card,
            delivery_type=delivery_method,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            initiated_by=kwargs.get('initiated_by'),
            file_format=kwargs.get('file_format', 'pdf'),
            status='processing',  # Start with processing
            email_subject=kwargs.get('email_subject', ''),
            email_message=kwargs.get('email_message', ''),
            max_downloads=kwargs.get('max_downloads', 5),
        )
        
        logger.info(f"✓ Created delivery record {delivery.id} with status: {delivery.status}")
        
        # Process delivery immediately
        try:
            if delivery_method == 'email_pdf':
                logger.info("→ Processing email PDF delivery")
                process_email_pdf_delivery(delivery, kwargs)
                
            elif delivery_method == 'email_link':
                logger.info("→ Processing email link delivery")
                process_email_link_delivery(delivery, kwargs)
                
            elif delivery_method == 'direct_download':
                logger.info("→ Processing direct download")
                return process_direct_download_delivery(delivery, kwargs)
                
            else:
                raise ValueError(f"Unsupported delivery method: {delivery_method}")
                
        except Exception as processing_error:
            logger.error(f"✗ Processing failed: {processing_error}")
            delivery.status = 'failed'
            delivery.failure_reason = str(processing_error)
            delivery.save()
            raise
        
        # Refresh and return
        delivery.refresh_from_db()
        logger.info(f"=== DELIVERY CREATION COMPLETE ===")
        logger.info(f"Final status: {delivery.status}")
        
        return delivery
        
    except Exception as e:
        logger.error(f"✗ DELIVERY CREATION FAILED: {e}")
        if delivery:
            delivery.status = 'failed'
            delivery.failure_reason = str(e)
            delivery.save()
        raise


def process_email_pdf_delivery(delivery, kwargs):
    """
    Process email delivery with PDF attachment - USING STYLED PDF GENERATOR
    """
    try:
        card = delivery.card
        logger.info(f"Starting PDF email delivery for {card.card_number}")
        logger.info(f"Delivery ID: {delivery.id}, Status: {delivery.status}")
        
        # Update status to processing
        delivery.status = 'processing'
        delivery.save()
        logger.info("Updated status to processing")
        
        # Generate STYLED PDF file using the views function
        logger.info("Generating STYLED PDF using views.generate_card_pdf...")
        try:
            # Import and use the styled PDF generator from views
            from .views import generate_card_pdf
            file_content, filename, content_type = generate_card_pdf(card)
            logger.info(f"STYLED PDF generated: {filename} ({len(file_content)} bytes)")
        except Exception as pdf_error:
            logger.warning(f"Styled PDF generation failed: {pdf_error}, falling back to simple PDF")
            # Fallback to simple PDF if styled version fails
            file_content, filename, content_type = generate_card_file_simple(card, 'pdf')
            logger.info(f"Simple PDF fallback generated: {filename} ({len(file_content)} bytes)")
        
        # Prepare email context for template
        logger.info("Preparing email context for professional template...")
        context = {
            'card': card,
            'delivery': delivery,
            'recipient_name': delivery.recipient_name,
            'card_number': card.card_number,
            'council_name': getattr(card, 'council_name', 'N/A'),
            'affiliation_type': getattr(card, 'affiliation_type', 'N/A').title() if hasattr(card, 'affiliation_type') else 'N/A',
            'current_year': timezone.now().year,
            'system_name': 'ACRP AMS',
        }
        
        # Use professional email template (with fallback)
        subject = kwargs.get('email_subject', f'Your ACRP Digital Card - {card.card_number}')
        
        try:
            # Try to use the professional email template
            logger.info("Attempting to use card_pdf_delivery.html template...")
            html_content = render_to_string('email_templates/affiliationcard/card_pdf_delivery.html', context)
            logger.info("Successfully used professional email template")
            
            # Also try to get text version
            try:
                text_content = render_to_string('email_templates/affiliationcard/card_pdf_delivery.txt', context)
                logger.info("Successfully used professional text template")
            except:
                # Fallback text content if text template doesn't exist
                text_content = f"""Dear {delivery.recipient_name},

Your ACRP digital affiliation card is attached to this email as a PDF document.

Card Details:
- Card Number: {card.card_number}
- Council: {context['council_name']}
- Affiliation Type: {context['affiliation_type']}
- Status: {card.get_status_display()}

Please save this card to your device and present it when required for verification of your professional standing.

Thank you for your continued commitment to excellence in ministry.

Best regards,
ACRP Administration Team"""
                logger.info("Used fallback text content")
                
        except Exception as template_error:
            # Fallback to simple email content if template fails
            logger.warning(f"Professional email template failed: {template_error}, using simple content")
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Your ACRP Digital Card</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #1e40af;">Your ACRP Digital Card</h1>
                    
                    <p>Dear {delivery.recipient_name},</p>
                    
                    <p>Your ACRP digital affiliation card is attached to this email as a PDF document.</p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #1e40af; margin: 20px 0;">
                        <h3 style="margin: 0 0 10px 0;">Card Details</h3>
                        <p style="margin: 0;"><strong>Card Number:</strong> {card.card_number}</p>
                        <p style="margin: 0;"><strong>Council:</strong> {context['council_name']}</p>
                        <p style="margin: 0;"><strong>Affiliation Type:</strong> {context['affiliation_type']}</p>
                        <p style="margin: 0;"><strong>Status:</strong> {card.get_status_display()}</p>
                    </div>
                    
                    <p>Please save this card to your device and present it when required for verification.</p>
                    
                    <p>Best regards,<br>The ACRP Team</p>
                </div>
            </body>
            </html>
            """
            
            text_content = f"""Dear {delivery.recipient_name},

Your ACRP digital affiliation card is attached as a PDF.

Card Number: {card.card_number}
Status: {card.get_status_display()}

Best regards,
The ACRP Team"""
        
        logger.info("Email content prepared")
        
        # Create and send email using Django's EmailMultiAlternatives
        logger.info("Creating email message...")
        
        from django.core.mail import EmailMultiAlternatives
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'ams@acrp.org.za'),
            to=[delivery.recipient_email],
            reply_to=[getattr(settings, 'DEFAULT_FROM_EMAIL', 'ams@acrp.org.za')]
        )
        
        # Add HTML version
        email.attach_alternative(html_content, "text/html")
        
        # Attach the STYLED PDF
        email.attach(filename, file_content, content_type)
        
        logger.info(f"Sending email to {delivery.recipient_email}...")
        
        # Send the email
        email.send()
        
        logger.info("Email sent successfully!")
        
        # Update delivery status to completed
        delivery.status = 'completed'
        delivery.completed_at = timezone.now()
        delivery.delivery_notes = f"Styled PDF sent successfully to {delivery.recipient_email}"
        delivery.save()
        
        logger.info(f"DELIVERY COMPLETED: Status = {delivery.status}")
        
    except Exception as e:
        logger.error(f"PDF email delivery failed: {e}")
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.save()
        raise



def process_email_link_delivery(delivery, kwargs):
    """
    Process email delivery with secure download link - SIMPLIFIED VERSION
    """
    try:
        card = delivery.card
        request = kwargs.get('request')
        
        logger.info(f"🔗 Starting link email process for {card.card_number}")
        
        # Generate secure download token
        if not delivery.download_token:
            delivery.download_token = secrets.token_urlsafe(32)
            delivery.download_expires_at = timezone.now() + timedelta(days=30)
            delivery.max_downloads = kwargs.get('max_downloads', 5)
            delivery.save()
            
        logger.info(f"🔑 Generated download token: {delivery.download_token[:10]}...")
        
        # Build download URL
        download_path = reverse('affiliationcard:download_card', args=[delivery.download_token])
        if request:
            download_url = request.build_absolute_uri(download_path)
        else:
            download_url = f"http://localhost:8000{download_path}"
            
        logger.info(f"🔗 Download URL: {download_url}")
        
        # Simple email content
        subject = kwargs.get('email_subject', f'Download Your ACRP Digital Card - {card.card_number}')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1>Download Your ACRP Digital Card</h1>
                <p>Dear {delivery.recipient_name},</p>
                <p>Your ACRP digital card is ready for download.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{download_url}" style="background-color: #1e40af; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">Download Your Card</a>
                </div>
                <p><strong>Card Number:</strong> {card.card_number}</p>
                <p><strong>Expires:</strong> {delivery.download_expires_at.strftime('%B %d, %Y')}</p>
                <p><strong>Max Downloads:</strong> {delivery.max_downloads}</p>
                <p>Best regards,<br>The ACRP Team</p>
            </div>
        </body>
        </html>
        """
        
        # Send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Download your card at: {download_url}",
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'dave@kreeck.com'),
            to=[delivery.recipient_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info("✓ Link email sent successfully!")
        
        # Update delivery status
        delivery.status = 'completed'
        delivery.completed_at = timezone.now()
        delivery.delivery_notes = f"Download link sent to {delivery.recipient_email}"
        delivery.save()
        
        logger.info(f"✓ Link email delivery completed for card {card.card_number}")
        
    except Exception as e:
        logger.error(f"✗ Link email delivery failed: {e}")
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.save()
        raise


def process_direct_download_delivery(delivery, kwargs):
    """
    Process direct download generation - SIMPLIFIED VERSION
    """
    try:
        card = delivery.card
        logger.info(f"⬇️ Processing direct download for {card.card_number}")
        
        # Generate download token
        if not delivery.download_token:
            delivery.download_token = secrets.token_urlsafe(32)
            delivery.download_expires_at = timezone.now() + timedelta(hours=24)
            delivery.max_downloads = 1
            delivery.save()
        
        # Update status
        delivery.status = 'ready_for_download'
        delivery.completed_at = timezone.now()
        delivery.delivery_notes = f"Direct download prepared for {card.card_number}"
        delivery.save()
        
        logger.info(f"✓ Direct download prepared for card {card.card_number}")
        return delivery
        
    except Exception as e:
        logger.error(f"✗ Direct download failed: {e}")
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.save()
        raise


def generate_card_file_simple(card, file_format):
    """
    Simple card file generation - SELF-CONTAINED VERSION
    """
    logger.info(f"🎨 Generating {file_format} file for card {card.card_number}")
    
    try:
        if file_format.lower() == 'pdf':
            return generate_simple_pdf(card)
        elif file_format.lower() in ['png', 'jpg', 'jpeg']:
            return generate_simple_image(card, file_format.upper())
        else:
            raise ValueError(f"Unsupported format: {file_format}")
            
    except Exception as e:
        logger.error(f"✗ File generation failed: {e}")
        raise


def generate_simple_pdf(card):
    """
    Generate a simple PDF card - MINIMAL VERSION FOR TESTING
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        logger.info("🔨 Creating simple PDF...")
        
        # Create buffer
        buffer = BytesIO()
        
        # Simple 8.5x11 page for testing
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Simple card design
        c.setFont("Helvetica-Bold", 24)
        c.drawString(100, height - 100, "ACRP Digital Card")
        
        c.setFont("Helvetica", 16)
        c.drawString(100, height - 150, f"Card Number: {card.card_number}")
        c.drawString(100, height - 180, f"Name: {card.get_display_name()}")
        c.drawString(100, height - 210, f"Status: {card.get_status_display()}")
        
        # Add simple border
        c.rect(50, height - 300, 400, 200, stroke=1, fill=0)
        
        # Save PDF
        c.save()
        
        # Get content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        filename = f"ACRP_Card_{card.card_number}.pdf"
        content_type = 'application/pdf'
        
        logger.info(f"✓ Generated simple PDF: {filename} ({len(pdf_content)} bytes)")
        return pdf_content, filename, content_type
        
    except Exception as e:
        logger.error(f"✗ PDF generation failed: {e}")
        raise


def generate_simple_image(card, format_type):
    """
    Generate a simple image card - MINIMAL VERSION FOR TESTING
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        logger.info(f"🖼️ Creating simple {format_type} image...")
        
        # Create simple image
        width, height = 800, 500
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Use default font
        try:
            font_large = ImageFont.truetype("arial.ttf", 36)
            font_medium = ImageFont.truetype("arial.ttf", 24)
            font_small = ImageFont.truetype("arial.ttf", 18)
        except:
            # Fallback to default
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Simple design
        draw.rectangle([(10, 10), (width-10, height-10)], outline='black', width=3)
        draw.text((50, 50), "ACRP Digital Card", fill='black', font=font_large)
        draw.text((50, 120), f"Card: {card.card_number}", fill='black', font=font_medium)
        draw.text((50, 170), f"Name: {card.get_display_name()}", fill='black', font=font_medium)
        draw.text((50, 220), f"Status: {card.get_status_display()}", fill='black', font=font_small)
        
        # Save to buffer
        buffer = BytesIO()
        img.save(buffer, format=format_type)
        buffer.seek(0)
        
        # Prepare response
        extension = format_type.lower()
        if extension == 'jpeg':
            extension = 'jpg'
        
        filename = f"ACRP_Card_{card.card_number}.{extension}"
        content_type = f'image/{extension}'
        
        logger.info(f"✓ Generated simple {format_type}: {filename}")
        return buffer.getvalue(), filename, content_type
        
    except Exception as e:
        logger.error(f"✗ Image generation failed: {e}")
        raise


# For backward compatibility with views.py
def generate_card_file(card, file_format):
    """Wrapper function for backward compatibility"""
    return generate_card_file_simple(card, file_format)