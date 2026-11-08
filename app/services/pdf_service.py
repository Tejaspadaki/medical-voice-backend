import os
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from sqlalchemy.orm import Session
from app.models.consultation import Consultation
from app.models.medical_report import MedicalReport
from app.models.patient import Patient
from app.models.user import User
from app.core.logging import logger

REPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../generated_reports"))
os.makedirs(REPORTS_DIR, exist_ok=True)

# Register Kannada Unicode Font
FONT_NAME = "Helvetica"
BOLD_FONT_NAME = "Helvetica-Bold"

def init_kannada_fonts():
    global FONT_NAME, BOLD_FONT_NAME
    # 1. Primary: Dedicated Noto Sans Kannada TrueType Fonts in assets
    local_font = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../assets/fonts/NotoSansKannada-Regular.ttf"))
    local_bold = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../assets/fonts/NotoSansKannada-Bold.ttf"))
    
    if os.path.exists(local_font):
        try:
            pdfmetrics.registerFont(TTFont("Kannada", local_font))
            if os.path.exists(local_bold):
                pdfmetrics.registerFont(TTFont("Kannada-Bold", local_bold))
                BOLD_FONT_NAME = "Kannada-Bold"
            else:
                BOLD_FONT_NAME = "Kannada"
            FONT_NAME = "Kannada"
            logger.info("Successfully registered NotoSansKannada TTF fonts for PDF reports.")
            return
        except Exception as e:
            logger.warning(f"Failed to register NotoSansKannada font: {e}")

    # Fallback standard
    FONT_NAME = "Helvetica"
    BOLD_FONT_NAME = "Helvetica-Bold"

init_kannada_fonts()

class PdfReportService:
    @staticmethod
    def generate_and_save_pdf_report(
        db: Session,
        consultation: Consultation,
        patient: Patient,
        doctor_name: str,
        doctor_reg: str
    ) -> MedicalReport:
        init_kannada_fonts()

        clean_name = "".join(c for c in patient.full_name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        pdf_filename = f"Prescription_{clean_name}_{consultation.report_id}.pdf"
        pdf_file_path = os.path.join(REPORTS_DIR, pdf_filename)

        # Build PDF with ReportLab
        doc = SimpleDocTemplate(
            pdf_file_path,
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom Styles using Unicode Kannada font
        title_style = ParagraphStyle(
            'HospitalTitle',
            parent=styles['Heading1'],
            fontSize=15,
            leading=19,
            textColor=colors.HexColor('#0f172a'),
            fontName=BOLD_FONT_NAME
        )
        subtitle_style = ParagraphStyle(
            'HospitalSubtitle',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#0369a1'),
            fontName=BOLD_FONT_NAME
        )
        address_style = ParagraphStyle(
            'HospitalAddress',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#475569'),
            fontName=FONT_NAME
        )
        section_title = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor('#0f172a'),
            fontName=BOLD_FONT_NAME,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#1e293b'),
            fontName=FONT_NAME
        )
        meta_label = ParagraphStyle(
            'MetaLabel',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#64748b'),
            fontName=BOLD_FONT_NAME
        )
        meta_val = ParagraphStyle(
            'MetaVal',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#0f172a'),
            fontName=BOLD_FONT_NAME
        )

        elements = []

        # 1. Hospital Header
        header_data = [
            [
                Paragraph("<b>ಕರ್ನಾಟಕ ಆರೋಗ್ಯ ಮತ್ತು ಸಂಶೋಧನಾ ಸಂಸ್ಥೆ</b><br/><font size=8 color='#0369a1'>KARNATAKA HEALTH & CLINICAL RESEARCH INSTITUTE</font>", title_style),
                Paragraph(f"<b>{doctor_name}</b><br/><font size=8 color='#0369a1'>KMC Reg: {doctor_reg}</font>", ParagraphStyle('DocInfo', parent=styles['Normal'], fontName=BOLD_FONT_NAME, alignment=2, leading=12))
            ],
            [
                Paragraph("ಬಾಹ್ಯ ರೋಗಿಗಳ ವಿಭಾಗ (OPD Care) • ವೈದ್ಯಕೀಯ ಧ್ವನಿ ಲಿಪ್ಯಂತರ ವಿಭಾಗ<br/>ಮಲ್ಲೇಶ್ವರಂ ೧೮ನೇ ಕ್ರಾಸ್, ಬೆಂಗಳೂರು - ೫೬೦೦೦೩ | ದೂರವಾಣಿ: ೦೮೦-೨೩೪೫೬೭೮೯", address_style),
                Paragraph(f"<font size=8 color='#64748b'>ವರದಿ ಸಂ (Report ID):</font><br/><b>{consultation.report_id}</b>", ParagraphStyle('RepId', parent=styles['Normal'], fontName=BOLD_FONT_NAME, alignment=2, leading=11))
            ]
        ]
        header_table = Table(header_data, colWidths=[330, 190])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0f172a'), spaceAfter=10))

        # 2. Patient Demographics Bar
        signed_time = consultation.signed_at or consultation.created_at or datetime.now(timezone.utc)
        current_date_str = signed_time.strftime("%d-%m-%Y, %I:%M %p")
        gender_val = patient.gender if patient and patient.gender else "N/A"
        gender_kn = "ಪುರುಷ (Male)" if gender_val == "Male" else "ಮಹಿಳೆ (Female)" if gender_val == "Female" else gender_val
        
        patient_info = [
            [
                Paragraph("ರೋಗಿಯ ಹೆಸರು (Name):", meta_label),
                Paragraph(f"<b>{patient.full_name if patient else 'Patient'}</b>", meta_val),
                Paragraph("ರೋಗಿ ಐಡಿ (ID):", meta_label),
                Paragraph(f"<b>#PT-{str(patient.patient_id).zfill(4) if patient else '0001'}</b>", meta_val)
            ],
            [
                Paragraph("ಲಿಂಗ / ಜನ್ಮದಿನ:", meta_label),
                Paragraph(f"{gender_kn} • {(patient.dob if patient and patient.dob else 'N/A')}", body_style),
                Paragraph("ದಿನಾಂಕ (Date):", meta_label),
                Paragraph(current_date_str, body_style)
            ],
            [
                Paragraph("ಸಂಪರ್ಕ ಸಂಖ್ಯೆ:", meta_label),
                Paragraph(patient.phone if patient and patient.phone else "N/A", body_style),
                Paragraph("ಭಾಷೆ / ರಕ್ತದ ಗುಂಪು:", meta_label),
                Paragraph(f"{(patient.preferred_language if patient and patient.preferred_language else 'Kannada')} • {(patient.blood_group if patient and patient.blood_group else 'N/A')}", body_style)
            ]
        ]
        patient_table = Table(patient_info, colWidths=[110, 150, 100, 160])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(patient_table)
        elements.append(Spacer(1, 12))

        # 3. Chief Complaints & Symptoms
        elements.append(Paragraph("೧. ಪ್ರಮುಖ ರೋಗಲಕ್ಷಣಗಳು (Chief Complaints & Symptoms)", section_title))
        if consultation.symptoms:
            for s in consultation.symptoms:
                dur = f" (ಅವಧಿ: {s.get('duration')})" if s.get('duration') else ""
                eng = f" [{s.get('english')}]" if s.get('english') else ""
                elements.append(Paragraph(f"• <b>{s.get('entity')}</b>{eng}{dur}", body_style))
        else:
            elements.append(Paragraph("• ಯಾವುದೇ ಗಂಭೀರ ಲಕ್ಷಣಗಳಿಲ್ಲ.", body_style))
        elements.append(Spacer(1, 10))

        # 4. Clinical Diagnosis
        elements.append(Paragraph("೨. ವೈದ್ಯಕೀಯ ರೋಗನಿರ್ಣಯ (Provisional / Final Diagnosis)", section_title))
        if consultation.diagnosis:
            for d in consultation.diagnosis:
                eng = f" [{d.get('english')}]" if d.get('english') else ""
                elements.append(Paragraph(f"• <b>{d.get('entity')}</b>{eng}", body_style))
        else:
            elements.append(Paragraph("• ಸಾಮಾನ್ಯ ವೈದ್ಯಕೀಯ ತಪಾಸಣೆ", body_style))
        elements.append(Spacer(1, 10))

        # 5. Medications Table (Rx)
        elements.append(Paragraph("೩. ಔಷಧೀಯ ಚೀಟಿ (Prescribed Medications & Dosages - Rx)", section_title))
        rx_data = [
            [
                Paragraph("<b>ಕ್ರ.ಸಂ</b>", meta_label),
                Paragraph("<b>ಔಷಧ / ಮಾತ್ರೆ ಹೆಸರು (Drug Name)</b>", meta_label),
                Paragraph("<b>ಪ್ರಮಾಣ (Dose)</b>", meta_label),
                Paragraph("<b>ಸೇವಿಸುವ ಸಮಯ (Frequency)</b>", meta_label),
                Paragraph("<b>ಅವಧಿ (Duration)</b>", meta_label)
            ]
        ]
        for idx, m in enumerate(consultation.medications or []):
            rx_data.append([
                Paragraph(str(idx + 1), body_style),
                Paragraph(f"<b>{m.get('drug_name')}</b>", body_style),
                Paragraph(str(m.get('dosage', '-')), body_style),
                Paragraph(str(m.get('frequency', '-')), body_style),
                Paragraph(str(m.get('duration', '-')), body_style)
            ])
        
        if len(rx_data) > 1:
            rx_table = Table(rx_data, colWidths=[30, 180, 95, 135, 80])
            rx_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(rx_table)
        else:
            elements.append(Paragraph("• ಯಾವುದೇ ಔಷಧಗಳನ್ನು ಸೂಚಿಸಿಲ್ಲ.", body_style))
        elements.append(Spacer(1, 10))

        # 6. Patient Instructions / Advice
        elements.append(Paragraph("೪. ವೈದ್ಯರ ವಿಶೇಷ ಸಲಹೆಗಳು (Special Advice & Instructions)", section_title))
        if consultation.advice:
            for a in consultation.advice:
                elements.append(Paragraph(f"• {a.get('instruction')}", body_style))
        else:
            elements.append(Paragraph("• ಸಾಕಷ್ಟು ನೀರು ಕುಡಿಯಿರಿ ಮತ್ತು ವಿಶ್ರಾಂತಿ ಪಡೆಯಿರಿ.", body_style))
        elements.append(Spacer(1, 10))

        # 7. Kannada Transcription Transcript
        if consultation.kannada_transcript:
            elements.append(Paragraph("೫. ಕನ್ನಡ ಧ್ವನಿ ಮುದ್ರಣ ವಿವರಣೆ (Transcription)", section_title))
            elements.append(Paragraph(f"<i>\"{consultation.kannada_transcript}\"</i>", ParagraphStyle('Trans', parent=body_style, textColor=colors.HexColor('#334155'), fontSize=8, leading=11)))
            elements.append(Spacer(1, 14))

        # 8. Digital Signature Footer
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=8))
        sig_data = [
            [
                Paragraph("<font size=7 color='#64748b'>• AuraDoc AI ವೈದ್ಯಕೀಯ ಧ್ವನಿ ಸಮಾಲೋಚನೆ ವ್ಯವಸ್ಥೆ.<br/>• ವೈದ್ಯರಿಂದ ಅಧಿಕೃತವಾಗಿ ದೃಢೀಕರಿಸಲ್ಪಟ್ಟು ಡಿಜಿಟಲ್ ಸಹಿ ಮಾಡಲಾಗಿದೆ.</font>", body_style),
                Paragraph(f"<b>{doctor_name}</b><br/><font size=8 color='#0369a1'>KMC Reg: {doctor_reg}</font><br/><font size=7 color='#16a34a'><b>[ಡಿಜಿಟಲ್ ಸಹಿ ದೃಢೀಕರಿಸಲಾಗಿದೆ]</b></font>", ParagraphStyle('Sig', parent=styles['Normal'], fontName=BOLD_FONT_NAME, alignment=2, leading=11))
            ]
        ]
        sig_table = Table(sig_data, colWidths=[310, 210])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(sig_table)

        # Build document
        doc.build(elements)

        # Read generated PDF bytes and encode base64
        with open(pdf_file_path, "rb") as f:
            pdf_bytes = f.read()
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        file_size = len(pdf_bytes)

        # Update consultation model
        consultation.pdf_filename = pdf_filename
        consultation.pdf_file_path = pdf_file_path

        # Insert or update into medical_reports SQL table
        existing_report = db.query(MedicalReport).filter(MedicalReport.consultation_id == consultation.consultation_id).first()
        if existing_report:
            existing_report.pdf_filename = pdf_filename
            existing_report.pdf_file_path = pdf_file_path
            existing_report.pdf_base64_data = pdf_base64
            existing_report.file_size_bytes = file_size
            existing_report.signed_doctor_name = doctor_name
            existing_report.signed_doctor_reg = doctor_reg
            db.commit()
            db.refresh(existing_report)
            report_record = existing_report
        else:
            report_record = MedicalReport(
                consultation_id=consultation.consultation_id,
                patient_id=patient.patient_id,
                doctor_id=consultation.doctor_id,
                report_code=consultation.report_id,
                pdf_filename=pdf_filename,
                pdf_file_path=pdf_file_path,
                pdf_base64_data=pdf_base64,
                file_size_bytes=file_size,
                mime_type="application/pdf",
                signed_doctor_name=doctor_name,
                signed_doctor_reg=doctor_reg,
                status="CONFIRMED_SIGNED",
                created_at=datetime.now(timezone.utc)
            )
            db.add(report_record)
            db.commit()
            db.refresh(report_record)

        logger.info(f"Kannada Unicode PDF Prescription generated & saved in SQL database: {pdf_filename} ({file_size} bytes)")
        return report_record
