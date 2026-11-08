#!/usr/bin/env python3
"""Build the illustrated EPUB of *Ticket to Hell via Dieppe*.

Run from anywhere:   python "EPUB Build/build_epub.py"
Needs Python 3.8+ and Pillow (pip install pillow). Nothing else.

Inputs (paths relative to the book folder, i.e. the parent of this script's folder):
  TXT - Cleaned/*.txt          the corrected text
  Images/*.jpg, images.json    the images, titles, captions and transcriptions
  EPUB Build/placements.json   where each image goes (edit this to move an image)
  EPUB Build/style.css         the stylesheet
  Book Cover.png               the cover artwork (2:3 portrait)
Output:
  Ticket to Hell via Dieppe - Illustrated.epub
  or, with --no-images, Ticket to Hell via Dieppe - Text Only.epub
  (same text and cover; no pictures, captions or the photo appendix)
  --out PATH writes to PATH instead.
"""
import html, io, json, re, sys, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TXT = ROOT / "TXT - Cleaned"
IMG = ROOT / "Images"
COVER_FILE = "Book Cover.png"
NO_IMAGES = "--no-images" in sys.argv[1:]
EDITION = "Text Only" if NO_IMAGES else "Illustrated"
_args = sys.argv[1:]
# --out PATH writes the EPUB somewhere else (build_web.py uses this so the committed EPUB isn't touched).
OUT = Path(_args[_args.index("--out") + 1]) if "--out" in _args else ROOT / f"Ticket to Hell via Dieppe - {EDITION}.epub"
TITLE = "Ticket to Hell via Dieppe"
SUBTITLE = "From a Prisoner’s Wartime Log, 1942–1945"
AUTHOR = "A. Robert Prouse"
BOOK_ID = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "ticket-to-hell-via-dieppe-" + EDITION.lower()))
MAX_PHOTO = 1600     # longest side for photos and drawings
MAX_DOC = 2000       # longest side for documents (keeps handwriting legible)

e = lambda s: html.escape(s, quote=True)


def read(name):
    return (TXT / f"{name}.txt").read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def paras(s):
    return [" ".join(p.split("\n")).strip() for p in re.split(r"\n\s*\n", s) if p.strip()]


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("‘", "'")).strip().lower()


# ---------------------------------------------------------------- images
meta = {m["id"]: m for m in json.loads((IMG / "images.json").read_text(encoding="utf-8"))}
placements = json.loads((HERE / "placements.json").read_text(encoding="utf-8"))
media = {}   # epub path -> bytes


def add_image(fid):
    m = meta[fid]
    im = Image.open(ROOT / m["file"])
    im = im.convert("L") if im.mode in ("L", "1", "LA") else im.convert("RGB")
    limit = MAX_DOC if m["type"] in ("document", "map") else MAX_PHOTO
    if max(im.size) > limit:
        r = limit / max(im.size)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85, optimize=True, progressive=True)
    path = f"images/{fid}.jpg"
    media[path] = b.getvalue()
    return path


def figure_html(fid):
    m = meta[fid]
    title = m["title"]
    if m["type"] == "sidebar":          # typeset box: set as text, not a picture
        return sidebar_html(m)
    if NO_IMAGES:
        return f'<span id="fig-{fid}"></span>'
    src = add_image(fid)
    cap = m.get("caption") or ""
    if cap.startswith("(Same caption"):
        cap = ""
    capline = e(cap) if cap else f"<span class=\"figtitle\">{e(title)}</span>"
    out = [f'<figure id="fig-{fid}" class="{e(m["type"])}">',
           f'<img src="../{src}" alt="{e(title)}"/>',
           f"<figcaption>{capline}"]
    if m.get("transcription") and fid != "07-08":
        out.append(f'<span class="transcription"><span class="label">Transcription: </span>{e(m["transcription"])}</span>')
    out.append("</figcaption></figure>")
    return "\n".join(out)


def sidebar_html(m):
    t = m["transcription"]
    head1, rest = t.split(": ", 1)
    list1, rest = rest.split(". REMEMBER: ", 1)
    list2, bucket = rest.split(". The ‘Old Wooden Bucket’", 1)
    return (f'<aside class="sidebar" id="fig-{m["id"]}"><h3>POW Amusements &amp; Pastimes</h3>'
            f"<p>{e(list1)}</p><h3>Remember</h3><p>{e(list2)}</p>"
            f"<p>The ‘Old Wooden Bucket’{e(bucket)}</p></aside>")


def place(section, blocks):
    """blocks: list of (normalized paragraph text, html). Insert figures per placements.json."""
    items = [p for p in placements if p["section"] == section]
    after = {i: [] for i in range(-1, len(blocks))}
    for p in items:
        if p.get("at") == "start":
            idx = -1
        elif p.get("at") == "end":
            idx = len(blocks) - 1
        else:
            key = norm(p["after"])
            hits = [i for i, (t, _) in enumerate(blocks) if key in t]
            if not hits:
                sys.exit(f"placements.json: {p['id']}: text not found in {section}: {p['after']!r}")
            idx = hits[0]
        after[idx].append(figure_html(p["id"]))
    out = after[-1][:]
    for i, (_, h) in enumerate(blocks):
        out.append(h)
        out.extend(after[i])
    return "\n".join(out)


# ---------------------------------------------------------------- sections
docs = []   # (filename, title, body_html, epub_type)


def chapter(name, fname):
    ps = paras(read(name))
    if ps[0].startswith("Chapter"):
        num, title, body = ps[0], ps[1], ps[2:]
        head = f'<h1><span class="chapnum">{e(num)}</span>{e(title)}</h1>'
        toc = f"{num}: {title}"
    else:
        title, body = ps[0], ps[1:]
        head, toc = f"<h1>{e(title)}</h1>", title
    blocks = [(norm(p), f"<p>{e(p)}</p>") for p in body]
    docs.append((fname, toc, head + "\n" + place(name, blocks), "chapter"))


# front matter
fn = read("Front Notes and Contents").split("\n")
ded1, ded2 = " ".join(fn[0:3]), " ".join(fn[3:5])
copyright_lines = " ".join(fn[7:11]).replace(" - ", " — ")
docs.append(("title.xhtml", "Title Page",
             f'<div class="titlepage"><p class="t1">Ticket to Hell</p><p class="t2">via Dieppe</p>'
             f'<p class="sub">{e(SUBTITLE)}</p><p class="author">{e(AUTHOR)}</p></div>', "titlepage"))
docs.append(("copyright.xhtml", "Copyright",
             f'<div class="copyright"><p>{e(fn[6])}</p><p>{e(copyright_lines)}</p>'
             f"<p>First published in 1982 by Van Nostrand Reinhold Publishers, Toronto, "
             f"and Webb &amp; Bower (Publishers) Limited, Exeter.</p></div>", "copyright-page"))
docs.append(("dedication.xhtml", "Dedication",
             f'<div class="dedication"><p>{e(ded1)}</p><p>{e(ded2)}</p></div>', "dedication"))

chapter("Prologue", "prologue.xhtml")
for i, n in enumerate(["1 - A Raid on Dieppe", "2 - Limping Towards Germany", "3 - Niederorschel Work Kommando 1049",
                       "4 - The Escape of Janek Mrachek", "5 - If at First...", "6 - The Castle on the Hill",
                       "7 - Passing the Time", "8 - The War Catches Up", "9 - Forced March to Liberation"], 1):
    chapter(n, f"chapter{i:02d}.xhtml")
chapter("Epilogue", "epilogue.xhtml")

# Barbed-Wire Ballads
TITLE_RE = re.compile(r"^(‘[A-Z][A-Z ,!?’'\-—.]*[A-Z?’]’?|MISADVENTURE)$")
bp = re.split(r"\n\s*\n", read("Barbed-Wire Ballads"))
body = ["<h1>Barbed-Wire Ballads</h1>"]
for b in bp[1:]:
    lines = [l for l in b.split("\n") if l.strip()]
    if len(lines) == 1 and not TITLE_RE.match(lines[0].strip()):
        body.append(f"<p class=\"note\">{e(lines[0])}</p>")
        continue
    verse = []
    i = 0
    while i < len(lines):
        l = lines[i].strip()
        if TITLE_RE.match(l):
            if verse: body.append('<p class="verse">' + "<br/>".join(map(e, verse)) + "</p>"); verse = []
            body.append(f"<h3>{e(l)}</h3>")
        elif l.startswith("Sign Reads"):
            if verse: body.append('<p class="verse">' + "<br/>".join(map(e, verse)) + "</p>"); verse = []
            rest = " ".join(x.strip() for x in lines[i:])
            a, _, c = rest.partition(" (")
            body.append(f'<p class="note"><i>Sign reads:</i>{e(a[len("Sign Reads:"):])}</p>')
            if c: body.append(f'<p class="note">({e(c)}</p>')
            break
        else:
            verse.append(l)
        i += 1
    if verse:
        body.append('<p class="verse">' + "<br/>".join(map(e, verse)) + "</p>")
docs.append(("ballads.xhtml", "Appendix: Barbed-Wire Ballads", "\n".join(body), "appendix"))

# End Notes: German Orders, Air Raids, A Note on Photos, Organized Compassion
en = read("End Notes")
parts = re.split(r"\n\n\n(?=(?:Air Raids|A Note on Photos, Mementos and Artifacts|Organized Compassion)\n)", en)
go, ar, note, oc = [p.strip() for p in parts]

body = ["<h1>German Orders</h1>"]
for blk in re.split(r"\n\s*\n", go.split("\n", 1)[1]):
    lines = [l for l in blk.split("\n") if l.strip()]
    nums = [l for l in lines if re.match(r"^\d+\. ", l)]
    if nums:
        body.append(f'<p class="doc-head">{e(lines[0])}</p><ol class="orders">' +
                    "".join(f"<li>{e(re.sub(r'^\d+\. ', '', l))}</li>" for l in nums) + "</ol>")
        for l in lines[len(nums) + 1:]:
            body.append(f'<p class="sig">{e(l)}</p>')
        continue
    for l in lines:
        if re.match(r"^(Signed|Ober Wehrmacht|Unteroffizier)", l):
            body.append(f'<p class="sig">{e(l)}</p>')
        elif l.endswith(":") or l in ("NOTICE", "‘BUT’", "‘WARNING’"):
            body.append(f'<p class="doc-head">{e(l)}</p>')
        else:
            body.append(f'<p class="doc">{e(l)}</p>')
docs.append(("orders.xhtml", "Appendix: German Orders", "\n".join(body), "appendix"))

body = ["<h1>Air Raids</h1>"]
pre, daily = ar.split("Example of March, 1945", 1)
for x in re.split(r"\n\s*\n", pre.split("\n", 1)[1].strip()):
    lines = x.split("\n")
    if lines[0] in ("AIR RAIDS (Comparison)",):
        body.append("<h2>Comparison</h2>"); continue
    if lines[0].startswith("Example Months"):
        body.append(f"<table class=\"raids\"><caption>{e(lines[0])}</caption>" +
                    "".join("<tr><td>{}</td><td class=\"n\">{}</td></tr>".format(*map(e, re.split(r"\s{2,}", l.strip())))
                            for l in lines[1:]) + "</table>")
        continue
    first, _, rest = lines[0].partition(":")
    if first in ("ENGLAND", "GERMANY"):
        body.append(f"<h3>{first.title()}</h3>")
        lines = lines[1:]
    body.append(f"<p>{e(' '.join(lines))}</p>")
dl = daily.strip().split("\n")
rows = []
for l in dl:
    m = re.match(r"^(?:March)?\s*(\d+)\s*(\d*)\s*(\d*)\s*(\d*)\s*$", l)
    if m: rows.append(m.groups())
total = [l for l in dl if l.startswith("March, 1945 Total")][0]
body.append(f"<table class=\"raids daily\"><caption>Example of March, 1945, in Mühlhausen, Thüringen</caption>"
            "<tr><th>March</th><th>Raids</th><th>Hours</th><th>Min.</th></tr>" +
            "".join("<tr>" + "".join(f"<td class=\"n\">{c}</td>" for c in r) + "</tr>" for r in rows) +
            f"</table><p class=\"total\">{e(total)}</p>")
docs.append(("airraids.xhtml", "Appendix: Air Raids", "\n".join(body), "appendix"))

npar = paras(note)
blocks = [(norm(p), f"<p>{e(p)}</p>") for p in npar[1:]]
photos_html = f"<h1>{e(npar[0])}</h1>\n" + place("Note on Photos", blocks)
if not NO_IMAGES:   # the note is about the pictures, so it only belongs in the illustrated edition
    docs.append(("photos.xhtml", "Appendix: A Note on Photos, Mementos and Artifacts", photos_html, "appendix"))
opar = paras(oc)
blocks = [(norm(p), f"<p>{e(p)}</p>") for p in opar[1:]]
docs.append(("compassion.xhtml", "Appendix: Organized Compassion",
             f"<h1>{e(opar[0])}</h1>\n" + place("Organized Compassion", blocks), "appendix"))

# every placement must have been used exactly once
used = set(re.findall(r'id="fig-(\d\d-\d\d)"', "".join(d[2] for d in docs) + photos_html))
missing = {p["id"] for p in placements} - used
if missing:
    sys.exit(f"Images not placed: {sorted(missing)}")

# ---------------------------------------------------------------- cover
# Full-colour cover art, used at its own size (no upscaling). Pad to a 2:3 portrait if it isn't one.
cover = Image.open(ROOT / COVER_FILE).convert("RGB")
if abs(cover.width / cover.height - 2 / 3) > 0.01:
    W = max(cover.width, round(cover.height * 2 / 3)); H = round(W * 3 / 2)
    padded = Image.new("RGB", (W, H), "white")
    padded.paste(cover, ((W - cover.width) // 2, (H - cover.height) // 2))
    cover = padded
b = io.BytesIO(); cover.save(b, "JPEG", quality=90, optimize=True); media["images/cover.jpg"] = b.getvalue()

# ---------------------------------------------------------------- package
def xhtml(title, body, etype):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en-CA" xml:lang="en-CA">\n'
            f'<head><meta charset="utf-8"/><title>{e(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="../style.css"/></head>\n'
            f'<body epub:type="{etype}"><section epub:type="{etype}">\n{body}\n</section></body></html>\n')


cover_x = xhtml("Cover", '<div class="cover"><img src="../images/cover.jpg" alt="Ticket to Hell via Dieppe, by A. Robert Prouse"/></div>', "cover")
toc_skip = {"title.xhtml", "copyright.xhtml"}
nav_items = "".join(f'<li><a href="text/{f}">{e(t)}</a></li>' for f, t, _, _ in docs if f not in toc_skip)
nav = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
       '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en-CA" xml:lang="en-CA">'
       '<head><meta charset="utf-8"/><title>Contents</title><link rel="stylesheet" type="text/css" href="style.css"/></head>'
       f'<body><nav epub:type="toc" id="toc"><h1>Contents</h1><ol class="toc">{nav_items}</ol></nav>'
       '<nav epub:type="landmarks" hidden="hidden"><ol>'
       '<li><a epub:type="cover" href="text/cover.xhtml">Cover</a></li>'
       '<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>'
       '<li><a epub:type="bodymatter" href="text/prologue.xhtml">Begin Reading</a></li></ol></nav></body></html>')
ncx_pts = "".join(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{e(t)}</text></navLabel><content src="text/{f}"/></navPoint>'
                  for i, (f, t, _, _) in enumerate([d for d in docs if d[0] not in toc_skip], 1))
ncx = ('<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
       f'<head><meta name="dtb:uid" content="{BOOK_ID}"/></head><docTitle><text>{e(TITLE)}</text></docTitle>'
       f"<navMap>{ncx_pts}</navMap></ncx>")

modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            '<item id="css" href="style.css" media-type="text/css"/>',
            '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
            '<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>']
spine = ['<itemref idref="cover" linear="yes"/>']
for f, _, _, _ in docs:
    i = f.replace(".xhtml", "")
    manifest.append(f'<item id="{i}" href="text/{f}" media-type="application/xhtml+xml"/>')
    spine.append(f'<itemref idref="{i}"/>')
    if f == "dedication.xhtml":
        spine.append('<itemref idref="nav"/>')
for p in sorted(media):
    if p != "images/cover.jpg":
        iid = "img_" + p.split("/")[1].replace(".jpg", "").replace("-", "_")
        manifest.append(f'<item id="{iid}" href="{p}" media-type="image/jpeg"/>')
opf = ('<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en-CA">'
       '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
       f'<dc:identifier id="bookid">{BOOK_ID}</dc:identifier><dc:title>{e(TITLE)}</dc:title>'
       f'<dc:creator>{e(AUTHOR)}</dc:creator><dc:language>en-CA</dc:language><dc:date>1982</dc:date>'
       f'<dc:description>{e(SUBTITLE)}. {EDITION} edition.</dc:description>'
       f'<dc:rights>Copyright © A. Robert Prouse 1982. All rights reserved.</dc:rights>'
       f'<meta property="dcterms:modified">{modified}</meta><meta name="cover" content="cover-image"/></metadata>'
       f'<manifest>{"".join(manifest)}</manifest><spine toc="ncx">{"".join(spine)}</spine></package>')

with zipfile.ZipFile(OUT, "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    zi = lambda n: zipfile.ZipInfo(n, date_time=(2026, 1, 1, 0, 0, 0))
    def w(n, data): z.writestr(zi(n), data, compress_type=zipfile.ZIP_DEFLATED)
    w("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
      '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    w("OEBPS/content.opf", opf)
    w("OEBPS/nav.xhtml", nav)
    w("OEBPS/toc.ncx", ncx)
    w("OEBPS/style.css", (HERE / "style.css").read_text(encoding="utf-8"))
    w("OEBPS/text/cover.xhtml", cover_x)
    for f, t, b_, et in docs:
        w(f"OEBPS/text/{f}", xhtml(t, b_, et))
    for p, data in media.items():
        z.writestr(zipfile.ZipInfo("OEBPS/" + p, date_time=(2026, 1, 1, 0, 0, 0)), data, compress_type=zipfile.ZIP_STORED)

print(f"Wrote {OUT.name}: {len(docs)} sections, {len(media) - 1} images, {OUT.stat().st_size / 1e6:.1f} MB")
