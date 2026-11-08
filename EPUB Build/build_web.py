#!/usr/bin/env python3
"""Build the online reading edition of *Ticket to Hell via Dieppe* into site/read/.

Run from anywhere:   python "EPUB Build/build_web.py"

The pages are made from the illustrated EPUB, so the text, images, captions and placements always
match it. The script builds that EPUB into a temporary folder first (the committed EPUB is not
touched), then turns each section into a web page.

Needs:  Python 3.8+ and Pillow (pip install pillow)
Output: site/read/
          index.html          contents page (cover, dedication, contents, copyright)
          <section>.html      one page per section: prologue, chapter-1 ... chapter-9, epilogue, appendices
          gallery.html        every picture, linked to its place in the text
          images/ID.jpg       images sized for the page (1200 px longest side)
          images/large/ID.jpg the EPUB's larger copies, opened when a picture is tapped
          images/thumbs/ID.jpg gallery thumbnails
        reader.css and reader.js in site/read/ are hand-written and are not touched.
Commit site/read/ afterwards; the Pages workflow publishes it on the next push to main.
"""
import html, io, json, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "site" / "read"
IMG = ROOT / "Images"
BASE = "https://tth-dieppe.github.io/ticket-to-hell/"
BOOK = "Ticket to Hell via Dieppe"
DISPLAY = 1200       # longest side of the image shown in the page
THUMB = 480          # longest side of a gallery thumbnail
HAND_WRITTEN = {"reader.css", "reader.js"}

# Friendlier page names than the EPUB's file names.
SLUGS = {"prologue": "prologue", "epilogue": "epilogue", "ballads": "barbed-wire-ballads",
         "orders": "german-orders", "airraids": "air-raids", "photos": "note-on-photos",
         "compassion": "organized-compassion"}
SLUGS.update({f"chapter{i:02d}": f"chapter-{i}" for i in range(1, 10)})

e = lambda s: html.escape(s, quote=True)

# ---------------------------------------------------------------- 1. build the EPUB to a temp folder
tmp = Path(tempfile.mkdtemp(prefix="tthvd_web_"))
epub = tmp / "book.epub"
subprocess.run([sys.executable, str(HERE / "build_epub.py"), "--out", str(epub)], check=True)
with zipfile.ZipFile(epub) as z:
    z.extractall(tmp / "x")
oebps = tmp / "x" / "OEBPS"


def body_of(name):
    x = (oebps / "text" / name).read_text(encoding="utf-8")
    b = re.search(r"<body[^>]*>(.*)</body>", x, re.S).group(1)
    return re.sub(r"</?section[^>]*>", "", b).strip()


def text_of(h):
    return html.unescape(re.sub(r"<[^>]+>", "", h)).strip()


nav = (oebps / "nav.xhtml").read_text(encoding="utf-8")
toc = re.findall(r'<li><a href="text/([^"]+)\.xhtml">(.*?)</a></li>', re.search(r'<nav epub:type="toc".*?</nav>', nav, re.S).group(0))
sections = [(SLUGS[f], f, html.unescape(t)) for f, t in toc if f in SLUGS]   # (slug, epub name, title)
missing = [f for f, _ in toc if f not in SLUGS and f != "dedication"]
if missing:
    sys.exit(f"build_web.py: no page name for EPUB section(s) {missing}; add them to SLUGS")

meta = {m["id"]: m for m in json.loads((IMG / "images.json").read_text(encoding="utf-8"))}

# ---------------------------------------------------------------- 2. images
OUT.mkdir(parents=True, exist_ok=True)
written = set()


def save(rel, data):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.read_bytes() != data:
        p.write_bytes(data)
    written.add(p.resolve())


def jpeg(im, limit, quality):
    if max(im.size) > limit:
        r = limit / max(im.size)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=quality, optimize=True, progressive=True)
    return b.getvalue(), im.size


sizes = {}   # id -> (w, h) of the display image


def make_images(fid):
    if fid in sizes:
        return
    im = Image.open(ROOT / meta[fid]["file"])
    im = im.convert("L") if im.mode in ("L", "1", "LA") else im.convert("RGB")
    data, sizes[fid] = jpeg(im, DISPLAY, 80)
    save(f"images/{fid}.jpg", data)
    save(f"images/thumbs/{fid}.jpg", jpeg(im, THUMB, 75)[0])
    save(f"images/large/{fid}.jpg", (oebps / "images" / f"{fid}.jpg").read_bytes())


FIG_RE = re.compile(r'<figure id="fig-([\w-]+)" class="([\w-]+)">\s*<img src="\.\./images/[\w-]+\.jpg" alt="([^"]*)"/>')


def web_figures(body):
    def sub(m):
        fid, kind, alt = m.groups()
        make_images(fid)
        w, h = sizes[fid]
        return (f'<figure id="fig-{fid}" class="{kind}">'
                f'<a class="zoom" href="images/large/{fid}.jpg" aria-label="Enlarge: {alt}">'
                f'<img src="images/{fid}.jpg" alt="{alt}" width="{w}" height="{h}" loading="lazy" decoding="async"></a>')
    body = FIG_RE.sub(sub, body)
    if "../images/" in body:
        sys.exit("build_web.py: an image in the EPUB was not converted; check FIG_RE against build_epub.py's figure_html()")
    return body.replace("<br/>", "<br>")


# ---------------------------------------------------------------- 3. page template
HEAD_SCRIPT = ('<script>try{var d=document.documentElement,t=localStorage.getItem("tth-theme"),'
               's=localStorage.getItem("tth-size");if(t)d.dataset.theme=t;if(s)d.style.setProperty("--scale",s)}catch(e){}</script>')

SETTINGS = """<div class="settings" id="settings" hidden>
  <div class="setting" role="group" aria-label="Text size">
    <span class="label">Text size</span>
    <button type="button" data-size="-1" aria-label="Smaller text">A−</button>
    <button type="button" data-size="0" aria-label="Default text size">A</button>
    <button type="button" data-size="1" aria-label="Larger text">A+</button>
  </div>
  <div class="setting" role="group" aria-label="Colours">
    <span class="label">Colours</span>
    <button type="button" data-theme-set="">Auto</button>
    <button type="button" data-theme-set="light">Light</button>
    <button type="button" data-theme-set="dark">Dark</button>
  </div>
</div>"""

FOOTER = """<footer class="site-footer">
  <p>Copyright © 1982 A. Robert Prouse. Shared under the
    <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/" rel="license">Creative Commons Attribution-NonCommercial-NoDerivatives 4.0</a>
    licence.</p>
  <p><a href="../">About the book and downloads</a> · <a href="https://github.com/tth-dieppe/ticket-to-hell">Source files on GitHub</a></p>
</footer>"""


def page(slug, title, desc, main, kind="chapter", image=None):
    url = BASE + "read/" + ("" if slug == "index" else f"{slug}.html")
    full = BOOK if slug == "index" else f"{title} · {BOOK}"
    og_img = image or BASE + "images/social.jpg"
    og_size = "" if image else '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
    return f"""<!doctype html>
<html lang="en-CA">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="{'book' if slug == 'index' else 'article'}">
<meta property="og:site_name" content="{BOOK}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{og_img}">{og_size}
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" href="../images/favicon.png">
<link rel="apple-touch-icon" href="../images/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Zilla+Slab:wght@600;700&display=swap">
<link rel="stylesheet" href="reader.css">
{HEAD_SCRIPT}
<script src="reader.js" defer></script>
</head>
<body class="is-{kind}" data-page="{slug}" data-title="{e(title)}">
<a class="skip-link" href="#main">Skip to text</a>
<header class="bar">
  <div class="bar-in">
    <a class="home" href="./">Ticket to Hell <span>via Dieppe</span></a>
    <nav class="bar-nav" aria-label="Book">
      <a href="./#contents">Contents</a>
      <a href="gallery.html">Pictures</a>
      <button type="button" class="settings-btn" aria-expanded="false" aria-controls="settings" aria-label="Reading settings">Aa</button>
    </nav>
  </div>
  <div class="progress" aria-hidden="true"><span></span></div>
</header>
{SETTINGS}
<main id="main">
{main}
</main>
{FOOTER}
</body>
</html>
"""


def write(slug, data):
    save(f"{slug}.html", data.encode("utf-8"))


# ---------------------------------------------------------------- 4. reading pages
figures_by_page = []   # (slug, title, [ids])
for i, (slug, name, title) in enumerate(sections):
    body = web_figures(body_of(f"{name}.xhtml"))
    ids = re.findall(r'<figure id="fig-([\w-]+)"', body)
    figures_by_page.append((slug, title, ids))
    first_p = re.search(r"<p>(.*?)</p>", body, re.S)
    desc = text_of(first_p.group(1)) if first_p else title
    if len(desc) > 160:
        desc = desc[:157].rsplit(" ", 1)[0] + "…"
    prev = sections[i - 1] if i else None
    nxt = sections[i + 1] if i + 1 < len(sections) else None
    pn = ['<nav class="pager" aria-label="Previous and next">']
    pn.append(f'<a class="prev" rel="prev" href="{prev[0]}.html"><span>Previous</span>{e(prev[2])}</a>' if prev
              else '<a class="prev" href="./"><span>Previous</span>Contents</a>')
    pn.append(f'<a class="next" rel="next" href="{nxt[0]}.html"><span>Next</span>{e(nxt[2])}</a>' if nxt
              else '<a class="next" href="gallery.html"><span>Next</span>All the pictures</a>')
    pn.append("</nav>")
    image = BASE + f"read/images/{ids[0]}.jpg" if ids else None
    write(slug, page(slug, title, desc, f'<article class="text">\n{body}\n</article>\n' + "".join(pn), image=image))

# ---------------------------------------------------------------- 5. contents page
cover_meta = '<img src="../images/cover.jpg" srcset="../images/cover.jpg 400w, ../images/cover@2x.jpg 800w" sizes="(min-width: 800px) 260px, 60vw" width="400" height="600" alt="Cover of Ticket to Hell via Dieppe, by A. Robert Prouse">'
dedication = body_of("dedication.xhtml")
copyright_ = body_of("copyright.xhtml").replace('class="copyright"', 'class="copyright-note"')


def toc_item(slug, title):
    m = re.match(r"(Chapter \d+): (.*)", title)
    if m:
        return f'<li><a href="{slug}.html"><span class="num">{e(m.group(1))}</span>{e(m.group(2))}</a></li>'
    return f'<li><a href="{slug}.html">{e(title.replace("Appendix: ", ""))}</a></li>'


story = [s for s in sections if not s[2].startswith("Appendix")]
appx = [s for s in sections if s[2].startswith("Appendix")]
contents = f"""<div class="intro">
  <figure class="book-cover">{cover_meta}</figure>
  <div>
    <h1 class="book-title">Ticket to Hell <span>via Dieppe</span></h1>
    <p class="book-sub">From a Prisoner’s Wartime Log, 1942–1945</p>
    <p class="book-author">A. Robert Prouse</p>
    <p class="start"><a class="button primary" href="{sections[0][0]}.html" id="start">Start reading</a></p>
    <p class="continue" id="continue" hidden></p>
  </div>
</div>
{dedication}
<section id="contents" class="contents" aria-labelledby="contents-title">
  <h2 id="contents-title">Contents</h2>
  <ol class="toc">{"".join(toc_item(s, t) for s, _, t in story)}</ol>
  <h3>Appendices</h3>
  <ol class="toc">{"".join(toc_item(s, t) for s, _, t in appx)}</ol>
  <p class="gallery-link"><a href="gallery.html">All the photographs, drawings, documents and maps</a></p>
</section>
{copyright_}"""
write("index", page("index", BOOK, "Read Ticket to Hell via Dieppe online: a Canadian soldier’s secret diary of capture at Dieppe in 1942 and three years in German prison camps.", contents, kind="home"))

# ---------------------------------------------------------------- 6. gallery
g = ["<h1>Pictures</h1>",
     '<p class="lede">The photographs, drawings, documents and maps from the 1982 edition. Each one links to its place in the text.</p>']
count = 0
for slug, title, ids in figures_by_page:
    if not ids:
        continue
    g.append(f'<h2><a href="{slug}.html">{e(title)}</a></h2><ul class="thumbs">')
    for fid in ids:
        count += 1
        g.append(f'<li><a href="{slug}.html#fig-{fid}"><img src="images/thumbs/{fid}.jpg" alt="" loading="lazy" decoding="async">'
                 f'<span>{e(meta[fid]["title"])}</span></a></li>')
    g.append("</ul>")
write("gallery", page("gallery", "Pictures", "The photographs, drawings, documents and maps from Ticket to Hell via Dieppe.",
                      '<article class="gallery">\n' + "\n".join(g) + "\n</article>", kind="gallery"))

# ---------------------------------------------------------------- 7. remove anything left from an old build
for p in OUT.rglob("*"):
    if p.is_file() and p.resolve() not in written and p.name not in HAND_WRITTEN:
        p.unlink()
shutil.rmtree(tmp, ignore_errors=True)
print(f"Wrote site/read/: {len(sections)} reading pages, contents, gallery, {count} pictures")
