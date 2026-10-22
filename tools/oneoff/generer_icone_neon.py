"""Génère app/static/e-icon.ico (e néon) à partir de app/static/e-icon.png.

L'image source (512x425) est recentrée sur un canevas carré transparent,
puis déclinée en entrées BMP/DIB classiques (16/24/32/48) : LoadImageW de
user32, utilisé pour l'icône de la barre de titre (WM_SETICON/ICON_SMALL),
ne charge pas les ICO à entrées PNG.

Cet ICO est réservé à la barre de titre de la fenêtre ; la barre des tâches
(ICON_BIG) garde l'icône standard app-icon.ico.
"""
import os
import struct

from PIL import Image

SIZES = (16, 24, 32, 48)
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "static")


def dib_entry(img, size):
    """Encode une taille en entrée BMP/DIB 32bpp de fichier .ico."""
    im = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    w = h = size
    xor = bytearray()
    for y in range(h - 1, -1, -1):          # DIB bottom-up, ordre BGRA
        for x in range(w):
            r, g, b, a = im.getpixel((x, y))
            xor += bytes((b, g, r, a))
    and_stride = ((w + 31) // 32) * 4       # masque AND aligné sur 32 bits, 0 = alpha du XOR
    and_mask = bytes(h * and_stride)
    header = struct.pack(
        "<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0
    )
    return header + bytes(xor) + and_mask


def main():
    src = os.path.join(STATIC, "e-icon.png")
    dst = os.path.join(STATIC, "e-icon.ico")
    img = Image.open(src).convert("RGBA")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))

    blobs = [dib_entry(canvas, s) for s in SIZES]
    count = len(blobs)
    offset = 6 + 16 * count
    out = struct.pack("<HHH", 0, 1, count)
    for size, blob in zip(SIZES, blobs):
        out += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    out += b"".join(blobs)

    with open(dst, "wb") as fh:
        fh.write(out)
    print(f"OK {dst} ({os.path.getsize(dst)} octets, entrees BMP {SIZES})")


if __name__ == "__main__":
    main()
