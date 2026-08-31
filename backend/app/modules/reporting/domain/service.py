"""
Report generation service. Deliberately stateless in v1 — reports are
generated on demand from the current investigation data rather than
persisted with a version history (ReportRun in the architecture doc's
`reporting` module is a documented v2 addition once report history/
sharing is actually needed; generating fresh every time is simpler and
correct for an MVP where the underlying data can still change).

Two formats (Markdown, PDF) are both derived directly from the
Investigation object rather than converting Markdown -> PDF, so each
format can be laid out appropriately for its medium (PDF gets a title
page and severity color accents; Markdown stays terse and copy-pasteable).
"""
from datetime import datetime, timezone
from io import BytesIO
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.investigations.infrastructure.models import Investigation
from app.shared.exceptions import ValidationError

_SEVERITY_COLORS = {
    "critical": colors.HexColor("#E5484D"),
    "high": colors.HexColor("#F2994A"),
    "medium": colors.HexColor("#F2C94C"),
    "low": colors.HexColor("#4DD8E8"),
    "info": colors.HexColor("#6B7280"),
}

REPORT_TYPES = {"executive", "technical"}
REPORT_FORMATS = {"markdown", "pdf"}


def _pdf_text(value: object) -> str:
    """ReportLab Paragraph accepts markup; persisted values must remain text."""
    return escape(str(value or ""))


class ReportService:
    def generate(self, investigation: Investigation, report_type: str, report_format: str) -> tuple[bytes, str, str]:
        """Returns (content_bytes, media_type, filename)."""
        if report_type not in REPORT_TYPES:
            raise ValidationError(f"Invalid report type '{report_type}'. Must be one of: {', '.join(REPORT_TYPES)}.")
        if report_format not in REPORT_FORMATS:
            raise ValidationError(f"Invalid format '{report_format}'. Must be one of: {', '.join(REPORT_FORMATS)}.")

        slug = re.sub(r"[^a-z0-9]+", "-", investigation.title.lower()).strip("-")[:40] or "investigation"
        base_filename = f"{report_type}-report-{slug}"

        if report_format == "markdown":
            content = self._generate_markdown(investigation, report_type)
            return content.encode("utf-8"), "text/markdown", f"{base_filename}.md"

        content = self._generate_pdf(investigation, report_type)
        return content, "application/pdf", f"{base_filename}.pdf"

    # --- Markdown ---

    def _generate_markdown(self, inv: Investigation, report_type: str) -> str:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# {inv.title}",
            "",
            f"**Severity:** {inv.severity.value.title()}  ",
            f"**Status:** {inv.status.value.replace('_', ' ').title()}  ",
            f"**Source:** {inv.source}  ",
            f"**Generated:** {generated_at}",
            "",
            "## Root Cause",
            "",
            inv.root_cause or "_Not yet determined._",
            "",
        ]

        if report_type == "executive":
            lines += [
                "## Business Impact",
                "",
                inv.blast_radius_summary or "_Not yet assessed._",
                "",
                "## Recommended Actions",
                "",
            ]
            if inv.recommended_actions:
                for action in inv.recommended_actions:
                    lines.append(f"- **{action.title}** _( {action.status} )_ — {action.description}")
            else:
                lines.append("_No actions recommended._")
            lines.append("")
            lines += [
                "## AI Confidence",
                "",
                f"Aegis AI assessed this finding with {inv.confidence}% confidence "
                f"and a {inv.false_positive_probability}% estimated false-positive probability.",
                "",
            ]
        else:  # technical
            lines += [
                "## MITRE ATT&CK Techniques",
                "",
                (", ".join(inv.mitre_techniques) if inv.mitre_techniques else "_None identified._"),
                "",
                "## Blast Radius",
                "",
                inv.blast_radius_summary or "_Not yet assessed._",
                "",
                "## Indicators of Compromise",
                "",
            ]
            if inv.evidence:
                for ev in inv.evidence:
                    lines.append(f"- `{ev.value}` ({ev.type.value})")
            else:
                lines.append("_None recorded._")
            lines += ["", "## Timeline", ""]
            if inv.timeline_events:
                for event in sorted(inv.timeline_events, key=lambda e: e.occurred_at):
                    ts = event.occurred_at.strftime("%Y-%m-%d %H:%M UTC")
                    lines.append(f"- **{ts}** — {event.description}")
            else:
                lines.append("_No timeline events recorded._")
            lines += ["", "## Analyst Notes", ""]
            if inv.notes:
                for note in inv.notes:
                    ts = note.created_at.strftime("%Y-%m-%d %H:%M UTC")
                    lines.append(f"- **{ts}** — {note.body}")
            else:
                lines.append("_No notes recorded._")
            lines += [
                "",
                "## AI Assessment",
                "",
                f"- Confidence: {inv.confidence}%",
                f"- False-positive probability: {inv.false_positive_probability}%",
                "",
            ]

        return "\n".join(lines)

    # --- PDF ---

    def _generate_pdf(self, inv: Investigation, report_type: str) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.85 * inch,
            rightMargin=0.85 * inch,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "AegisTitle", parent=styles["Title"], textColor=colors.HexColor("#12161D"), spaceAfter=4
        )
        heading_style = ParagraphStyle(
            "AegisHeading", parent=styles["Heading2"], textColor=colors.HexColor("#12161D"), spaceBefore=16, spaceAfter=6
        )
        body_style = ParagraphStyle("AegisBody", parent=styles["BodyText"], leading=15)
        meta_style = ParagraphStyle("AegisMeta", parent=styles["BodyText"], textColor=colors.grey, fontSize=9)

        severity_color = _SEVERITY_COLORS.get(inv.severity.value, colors.grey)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        story = [
            Paragraph(f"{'Executive' if report_type == 'executive' else 'Technical'} Report", meta_style),
            Paragraph(_pdf_text(inv.title), title_style),
            Paragraph(
                f'<font color="{severity_color.hexval()}"><b>{inv.severity.value.upper()}</b></font> '
                f"&nbsp;•&nbsp; {inv.status.value.replace('_', ' ').title()} &nbsp;•&nbsp; "
                f"Source: {_pdf_text(inv.source)} &nbsp;•&nbsp; Generated {generated_at}",
                meta_style,
            ),
            Spacer(1, 12),
            Paragraph("Root Cause", heading_style),
            Paragraph(_pdf_text(inv.root_cause or "Not yet determined."), body_style),
        ]

        if report_type == "executive":
            story += [
                Paragraph("Business Impact", heading_style),
                Paragraph(_pdf_text(inv.blast_radius_summary or "Not yet assessed."), body_style),
                Paragraph("Recommended Actions", heading_style),
            ]
            if inv.recommended_actions:
                data = [["Action", "Status"]] + [
                    [a.title, a.status.value.title()] for a in inv.recommended_actions
                ]
                table = Table(data, colWidths=[4.2 * inch, 1.3 * inch])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12161D")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.append(table)
            else:
                story.append(Paragraph("No actions recommended.", body_style))
            story += [
                Paragraph("AI Confidence", heading_style),
                Paragraph(
                    f"Aegis AI assessed this finding with {inv.confidence}% confidence and a "
                    f"{inv.false_positive_probability}% estimated false-positive probability.",
                    body_style,
                ),
            ]
        else:
            story += [
                Paragraph("MITRE ATT&CK Techniques", heading_style),
                Paragraph(_pdf_text(", ".join(inv.mitre_techniques) or "None identified."), body_style),
                Paragraph("Blast Radius", heading_style),
                Paragraph(_pdf_text(inv.blast_radius_summary or "Not yet assessed."), body_style),
                Paragraph("Indicators of Compromise", heading_style),
            ]
            if inv.evidence:
                data = [["Value", "Type"]] + [[e.value, e.type.value] for e in inv.evidence]
                table = Table(data, colWidths=[3.8 * inch, 1.7 * inch])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12161D")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 1), (0, -1), "Courier"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.append(table)
            else:
                story.append(Paragraph("None recorded.", body_style))

            story.append(Paragraph("Timeline", heading_style))
            if inv.timeline_events:
                for event in sorted(inv.timeline_events, key=lambda e: e.occurred_at):
                    ts = event.occurred_at.strftime("%Y-%m-%d %H:%M UTC")
                    story.append(Paragraph(f"<b>{ts}</b> — {_pdf_text(event.description)}", body_style))
            else:
                story.append(Paragraph("No timeline events recorded.", body_style))

            story.append(Paragraph("Analyst Notes", heading_style))
            if inv.notes:
                for note in inv.notes:
                    ts = note.created_at.strftime("%Y-%m-%d %H:%M UTC")
                    story.append(Paragraph(f"<b>{ts}</b> — {_pdf_text(note.body)}", body_style))
            else:
                story.append(Paragraph("No notes recorded.", body_style))

            story += [
                Paragraph("AI Assessment", heading_style),
                Paragraph(
                    f"Confidence: {inv.confidence}% &nbsp;•&nbsp; "
                    f"False-positive probability: {inv.false_positive_probability}%",
                    body_style,
                ),
            ]

        doc.build(story)
        return buffer.getvalue()
