"""PDF outpass generation service using ReportLab."""
import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Image, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from app.services.qr_service import generate_qr_image_bytes


def generate_outpass_pdf(outpass):
    """Generate a professional PDF outpass document.
    
    Returns a BytesIO buffer with the PDF content.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=1.5*cm, bottomMargin=1.5*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=18, textColor=HexColor('#1a237e'),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=12, textColor=HexColor('#37474f'),
        alignment=TA_CENTER, spaceAfter=12
    )
    heading_style = ParagraphStyle(
        'SectionHeading', parent=styles['Heading2'],
        fontSize=13, textColor=HexColor('#1565c0'),
        spaceBefore=10, spaceAfter=6
    )
    normal_style = ParagraphStyle(
        'CustomNormal', parent=styles['Normal'],
        fontSize=10, leading=14
    )
    bold_style = ParagraphStyle(
        'BoldNormal', parent=styles['Normal'],
        fontSize=10, leading=14,
        fontName='Helvetica-Bold'
    )

    elements = []

    # Header
    elements.append(Paragraph('COLLEGE HOSTEL OUTPASS', title_style))
    elements.append(Paragraph('Digital Outpass Management System', subtitle_style))
    elements.append(Spacer(1, 4*mm))

    # Status banner
    status_color = '#4caf50' if outpass.status in ('APPROVED', 'OUT') else '#f44336'
    elements.append(Paragraph(
        f'<font color="{status_color}" size="14"><b>STATUS: {outpass.status}</b></font>',
        ParagraphStyle('Status', alignment=TA_CENTER, spaceAfter=10)
    ))

    # Outpass details table
    student = outpass.student
    user = student.user
    
    elements.append(Paragraph('OUTPASS DETAILS', heading_style))
    
    details_data = [
        ['Outpass Number:', outpass.outpass_number, 'Type:', outpass.outpass_type.name],
        ['Student Name:', user.full_name, 'Register No:', student.register_number],
        ['Department:', student.department.name if student.department else 'N/A',
         'Year:', str(student.year or 'N/A')],
        ['Hostel Block:', student.hostel_block.name if student.hostel_block else 'N/A',
         'Room:', student.room.room_number if student.room else 'N/A'],
        ['Contact:', outpass.contact_number, 'Blood Group:', student.blood_group or 'N/A'],
    ]
    
    detail_table = Table(details_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
    detail_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#37474f')),
        ('TEXTCOLOR', (2, 0), (2, -1), HexColor('#37474f')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e0e0e0')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#f5f5f5')),
        ('BACKGROUND', (2, 0), (2, -1), HexColor('#f5f5f5')),
    ]))
    elements.append(detail_table)
    elements.append(Spacer(1, 6*mm))

    # Travel details
    elements.append(Paragraph('TRAVEL DETAILS', heading_style))
    travel_data = [
        ['Destination:', outpass.destination],
        ['Reason:', outpass.reason],
        ['Departure:', outpass.out_datetime.strftime('%d-%m-%Y %I:%M %p')],
        ['Expected Return:', outpass.expected_return_datetime.strftime('%d-%m-%Y %I:%M %p')],
        ['Parent Name:', student.parent_name or 'N/A'],
        ['Parent Phone:', student.parent_phone or 'N/A'],
    ]
    
    travel_table = Table(travel_data, colWidths=[4*cm, 13*cm])
    travel_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#37474f')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e0e0e0')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#f5f5f5')),
    ]))
    elements.append(travel_table)
    elements.append(Spacer(1, 8*mm))

    # QR Code
    if outpass.qr_token:
        elements.append(Paragraph('VERIFICATION QR CODE', heading_style))
        qr_buf = generate_qr_image_bytes(outpass.qr_token)
        qr_img = Image(qr_buf, width=5*cm, height=5*cm)
        
        qr_table = Table([[qr_img]], colWidths=[17*cm])
        qr_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(qr_table)
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph(
            f'<font size="8" color="#757575">Scan this QR at the gate • Valid until {outpass.expected_return_datetime.strftime("%d-%m-%Y %I:%M %p")}</font>',
            ParagraphStyle('QRNote', alignment=TA_CENTER)
        ))

    elements.append(Spacer(1, 10*mm))

    # Footer
    elements.append(Paragraph(
        f'<font size="7" color="#9e9e9e">Generated on {datetime.utcnow().strftime("%d-%m-%Y %I:%M %p")} | '
        f'This is a computer-generated document. No signature required.</font>',
        ParagraphStyle('Footer', alignment=TA_CENTER)
    ))

    doc.build(elements)
    buf.seek(0)
    return buf
