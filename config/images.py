from io import BytesIO
from PIL import Image, ImageOps


def encode_webp(source, *, lossless=False):
    """Decode image bytes, apply camera orientation and retain transparency."""
    source.seek(0)
    with Image.open(source) as original:
        original.load()
        image = ImageOps.exif_transpose(original)
        image = image.convert('RGBA' if image.mode in ('RGBA', 'LA', 'P') or 'transparency' in image.info else 'RGB')
        output = BytesIO()
        image.save(output, format='WEBP', quality=82, method=6, lossless=lossless)
        return output.getvalue()
