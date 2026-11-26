import os
from datetime import datetime, timezone
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.pdf_service import BOLD_FONT_NAME, FONT_NAME, REPORTS_DIR, init_kannada_fonts


class EvaluationReportService:
    """
    Generates official PDF Evaluation Reports for AuraDoc Clinical AI ML Experiments.
    Includes dataset breakdown, WER/CER methodology, model comparison tables,
    efficiency metrics, pilot warnings, and limitations.
    """

    @staticmethod
    def generate_pdf_report(eval_doc: Dict[str, Any], ds_doc: Dict[str, Any]) -> str:
        init_kannada_fonts()
        eval_id = eval_doc.get("evaluation_id", "EVAL")
        pdf_filename = f"AuraDoc_ML_Evaluation_{eval_id}.pdf"
        pdf_path = os.path.join(REPORTS_DIR, pdf_filename)

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=15, fontName=BOLD_FONT_NAME, textColor=colors.HexColor("#0f172a"))
        h2_style = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, fontName=BOLD_FONT_NAME, textColor=colors.HexColor("#0369a1"), spaceAfter=4)
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=13, fontName=FONT_NAME, textColor=colors.HexColor("#1e293b"))
        th_style = ParagraphStyle("TH", parent=styles["Normal"], fontSize=8, fontName=BOLD_FONT_NAME, textColor=colors.HexColor("#0f172a"))

        elements = []
        elements.append(Paragraph("AuraDoc Clinical AI — Multi-Model Speech & NLP Evaluation Report", title_style))
        elements.append(Paragraph(f"Experiment ID: <b>{eval_id}</b> | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", body_style))
        elements.append(Spacer(1, 6))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f172a"), spaceAfter=10))

        # 1. Dataset & Configuration
        ds_graphs = (eval_doc.get("graphs") or {}).get("dataset_graphs", {})
        size_info = ds_graphs.get("dataset_size_analysis", {})
        langs = ", ".join(f"{x['label']}: {x['count']}" for x in ds_graphs.get("language_distribution", []))

        elements.append(Paragraph("1. Dataset & Experiment Configuration", h2_style))
        elements.append(Paragraph(
            f"• <b>Dataset:</b> {ds_doc.get('name')} ({ds_doc.get('dataset_id')})<br/>"
            f"• <b>Total Audio Samples:</b> {size_info.get('total_files', 0)} "
            f"(Annotated Ground-Truth Samples: {eval_doc.get('annotated_samples', 0)})<br/>"
            f"• <b>Total Duration:</b> {size_info.get('total_duration_sec', 0)}s | <b>Total Size:</b> {size_info.get('total_size_mb', 0)} MB<br/>"
            f"• <b>Language Distribution:</b> {langs or 'N/A'}<br/>"
            f"• <b>Normalization Method:</b> {eval_doc.get('normalization_method')}",
            body_style,
        ))
        if eval_doc.get("pilot_warning"):
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(f"<b>[PILOT EVALUATION NOTICE]</b> {eval_doc['pilot_warning']}", body_style))
        elements.append(Spacer(1, 10))

        # 2. Evaluation Methodology
        elements.append(Paragraph("2. Evaluation Methodology", h2_style))
        elements.append(Paragraph(
            "WER = (Substitutions + Deletions + Insertions) / Reference Word Count<br/>"
            "CER = (Character Substitutions + Deletions + Insertions) / Reference Character Count<br/>"
            "Note: Metrics are computed strictly against human-provided reference transcriptions; unannotated samples are marked ANNOTATION_REQUIRED.",
            body_style,
        ))
        elements.append(Spacer(1, 10))

        # 3. Model Comparison Table
        elements.append(Paragraph("3. Model Comparison & Efficiency Results", h2_style))
        table_data = [[
            Paragraph("Model", th_style),
            Paragraph("Version", th_style),
            Paragraph("Mode", th_style),
            Paragraph("Avg WER", th_style),
            Paragraph("Avg CER", th_style),
            Paragraph("Avg Latency", th_style),
            Paragraph("Peak Mem", th_style),
        ]]
        for s in eval_doc.get("model_summaries", []):
            table_data.append([
                Paragraph(str(s.get("model_name")), body_style),
                Paragraph(str(s.get("version")), body_style),
                Paragraph(str(s.get("evaluation_mode")), body_style),
                Paragraph(str(s["avg_wer"]) if s.get("avg_wer") is not None else "Unavailable", body_style),
                Paragraph(str(s["avg_cer"]) if s.get("avg_cer") is not None else "Unavailable", body_style),
                Paragraph(f"{s.get('avg_latency_ms')} ms" if s.get("avg_latency_ms") is not None else "N/A", body_style),
                Paragraph(f"{s.get('peak_memory_mb')} MB" if s.get("peak_memory_mb") is not None else "N/A", body_style),
            ])

        t = Table(table_data, colWidths=[115, 65, 95, 55, 55, 70, 65])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 12))

        # 4. Findings, Limitations & Conclusion
        elements.append(Paragraph("4. Findings, Limitations & Conclusion", h2_style))
        elements.append(Paragraph(
            "• Cloud API models (Sarvam Saaras v3, Gemini) are evaluated in inference-only mode and do not expose local training loss curves.<br/>"
            "• Metrics marked 'Unavailable' indicate missing ground-truth annotations or unconfigured external API keys.<br/>"
            "• All experiments are logged in MongoDB with full preprocessing & model version metadata for reproducibility.",
            body_style,
        ))

        doc.build(elements)
        return pdf_path
