
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
    
    Args:
        card: AffiliationCard instance
        delivery_method: String - 'email_pdf', 'email_link', or 'direct_download'
        recipient_email: String - recipient's email address
        recipient_name: String - recipient's full name
        **kwargs: Additional parameters (email_subject, email_message, file_format, etc.)
    
    Returns:
        CardDelivery instance
    """
    try:
        # Import here to avoid circular imports
        from .models import CardDelivery
        
        # Create delivery record with initial status
        delivery = CardDelivery.objects.create(
            card=card,
            delivery_type=delivery_method,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            initiated_by=kwargs.get('initiated_by'),
            file_format=kwargs.get('file_format', 'pdf'),
            status='processing',
            email_subject=kwargs.get('email_subject', ''),
            email_message=kwargs.get('email_message', ''),
            max_downloads=kwargs.get('max_downloads', 5),
        )
        
        logger.info(f"Created card delivery {delivery.id} for card {card.card_number}")
        
        # Process delivery based on method
        if delivery_method == 'email_pdf':
            process_email_pdf_delivery(delivery, kwargs)
        elif delivery_method == 'email_link':
            process_email_link_delivery(delivery, kwargs)
        elif delivery_method == 'direct_download':
            return process_direct_download_delivery(delivery, kwargs)
        else:
            raise ValueError(f"Unsupported delivery method: {delivery_method}")
        
        return delivery
        
    except Exception as e:
        logger.error(f"Failed to create card delivery: {e}")
        # Update delivery status if it was created
        if 'delivery' in locals():
            delivery.status = 'failed'
            delivery.failure_reason = str(e)
            delivery.save()
        raise


def process_email_pdf_delivery(delivery, kwargs):
    """
    Process email delivery with PDF attachment using Mailjet.
    
    This function generates the card as a PDF and sends it via Mailjet
    with the PDF file attached directly to the message.
    
    Args:
        delivery: CardDelivery instance
        kwargs: Additional parameters from delivery creation
    """
    try:
        card = delivery.card
        
        logger.info(f"Processing PDF email delivery for card {card.card_number}")
        
        # Generate PDF file
        file_content, filename, content_type = generate_card_file(card, 'pdf')
        
        # Encode PDF for email attachment
        pdf_base64 = base64.b64encode(file_content).decode('utf-8')
        
        # Prepare email context for template rendering
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
        
        # Try to use templates, fallback to simple message if templates don't exist
        try:
            html_content = render_to_string('email_templates/affiliationcard/card_pdf_delivery.html', context)
            text_content = render_to_string('email_templates/affiliationcard/card_pdf_delivery.txt', context)
        except:
            # Fallback to simple email content
            html_content = f"""
            <h2>Your ACRP Digital Card - {card.card_number}</h2>
            <p>Dear {delivery.recipient_name},</p>
            <p>Your ACRP digital affiliation card has been generated and is attached to this email as a PDF file.</p>
            <p><strong>Card Details:</strong></p>
            <ul>
                <li>Card Number: {card.card_number}</li>
                <li>Council: {context['council_name']}</li>
                <li>Affiliation Type: {context['affiliation_type']}</li>
                <li>Status: {card.get_status_display()}</li>
            </ul>
            <p>Please save this card to your device for future use.</p>
            <p>Best regards,<br>ACRP Digital Cards Team</p>
            """
            
            text_content = f"""
Your ACRP Digital Card - {card.card_number}

Dear {delivery.recipient_name},

Your ACRP digital affiliation card has been generated and is attached to this email as a PDF file.

Card Details:
- Card Number: {card.card_number}
- Council: {context['council_name']}
- Affiliation Type: {context['affiliation_type']}
- Status: {card.get_status_display()}

Please save this card to your device for future use.

Best regards,
ACRP Digital Cards Team
            """
        
        # Check if Mailjet is configured, fallback to Django's EmailMessage if not
        try:
            # Try Mailjet first
            mailjet_client = get_mailjet_client()
            
            # Prepare Mailjet email data
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
                    'Subject': kwargs.get('email_subject', f'Your ACRP Digital Card - {card.card_number}'),
                    'TextPart': text_content,
                    'HTMLPart': html_content,
                    'Attachments': [{
                        'ContentType': content_type,
                        'Filename': filename,
                        'Base64Content': pdf_base64
                    }]
                }]
            }
            
            # Send email via Mailjet
            result = mailjet_client.send.create(data=email_data)
            
            if result.status_code == 200:
                # Update delivery status on success
                delivery.status = 'completed'
                delivery.completed_at = timezone.now()
                delivery.delivery_notes = f"PDF attachment sent successfully via Mailjet to {delivery.recipient_email}"
                delivery.mailjet_message_id = result.json()['Messages'][0]['MessageID']
                delivery.save()
                
                logger.info(f"PDF email delivery completed via Mailjet for card {card.card_number}")
            else:
                raise Exception(f"Mailjet API error: {result.status_code} - {result.json()}")
                
        except Exception as mailjet_error:
            # Fallback to Django's built-in email
            logger.warning(f"Mailjet delivery failed, falling back to Django email: {mailjet_error}")
            
            email = EmailMessage(
                subject=kwargs.get('email_subject', f'Your ACRP Digital Card - {card.card_number}'),
                body=text_content,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'dave@kreeck.com'),
                to=[delivery.recipient_email]
            )
            
            # Attach HTML alternative
            email.attach_alternative(html_content, "text/html")
            
            # Attach PDF
            email.attach(filename, file_content, content_type)
            
            # Send email
            email.send()
            
            # Update delivery status
            delivery.status = 'completed'
            delivery.completed_at = timezone.now()
            delivery.delivery_notes = f"PDF attachment sent successfully via Django email to {delivery.recipient_email}"
            delivery.save()
            
            logger.info(f"PDF email delivery completed via Django email for card {card.card_number}")
        
    except Exception as e:
        # Update delivery status on failure
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.error_message = str(e)  # For backward compatibility
        delivery.save()
        
        logger.error(f"PDF email delivery failed for card {card.card_number}: {e}")
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
    Process direct download generation.
    
    This function prepares a card for immediate download without email,
    typically used for admin-initiated downloads or API responses.
    
    Args:
        delivery: CardDelivery instance
        kwargs: Additional parameters from delivery creation
        
    Returns:
        tuple: (file_content, filename, content_type) for immediate download
    """
    try:
        card = delivery.card
        
        logger.info(f"Processing direct download for card {card.card_number}")
        
        # Generate download token for tracking
        if not delivery.download_token:
            delivery.download_token = secrets.token_urlsafe(32)
            delivery.download_expires_at = timezone.now() + timedelta(hours=24)
            delivery.max_downloads = 1  # Single download for direct downloads
        
        # Generate the card file for immediate availability
        file_content, filename, content_type = generate_card_file(
            card, 
            delivery.file_format or 'pdf'
        )
        
        # Store file metadata for tracking
        delivery.file_size = len(file_content)
        delivery.generated_filename = filename
        
        # Update delivery status
        delivery.status = 'ready_for_download'
        delivery.completed_at = timezone.now()
        delivery.delivery_notes = f"Direct download prepared for {card.card_number}"
        delivery.save()
        
        logger.info(f"Direct download delivery prepared for card {card.card_number}")
        
        # Return file data for immediate download
        return file_content, filename, content_type
        
    except Exception as e:
        # Update delivery status on failure
        delivery.status = 'failed'
        delivery.failure_reason = str(e)
        delivery.error_message = str(e)
        delivery.save()
        
        logger.error(f"Direct download delivery failed for card {card.card_number}: {e}")
        raise


def generate_card_file(card, file_format):
    """Generate card file in specified format."""
    if file_format.lower() == 'pdf':
        return generate_card_pdf(card)
    elif file_format.lower() in ['png', 'PNG']:
        return generate_card_image(card, 'PNG')
    elif file_format.lower() in ['jpg', 'jpeg', 'JPG', 'JPEG']:
        return generate_card_image(card, 'JPEG')
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def generate_card_pdf(card):
    """
    Generate enhanced PDF version of the card with professional design.
    
    Creates a business card sized PDF with proper layout, QR code,
    and ACRP branding elements.
    
    Args:
        card: AffiliationCard instance
        
    Returns:
        tuple: (pdf_content, filename, content_type)
    """
    try:
        # Create buffer for PDF
        buffer = BytesIO()
        
        # Standard business card size (3.5" x 2")
        card_width = 3.5 * inch
        card_height = 2 * inch
        
        # Create canvas with business card dimensions
        c = canvas.Canvas(buffer, pagesize=(card_width, card_height))
        
        # Set up colors
        primary_color = colors.HexColor('#1e40af')  # Blue
        secondary_color = colors.HexColor('#64748b')  # Gray
        text_color = colors.HexColor('#1f2937')  # Dark gray
        
        # Background
        c.setFillColor(colors.white)
        c.rect(0, 0, card_width, card_height, fill=1)
        
        # Header section with background
        c.setFillColor(primary_color)
        c.rect(0, card_height - 40, card_width, 40, fill=1)
        
        # ACRP Logo/Title
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(10, card_height - 25, "ACRP")
        
        c.setFont("Helvetica", 8)
        c.drawString(10, card_height - 35, "Digital Affiliation Card")
        
        # Card number (top right)
        c.setFont("Helvetica-Bold", 8)
        text_width = c.stringWidth(f"#{card.card_number}", "Helvetica-Bold", 8)
        c.drawString(card_width - text_width - 10, card_height - 25, f"#{card.card_number}")
        
        # Main content area
        c.setFillColor(text_color)
        y_position = card_height - 60
        
        # Affiliate name
        c.setFont("Helvetica-Bold", 12)
        affiliate_name = card.get_display_name()
        if len(affiliate_name) > 25:  # Truncate long names
            affiliate_name = affiliate_name[:22] + "..."
        c.drawString(10, y_position, affiliate_name)
        y_position -= 15
        
        # Council and affiliation type
        c.setFont("Helvetica", 8)
        c.setFillColor(secondary_color)
        council_text = f"{getattr(card, 'council_name', 'N/A')}"
        if len(council_text) > 30:
            council_text = council_text[:27] + "..."
        c.drawString(10, y_position, council_text)
        y_position -= 10
        
        affiliation_text = f"{getattr(card, 'affiliation_type', 'N/A').title()}"
        c.drawString(10, y_position, affiliation_text)
        y_position -= 15
        
        # Status and dates
        c.setFont("Helvetica", 7)
        c.setFillColor(text_color)
        
        status_text = f"Status: {card.get_status_display()}"
        c.drawString(10, y_position, status_text)
        y_position -= 8
        
        if hasattr(card, 'date_issued') and card.date_issued:
            issued_text = f"Issued: {card.date_issued.strftime('%m/%d/%Y')}"
            c.drawString(10, y_position, issued_text)
            y_position -= 8
        
        if hasattr(card, 'date_expires') and card.date_expires:
            expires_text = f"Expires: {card.date_expires.strftime('%m/%d/%Y')}"
            c.drawString(10, y_position, expires_text)
        
        # Generate and add QR code
        qr_data = getattr(card, 'qr_code_data', f"https://your-domain.com/verify/{getattr(card, 'verification_token', 'unknown')}")
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code to temporary buffer
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        # Add QR code to PDF (right side)
        qr_size = 50  # Size in points
        qr_x = card_width - qr_size - 10
        qr_y = 15
        
        c.drawInlineImage(qr_buffer, qr_x, qr_y, qr_size, qr_size)
        
        # QR code label
        c.setFont("Helvetica", 6)
        c.setFillColor(secondary_color)
        qr_label_width = c.stringWidth("Scan to verify", "Helvetica", 6)
        c.drawString(qr_x + (qr_size - qr_label_width) / 2, qr_y - 8, "Scan to verify")
        
        # Footer with verification URL (small text)
        c.setFont("Helvetica", 5)
        verification_token = getattr(card, 'verification_token', 'unknown')
        footer_text = f"Verify at: your-domain.com/verify/{verification_token[:8]}..."
        c.drawString(10, 5, footer_text)
        
        # Card border
        c.setStrokeColor(colors.lightgrey)
        c.setLineWidth(0.5)
        c.rect(0, 0, card_width, card_height, fill=0, stroke=1)
        
        # Save PDF
        c.save()
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        filename = f"ACRP_Card_{card.card_number}.pdf"
        content_type = 'application/pdf'
        
        logger.info(f"Generated PDF card for {card.card_number}")
        return pdf_content, filename, content_type
        
    except Exception as e:
        logger.error(f"Failed to generate PDF card for {card.card_number}: {e}")
        raise


def generate_card_image(card, format_type):
    """
    Generate professional image version of the card.
    
    Creates a business card sized image with modern design,
    proper typography, and QR code integration.
    
    Args:
        card: AffiliationCard instance
        format_type: String - 'PNG' or 'JPEG'
        
    Returns:
        tuple: (image_content, filename, content_type)
    """
    try:
        # Card dimensions (business card size at 300 DPI)
        width, height = 1050, 600  # 3.5" x 2" at 300 DPI
        
        # Create card background
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Colors
        primary_color = '#1e40af'
        secondary_color = '#64748b'
        text_color = '#1f2937'
        
        # Header background
        header_height = 120
        draw.rectangle([(0, 0), (width, header_height)], fill=primary_color)
        
        # Try to load fonts, fallback to default if not available
        try:
            title_font = ImageFont.truetype("arial.ttf", 42)
            subtitle_font = ImageFont.truetype("arial.ttf", 24)
            name_font = ImageFont.truetype("arial.ttf", 36)
            info_font = ImageFont.truetype("arial.ttf", 20)
            small_font = ImageFont.truetype("arial.ttf", 16)
        except:
            # Fallback to default font
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
            name_font = ImageFont.load_default()
            info_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # ACRP Title
        draw.text((30, 25), "ACRP", fill='white', font=title_font)
        draw.text((30, 70), "Digital Affiliation Card", fill='white', font=subtitle_font)
        
        # Card number (top right)
        card_num_text = f"#{card.card_number}"
        try:
            card_num_bbox = draw.textbbox((0, 0), card_num_text, font=info_font)
            card_num_width = card_num_bbox[2] - card_num_bbox[0]
        except:
            # Fallback for older Pillow versions
            card_num_width = len(card_num_text) * 10
        draw.text((width - card_num_width - 30, 25), card_num_text, fill='white', font=info_font)
        
        # Main content area
        y_pos = header_height + 30
        
        # Affiliate name
        affiliate_name = card.get_display_name()
        if len(affiliate_name) > 20:  # Adjust for image layout
            affiliate_name = affiliate_name[:17] + "..."
        
        draw.text((30, y_pos), affiliate_name, fill=text_color, font=name_font)
        y_pos += 50
        
        # Council and affiliation
        council_text = getattr(card, 'council_name', 'N/A')
        if len(council_text) > 35:
            council_text = council_text[:32] + "..."
        
        draw.text((30, y_pos), council_text, fill=secondary_color, font=info_font)
        y_pos += 30
        
        affiliation_text = getattr(card, 'affiliation_type', 'N/A').title()
        draw.text((30, y_pos), affiliation_text, fill=secondary_color, font=info_font)
        y_pos += 40
        
        # Status
        status_text = f"Status: {card.get_status_display()}"
        draw.text((30, y_pos), status_text, fill=text_color, font=small_font)
        
        # Generate QR code
        qr_data = getattr(card, 'qr_code_data', f"https://your-domain.com/verify/{getattr(card, 'verification_token', 'unknown')}")
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_size = 150
        qr_img = qr_img.resize((qr_size, qr_size))
        
        # Position QR code on the right side
        qr_x = width - qr_size - 30
        qr_y = height - qr_size - 30
        img.paste(qr_img, (qr_x, qr_y))
        
        # QR code label
        qr_label = "Scan to verify"
        try:
            qr_label_bbox = draw.textbbox((0, 0), qr_label, font=small_font)
            qr_label_width = qr_label_bbox[2] - qr_label_bbox[0]
        except:
            qr_label_width = len(qr_label) * 8
        qr_label_x = qr_x + (qr_size - qr_label_width) // 2
        draw.text((qr_label_x, qr_y - 25), qr_label, fill=secondary_color, font=small_font)
        
        # Card border
        draw.rectangle([(0, 0), (width-1, height-1)], outline='lightgray', width=2)
        
        # Save image to buffer
        buffer = BytesIO()
        img.save(buffer, format=format_type, quality=95 if format_type == 'JPEG' else None)
        buffer.seek(0)
        
        # Prepare response data
        extension = format_type.lower()
        if extension == 'jpeg':
            extension = 'jpg'
        
        filename = f"ACRP_Card_{card.card_number}.{extension}"
        content_type = f'image/{extension}'
        
        logger.info(f"Generated {format_type} card image for {card.card_number}")
        return buffer.getvalue(), filename, content_type
        
    except Exception as e:
        logger.error(f"Failed to generate {format_type} card for {card.card_number}: {e}")
        raise