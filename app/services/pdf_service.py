"""
LearnOrbit PDF Export Service
Generates clean, print-friendly study notes from Markdown content.
"""

import os
import re
import unicodedata
from datetime import datetime


def _md_to_text_blocks(md_text: str) -> list:
    """Parse the Markdown constructs used by the notes generator."""
    blocks = []
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        elif line.startswith("- [ ] ") or line.startswith("- [x] "):
            blocks.append(("checkbox", (line.startswith("- [x] "), line[6:].strip())))
        elif re.match(r"^\d+[.)]\s+", line):
            match = re.match(r"^(\d+)[.)]\s+(.*)$", line)
            blocks.append(("ordered", (match.group(1), match.group(2))))
        elif line.startswith(("- ", "* ", "+ ")):
            blocks.append(("bullet", line[2:].strip()))
        elif line.startswith("> "):
            blocks.append(("quote", line[2:].strip()))
        elif re.fullmatch(r"[-*_]{3,}", line):
            blocks.append(("rule", ""))
        elif not line:
            blocks.append(("blank", ""))
        else:
            blocks.append(("para", line))
    return blocks


def _pdf_safe(text: str) -> str:
    """Convert text to printable ASCII for FPDF's built-in Helvetica fonts."""
    normalized = unicodedata.normalize("NFKD", str(text))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _plain_markdown(text: str) -> str:
    """Remove Markdown and turn common LaTeX into readable printable notation."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(`{1,3})(.*?)\1", r"\2", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    # Helvetica in the PDF exporter is ASCII-only. Keep equations legible by
    # converting frequent LaTeX commands before unsupported glyphs are removed.
    text = re.sub(r"\\(?:\[|\]|\(|\))", "", text)
    text = text.replace("$$", "").replace("\\$", "$")
    text = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/ (\2)", text)
    text = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", text)
    text = re.sub(r"\\(?:text|mathrm|mathbf|mathit)\s*\{([^{}]*)\}", r"\1", text)
    latex_symbols = {
        r"\\times": " x ", r"\\cdot": " * ", r"\\div": " / ",
        r"\\pm": " +/- ", r"\\leq?": " <= ", r"\\geq?": " >= ",
        r"\\neq": " != ", r"\\approx": " ~= ", r"\\infty": "infinity",
        r"\\pi": "pi", r"\\theta": "theta", r"\\alpha": "alpha",
        r"\\beta": "beta", r"\\gamma": "gamma", r"\\Delta": "Delta",
        r"\\sum": "sum", r"\\prod": "product", r"\\int": "integral",
        r"\\rightarrow|\\to": " -> ", r"\\left|\\right": "",
    }
    for pattern, replacement in latex_symbols.items():
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\\(?:begin|end)\{[^{}]+\}", "", text)
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)
    return _pdf_safe(text.replace("\\$", "$"))


def export_notes_pdf(notes_md: str, topic: str, username: str, output_dir: str) -> str:
    """Export Markdown notes to a styled PDF. Falls back to UTF-8 text if needed."""
    os.makedirs(output_dir, exist_ok=True)
    safe_topic = re.sub(r"[^\w\s-]", "", topic).replace(" ", "_")[:40] or "Study_Notes"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"LearnOrbit_Notes_{safe_topic}_{timestamp}.pdf")

    try:
        from fpdf import FPDF, XPos, YPos

        class NotesPDF(FPDF):
            def header(self):
                # A restrained brand accent replaces the old page-sized watermark.
                self.set_fill_color(79, 70, 229)
                self.rect(0, 0, 210, 3, "F")
                self.set_y(8)
                self.set_font("Helvetica", "B", 9)
                self.set_text_color(67, 56, 202)
                self.cell(95, 6, "LEARNORBIT  /  STUDY NOTES")
                self.set_font("Helvetica", "", 8)
                self.set_text_color(107, 114, 128)
                self.cell(0, 6, _pdf_safe(topic), align="R")
                self.set_draw_color(226, 232, 240)
                self.set_line_width(0.3)
                self.line(self.l_margin, 17, 210 - self.r_margin, 17)
                self.set_y(23)

            def footer(self):
                self.set_y(-14)
                self.set_draw_color(226, 232, 240)
                self.set_line_width(0.3)
                self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
                self.set_y(-11)
                self.set_font("Helvetica", "", 8)
                self.set_text_color(107, 114, 128)
                self.cell(95, 5, "Prepared for " + _pdf_safe(username))
                self.cell(0, 5, f"Page {self.page_no()}", align="R")

        pdf = NotesPDF()
        pdf.set_margins(17, 23, 17)
        pdf.set_auto_page_break(auto=True, margin=19)
        pdf.add_page()

        # Clear, compact title treatment with useful metadata.
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(31, 41, 55)
        pdf.multi_cell(0, 10, _pdf_safe(topic), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 6, f"STUDY GUIDE  |  {datetime.utcnow().strftime('%d %B %Y')}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)
        pdf.set_fill_color(79, 70, 229)
        pdf.rect(pdf.l_margin, pdf.get_y(), 22, 1.2, "F")
        pdf.ln(6)

        blocks = _md_to_text_blocks(notes_md)
        # The generated Markdown begins with the topic heading, already shown above.
        if blocks and blocks[0][0] == "h1":
            blocks = blocks[1:]

        body_width = 210 - pdf.l_margin - pdf.r_margin
        for btype, content in blocks:
            if btype == "h1":
                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 16)
                pdf.set_text_color(49, 46, 129)
                pdf.multi_cell(0, 8, _plain_markdown(content), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)
            elif btype == "h2":
                if pdf.get_y() > 255:
                    pdf.add_page()
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(55, 48, 163)
                pdf.set_fill_color(238, 242, 255)
                pdf.multi_cell(body_width, 7.5, "  " + _plain_markdown(content),
                               fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1.5)
            elif btype == "h3":
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(67, 56, 202)
                pdf.multi_cell(0, 6, _plain_markdown(content), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif btype in ("bullet", "ordered", "checkbox"):
                pdf.set_font("Helvetica", "", 9.5)
                pdf.set_text_color(31, 41, 55)
                if btype == "checkbox":
                    checked, text = content
                    prefix = "[x] " if checked else "[ ] "
                elif btype == "ordered":
                    number, text = content
                    prefix = f"{number}. "
                else:
                    prefix = "- "
                    text = content
                pdf.set_x(pdf.l_margin + 3)
                pdf.multi_cell(body_width - 3, 5.8, prefix + _plain_markdown(text),
                               new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif btype == "quote":
                pdf.set_font("Helvetica", "I", 9.5)
                pdf.set_text_color(55, 65, 81)
                pdf.set_fill_color(249, 250, 251)
                pdf.set_x(pdf.l_margin + 3)
                pdf.multi_cell(body_width - 3, 6, _plain_markdown(content), fill=True,
                               new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif btype == "rule":
                pdf.ln(2)
                pdf.set_draw_color(203, 213, 225)
                pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
                pdf.ln(3)
            elif btype == "para":
                clean = _plain_markdown(content)
                if clean.strip():
                    pdf.set_font("Helvetica", "", 9.5)
                    pdf.set_text_color(31, 41, 55)
                    pdf.multi_cell(0, 5.8, clean, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(1)
            elif btype == "blank":
                pdf.ln(1.5)

        pdf.output(filepath)
        return filepath

    except ImportError:
        txt_path = filepath.replace(".pdf", ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"LearnOrbit Study Notes\nTopic: {topic}\nLearner: {username}\n")
            f.write(f"Generated: {datetime.utcnow()}\n\n{notes_md}")
        return txt_path
    except Exception as e:
        raise RuntimeError(f"PDF generation failed: {e}")
