#!/usr/bin/env python3
"""Build the illustrated PDF of *Ticket to Hell via Dieppe* (6 x 9 in trade-paperback page).

Run from anywhere:   python "EPUB Build/build_pdf.py"

The PDF is made from the illustrated EPUB, so the text, images, captions and placements always
match it. This script rebuilds that EPUB first, then lays it out for print with Chromium.

Needs:  pip install pillow playwright pypdf reportlab
        python -m playwright install chromium
Output: Ticket to Hell via Dieppe - Illustrated.pdf (in the book folder)
"""
import io, re, subprocess, sys, tempfile, zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EPUB = ROOT / "Ticket to Hell via Dieppe - Illustrated.epub"
OUT = ROOT / "Ticket to Hell via Dieppe - Illustrated.pdf"
PAGE_W, PAGE_H = 6 * inch, 9 * inch

# 1. Rebuild the illustrated EPUB so the PDF matches it exactly.
subprocess.run([sys.executable, str(HERE / "build_epub.py")], check=True)

tmp = Path(tempfile.mkdtemp(prefix="tthvd_pdf_"))
with zipfile.ZipFile(EPUB) as z:
    z.extractall(tmp)
oebps = tmp / "OEBPS"
opf = (oebps / "content.opf").read_text(encoding="utf-8")
hrefs = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf))
spine = [hrefs[i] for i in re.findall(r'<itemref idref="([^"]+)"', opf)]

# Sections that get an entry in the PDF contents page (everything with an <h1>, except Contents itself).
SKIP_TOC = {"text/cover.xhtml", "text/title.xhtml", "text/copyright.xhtml", "text/dedication.xhtml", "nav.xhtml"}


def body_of(href):
    x = (oebps / href).read_text(encoding="utf-8")
    b = re.search(r"<body[^>]*>(.*)</body>", x, re.S).group(1)
    b = re.sub(r"</?section[^>]*>", "", b)
    return b.replace('src="../images/', f'src="{(oebps / "images").as_uri()}/')


def section_title(href):
    h = re.search(r"<h1>(.*?)</h1>", (oebps / href).read_text(encoding="utf-8"), re.S).group(1)
    h = re.sub(r'<span class="chapnum">(.*?)</span>', r"\1: ", h)
    return re.sub(r"<[^>]+>", "", h).replace("&amp;", "&").strip()


toc_entries = [(h, section_title(h)) for h in spine if h not in SKIP_TOC]

PRINT_CSS = """
@page { size: 6in 9in; margin: 0.75in 0.7in 0.85in 0.7in; }
@page :first { margin: 0; }
html { font-size: 10.5pt; }
body { margin: 0; }
.sec { break-before: page; }
.sec h1 { page-break-before: auto; margin-top: 0.9in; break-inside: avoid; }
h1 + figure img, h1 + figure.document img, h1 + figure.map img, h1 + figure.drawing img { max-height: 4.4in; }
.cover-page { width: 6in; height: 9in; display: flex; align-items: center; justify-content: center; }
.cover-page img { width: 6in; height: 9in; object-fit: contain; }
.titlepage { margin-top: 2in; }
.copyright { margin-top: 4.6in; }
.dedication { margin-top: 2.6in; }
figure { break-inside: avoid; page-break-inside: avoid; margin: 0.25in 0; }
figcaption { break-before: avoid; }
figure img { max-width: 100%; max-height: 6.2in; }
figure.document img, figure.map img { max-height: 6.6in; }
figure.cover img { max-height: 6.6in; }
aside.sidebar, table.raids, p.verse { break-inside: avoid; }
h1, h2, h3 { break-after: avoid; }
p { orphans: 2; widows: 2; }
ol.pdftoc { list-style: none; padding: 0; margin: 0; }
ol.pdftoc li { display: flex; margin: 0.35em 0; }
ol.pdftoc .t { flex: 0 1 auto; }
ol.pdftoc .dots { flex: 1 1 auto; border-bottom: 1px dotted #777; margin: 0 0.4em 0.3em; }
ol.pdftoc .p { flex: 0 0 auto; }
"""


def build_html(pages):
    css = (oebps / "style.css").read_text(encoding="utf-8") + PRINT_CSS
    parts = [f'<div class="cover-page"><img src="{(oebps / "images/cover.jpg").as_uri()}"/></div>']
    for href in spine:
        if href == "text/cover.xhtml":
            continue
        if href == "nav.xhtml":
            items = "".join(
                f'<li><span class="t">{t}</span><span class="dots"></span><span class="p">{pages.get(h, "")}</span></li>'
                for h, t in toc_entries)
            parts.append(f'<div class="sec"><h1>Contents</h1><ol class="pdftoc">{items}</ol></div>')
            continue
        parts.append(f'<div class="sec">{body_of(href)}</div>')
    return ('<!DOCTYPE html><html lang="en-CA"><head><meta charset="utf-8"/>'
            f"<title>Ticket to Hell via Dieppe</title><style>{css}</style></head><body>"
            + "\n".join(parts) + "</body></html>")


def render(html_text, out_pdf):
    src = tmp / "book.html"
    src.write_text(html_text, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(src.as_uri(), wait_until="networkidle")
        pg.pdf(path=str(out_pdf), prefer_css_page_size=True, print_background=True, outline=True, tagged=True)
        b.close()


def h1_pages(pdf_path):
    """0-based page index of each top-level heading, in document order, from Chromium's outline."""
    r = PdfReader(str(pdf_path))
    return [r.get_destination_page_number(o) for o in r.outline if not isinstance(o, list)]


# 2. First pass: lay out with blank page numbers to find where each section lands.
pass1 = tmp / "pass1.pdf"
render(build_html({}), pass1)
starts = h1_pages(pass1)                       # Contents, then each TOC entry
first_numbered = starts[1]                     # the Prologue is page 1
pages = {h: starts[i + 1] - first_numbered + 1 for i, (h, _) in enumerate(toc_entries)}

# 3. Second pass with real page numbers in the contents; check nothing moved.
pass2 = tmp / "pass2.pdf"
render(build_html(pages), pass2)
starts2 = h1_pages(pass2)
if starts2 != starts:
    sys.exit("Page layout shifted between passes; rerun or adjust the contents page.")

# 4. Add page numbers (from the Prologue on) and a clean bookmark list.
reader = PdfReader(str(pass2))
writer = PdfWriter()
for i, page in enumerate(reader.pages):
    if i >= first_numbered:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
        c.setFont("Times-Roman", 9)
        c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(i - first_numbered + 1))
        c.save()
        page.merge_page(PdfReader(buf).pages[0])
    writer.add_page(page)
writer.add_outline_item("Cover", 0)
writer.add_outline_item("Contents", starts2[0])
for (h, t), idx in zip(toc_entries, starts2[1:]):
    writer.add_outline_item(t, idx)
writer.add_metadata({"/Title": "Ticket to Hell via Dieppe", "/Author": "A. Robert Prouse",
                     "/Subject": "From a Prisoner’s Wartime Log, 1942–1945. Illustrated edition."})
with open(OUT, "wb") as f:
    writer.write(f)
print(f"Wrote {OUT.name}: {len(reader.pages)} pages, {OUT.stat().st_size / 1e6:.1f} MB")
