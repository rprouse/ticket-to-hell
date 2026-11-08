#!/usr/bin/env python3
"""Build the online reading edition of *Ticket to Hell via Dieppe* into site/read/.

Run from anywhere:   python "EPUB Build/build_web.py"

The pages are made from the illustrated EPUB, so the text, images, captions and placements always
match it. The script builds that EPUB into a temporary folder first (the committed EPUB is not
touched), then turns each section into a web page.

Needs:  Python 3.8+, Pillow and mutagen (pip install pillow mutagen)
Output: site/read/
          index.html          contents page (cover, dedication, contents, copyright)
          <section>.html      one page per section: prologue, chapter-1 ... chapter-9, epilogue, appendices
          gallery.html        every picture, linked to its place in the text
          images/ID.jpg       images sized for the page (1200 px longest side)
          images/large/ID.jpg the EPUB's larger copies, opened when a picture is tapped
          images/thumbs/ID.jpg gallery thumbnails
        site/listen/
          index.html          the audiobook player page
          tracks.js           the track list (titles and lengths read from the MP3 tags in Audiobook/)
        reader.css, reader.js and listen/player.js are hand-written and are not touched.
        The MP3s themselves are NOT copied: the Pages workflow copies Audiobook/*.mp3 into
        site/listen/audio/ when it deploys, so they aren't stored twice in the repository.
        --with-audio copies them there too, for previewing locally (that folder is git-ignored).
Commit site/read/ and site/listen/ afterwards; the Pages workflow publishes them on the next push to main.
"""
import html, io, json, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
from urllib.parse import quote
from PIL import Image
from mutagen.mp3 import MP3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "site" / "read"
IMG = ROOT / "Images"
BASE = "https://tth-dieppe.github.io/"
BOOK = "Ticket to Hell via Dieppe"
DISPLAY = 1200       # longest side of the image shown in the page
THUMB = 480          # longest side of a gallery thumbnail
HAND_WRITTEN = {"reader.css", "reader.js", "player.js"}
LISTEN = ROOT / "site" / "listen"
AUDIO = ROOT / "Audiobook"
AUDIO_URL = "/listen/audio/"     # where pages.yml puts the MP3s

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


# ---------------------------------------------------------------- 3. audiobook tracks
# Titles and lengths come from the MP3 tags, so the list always matches the files in Audiobook/.
tracks = []
for p in sorted(AUDIO.glob("*.mp3")):
    a = MP3(p)
    tracks.append({"f": p.name, "u": AUDIO_URL + quote(p.name), "t": str(a["TIT2"]), "d": round(a.info.length)})
if not tracks:
    sys.exit("build_web.py: no MP3s found in Audiobook/")

# Which tracks go with which reading page, by track number (the NN_ at the start of the file name).
TRACKS_FOR = {"prologue": [1], "epilogue": [11], "barbed-wire-ballads": list(range(12, 30)),
              "german-orders": [30], "air-raids": [31], "organized-compassion": [32]}
TRACKS_FOR.update({f"chapter-{i}": [i + 1] for i in range(1, 10)})
by_num = {int(t["f"].split("_", 1)[0]): i for i, t in enumerate(tracks)}
titles = {s: t for s, _, t in sections}
for slug, nums in TRACKS_FOR.items():
    for n in nums:
        if n not in by_num:
            sys.exit(f"build_web.py: no audiobook track {n:02d}_… for {slug}; check TRACKS_FOR")
        tracks[by_num[n]]["p"] = slug
    first = tracks[by_num[nums[0]]]["t"]
    if first != titles[slug]:     # catches a renumbered or reordered audiobook
        sys.exit(f"build_web.py: track {nums[0]:02d} is {first!r} but {slug} is {titles[slug]!r}; check TRACKS_FOR")


def hms(s):
    h, m = divmod(round(s / 60), 60)     # same rounding as player.js
    return f"{h} hr {m} min" if h else f"{max(1, m)} min"


def clock(s):
    h, rem = divmod(round(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ---------------------------------------------------------------- 4. page template
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
  <p><a href="/">About the book and downloads</a> · <a href="https://github.com/tth-dieppe/tth-dieppe.github.io">Source files on GitHub</a></p>
</footer>"""

PLAYER_SCRIPTS = '<script src="/listen/tracks.js" defer></script>\n<script src="/listen/player.js" defer></script>\n'


def page(path, slug, title, desc, main, kind="chapter", image=None, audio=False):
    """path: the page's address under the site root, e.g. 'read/chapter-1.html'. Links are root-relative."""
    url = BASE + path
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
<link rel="icon" type="image/png" href="/images/favicon.png">
<link rel="apple-touch-icon" href="/images/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Zilla+Slab:wght@600;700&display=swap">
<link rel="stylesheet" href="/read/reader.css">
{HEAD_SCRIPT}
<script src="/read/reader.js" defer></script>
{PLAYER_SCRIPTS if audio else ""}</head>
<body class="is-{kind}" data-page="{slug}" data-title="{e(title)}">
<a class="skip-link" href="#main">Skip to {'text' if kind != 'listen' else 'tracks'}</a>
<header class="bar">
  <div class="bar-in">
    <a class="home" href="/" title="About the book and downloads">Ticket to Hell <span>via Dieppe</span></a>
    <nav class="bar-nav" aria-label="Book">
      <a href="/read/#contents">Contents</a>
      <a href="/read/gallery.html" class="nav-pictures">Pictures</a>
      <a href="/listen/">Listen</a>
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


def save_to(base, rel, data):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.read_bytes() != data:
        p.write_bytes(data)
    written.add(p.resolve())


def write(slug, data):
    save(f"{slug}.html", data.encode("utf-8"))


def listen_button(slug):
    idx = [by_num[n] for n in TRACKS_FOR.get(slug, [])]
    if not idx:
        return ""
    total = sum(tracks[i]["d"] for i in idx)
    what = "the ballads" if len(idx) > 1 else ("this chapter" if slug.startswith("chapter") else "this section")
    return (f'<div class="listen-here"><button type="button" class="listen-btn" data-tracks="{",".join(map(str, idx))}" hidden>'
            f'<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'
            f'<span class="lb-label">Listen to {what}</span> <span class="lb-len">· {hms(total)}</span></button></div>')


# ---------------------------------------------------------------- 5. reading pages
figures_by_page = []   # (slug, title, [ids])
for i, (slug, name, title) in enumerate(sections):
    body = web_figures(body_of(f"{name}.xhtml"))
    body = body.replace("</h1>", "</h1>\n" + listen_button(slug), 1)
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
    write(slug, page(f"read/{slug}.html", slug, title, desc, f'<article class="text">\n{body}\n</article>\n' + "".join(pn),
                     image=image, audio=slug in TRACKS_FOR))

# ---------------------------------------------------------------- 6. contents page
cover_meta = '<img src="/images/cover.jpg" srcset="/images/cover.jpg 400w, /images/cover@2x.jpg 800w" sizes="(min-width: 800px) 260px, 60vw" width="400" height="600" alt="Cover of Ticket to Hell via Dieppe, by A. Robert Prouse">'
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
    <p class="other-editions">Or <a href="/listen/">listen to the audiobook</a>, or <a href="/#downloads">download the ebook, PDF or MP3s</a> free.</p>
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
write("index", page("read/", "index", BOOK, "Read Ticket to Hell via Dieppe online: a Canadian soldier’s secret diary of capture at Dieppe in 1942 and three years in German prison camps.", contents, kind="home"))

# ---------------------------------------------------------------- 7. gallery
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
write("gallery", page("read/gallery.html", "gallery", "Pictures", "The photographs, drawings, documents and maps from Ticket to Hell via Dieppe.",
                      '<article class="gallery">\n' + "\n".join(g) + "\n</article>", kind="gallery"))

# ---------------------------------------------------------------- 8. listen page
GROUPS = [("The story", range(0, 12)), ("Barbed-Wire Ballads", range(12, 30)), ("Appendices", range(30, 33))]


def track_li(n):
    i = by_num[n]
    t = tracks[i]
    read = f'<a class="t-read" href="/read/{t["p"]}.html" aria-label="Read {e(t["t"])}">Read</a>' if t.get("p") and (n == TRACKS_FOR[t["p"]][0]) else ""
    if n == 0:
        read = '<a class="t-read" href="/read/" aria-label="Read the dedication">Read</a>'
    sub = " sub" if 12 < n < 30 else ""
    return (f'<li class="track{sub}" data-track="{i}"><button type="button" class="t-play">'
            f'<span class="t-icon" aria-hidden="true"></span><span class="t-title">{e(t["t"])}</span>'
            f'<span class="t-state"></span><span class="t-len">{clock(t["d"])}</span></button>{read}</li>')


total = sum(t["d"] for t in tracks)
lst = []
for name, rng in GROUPS:
    lst.append(f'<h2>{e(name)}</h2><ol class="tracks">' + "".join(track_li(n) for n in rng if n in by_num) + "</ol>")
listen = f"""<div class="listen">
<div class="intro">
  <figure class="book-cover square"><img src="/images/audiobook.jpg" width="600" height="600" alt="Audiobook cover of Ticket to Hell via Dieppe, by A. Robert Prouse"></figure>
  <div>
    <h1 class="book-title">Listen <span>to the audiobook</span></h1>
    <p class="book-sub">Ticket to Hell via Dieppe, by A. Robert Prouse · {len(tracks)} tracks · {hms(total)}</p>
    <p class="start"><button type="button" class="button primary" id="listen-start">Play from the beginning</button></p>
    <p class="continue" id="listen-continue" hidden></p>
    <p class="other-editions">Your place in each track is remembered on this device. Prefer your own player? <a href="/#listen">Download the MP3s</a>.</p>
  </div>
</div>
<noscript><p class="lede">The player needs JavaScript. You can still <a href="/#listen">download the MP3s</a>.</p></noscript>
{"".join(lst)}
</div>"""
LISTEN.mkdir(parents=True, exist_ok=True)
save_to(LISTEN, "index.html", page("listen/", "listen", "Listen to the audiobook",
                                   "Listen to the audiobook of Ticket to Hell via Dieppe online, chapter by chapter, free.",
                                   listen, kind="listen", audio=True).encode("utf-8"))
save_to(LISTEN, "tracks.js", ("// Generated by EPUB Build/build_web.py from the tags in Audiobook/*.mp3. Don't edit by hand.\n"
                              "window.TTH_TRACKS = " + json.dumps(tracks, ensure_ascii=False, indent=0) + ";\n").encode("utf-8"))

if "--with-audio" in sys.argv[1:]:     # local preview only; the folder is git-ignored and pages.yml does this on deploy
    dest = LISTEN / "audio"
    dest.mkdir(exist_ok=True)
    for t in tracks:
        src, out = AUDIO / t["f"], dest / t["f"]
        if not out.exists() or out.stat().st_size != src.stat().st_size:
            shutil.copy2(src, out)

# ---------------------------------------------------------------- 9. remove anything left from an old build
for p in OUT.rglob("*"):
    if p.is_file() and p.resolve() not in written and p.name not in HAND_WRITTEN:
        p.unlink()
shutil.rmtree(tmp, ignore_errors=True)
print(f"Wrote site/read/: {len(sections)} reading pages, contents, gallery, {count} pictures; "
      f"site/listen/: {len(tracks)} tracks, {hms(total)}")
