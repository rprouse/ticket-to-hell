"""Make the web-sized cover images used by the GitHub Pages site.

Reads the original cover art from the book folder (never modifies it) and
writes resized copies into site/images/:

- cover.jpg / cover@2x.jpg   portrait cover for the page (from Book Cover.png)
- social.jpg                 1200x630 link-preview image (from Audiobook Cover.png)
- favicon.png / apple-touch-icon.png  small square icons (from Audiobook Cover.png)

Run after changing either cover:  python site/build_images.py
Needs Pillow (pip install pillow). The outputs are committed, so the Pages
workflow does not need to run this.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "images"


def save_jpeg(img: Image.Image, name: str, quality: int = 85) -> None:
    path = OUT / name
    img.convert("RGB").save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    print(f"{name}: {img.width}x{img.height}, {path.stat().st_size // 1024} KB")


def save_png(img: Image.Image, name: str) -> None:
    path = OUT / name
    img.convert("RGB").save(path, "PNG", optimize=True)
    print(f"{name}: {img.width}x{img.height}, {path.stat().st_size // 1024} KB")


def main() -> None:
    OUT.mkdir(exist_ok=True)

    # Portrait cover (2:3). Shown at up to ~360 px wide, so 400 and 800 px cover 1x and 2x screens.
    with Image.open(ROOT / "Book Cover.png") as cover:
        for width, name in ((400, "cover.jpg"), (800, "cover@2x.jpg")):
            height = round(cover.height * width / cover.width)
            save_jpeg(cover.resize((width, height), Image.LANCZOS), name)

    with Image.open(ROOT / "Audiobook Cover.png") as square:
        # Link preview (1.91:1): crop the title, subtitle and author band from the square art.
        w = square.width
        h = round(w * 630 / 1200)
        top = round(square.height * 0.015)
        band = square.crop((0, top, w, top + h))
        save_jpeg(band.resize((1200, 630), Image.LANCZOS), "social.jpg")

        # Icons: the full square art reads poorly at 32 px, so crop to the "Ticket to Hell" title.
        side = round(square.width * 0.66)
        left = (square.width - side) // 2
        icon = square.crop((left, 0, left + side, side))
        save_png(icon.resize((180, 180), Image.LANCZOS), "apple-touch-icon.png")
        save_png(icon.resize((64, 64), Image.LANCZOS), "favicon.png")


if __name__ == "__main__":
    main()
