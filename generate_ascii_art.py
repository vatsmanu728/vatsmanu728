from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFont
import sys

# Dark-to-light density ramp mixing letters/symbols for an organic,
# textured look (rather than a flat block gradient).
RAMP = "@%#8&MW$B0QOZmwqpbdkhaoe*x/\\|()1{}[]?-_+~<>i!lI;:,\"^`'.  "

def image_to_ascii(path, cols=54, aspect_correction=0.52, invert=False,
                    contrast=1.35, brightness=1.0, gamma=1.0,
                    crop_box=None):
    im = Image.open(path).convert("L")
    if crop_box:
        im = im.crop(crop_box)

    w, h = im.size
    cell_h = int(cols * (h / w) * aspect_correction)
    im = im.resize((cols, cell_h), Image.LANCZOS)

    im = ImageEnhance.Brightness(im).enhance(brightness)
    im = ImageEnhance.Contrast(im).enhance(contrast)

    pixels = im.load()
    ramp = RAMP[::-1] if invert else RAMP
    n = len(ramp) - 1

    lines = []
    for y in range(cell_h):
        row = []
        for x in range(cols):
            v = pixels[x, y] / 255.0
            if gamma != 1.0:
                v = v ** gamma
            idx = int(v * n)
            row.append(ramp[idx])
        lines.append("".join(row))
    return lines

def render_preview(lines, out_path, dark=True, font_size=14):
    font = ImageFont.load_default()
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size
        )
    except Exception:
        pass
    char_w = font.getbbox("M")[2] + 1
    line_h = font_size + 2
    W = char_w * max(len(l) for l in lines) + 20
    H = line_h * len(lines) + 20
    bg = (13, 17, 23) if dark else (13, 17, 23)
    fg = (230, 237, 243) if dark else (230, 237, 243)
    # bg = (13, 17, 23) if dark else (255, 255, 255)
    # fg = (230, 237, 243) if dark else (20, 20, 20)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((10, 10 + i * line_h), line, font=font, fill=fg)
    img.save(out_path)

if __name__ == "__main__":
    # Usage: python3 generate_ascii_art.py your_photo.jpg
    # Crop to a roughly square head-and-shoulders region first (an image
    # editor, or PIL's .crop()) for best results -- busy backgrounds turn
    # into noise. Tune cols/contrast/crop_box below and re-run until it
    # looks right, then copy ascii_out.txt over ../ascii_art.txt.
    photo = sys.argv[1] if len(sys.argv) > 1 else "face.png"
    from PIL import ImageFilter, ImageEnhance
    im = Image.open(photo).convert("L")
    im = im.filter(ImageFilter.GaussianBlur(1.3))
    w, h = im.size
    cols = 56
    cell_h = int(cols * (h / w) * 0.52)
    im = im.resize((cols, cell_h), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.55)
    ramp = "@%#8&Odbao*+=~-:,.  "
    n = len(ramp) - 1
    pixels = im.load()
    lines = []
    for y in range(cell_h):
        row = []
        for x in range(cols):
            v = (pixels[x, y] / 255.0) ** 0.85
            row.append(ramp[int(v * n)])
        lines.append("".join(row))
    with open("ascii_out.txt", "w") as f:
        f.write("\n".join(lines))
    render_preview(lines, "preview_dark.png", dark=True)
    render_preview(lines, "preview_light.png", dark=False)
    print(f"{len(lines)} rows x {cols} cols -- check preview_dark.png / preview_light.png")
