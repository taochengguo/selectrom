from io import BytesIO
from PIL import Image
from django.test import SimpleTestCase
from config.images import encode_webp


class WebPConversionTests(SimpleTestCase):
    def test_transparency_and_orientation_are_preserved(self):
        source=BytesIO()
        image=Image.new('RGBA',(3,2),(20,40,60,0))
        image.save(source,format='PNG')
        with Image.open(BytesIO(encode_webp(source))) as result:
            self.assertEqual(result.format,'WEBP')
            self.assertEqual(result.getpixel((0,0))[3],0)
        source=BytesIO()
        exif=Image.Exif()
        exif[274]=6
        Image.new('RGB',(3,2),'blue').save(source,format='JPEG',exif=exif)
        with Image.open(BytesIO(encode_webp(source))) as result:
            self.assertEqual(result.size,(2,3))

    def test_invalid_image_is_rejected(self):
        from PIL import UnidentifiedImageError
        with self.assertRaises(UnidentifiedImageError):
            encode_webp(BytesIO(b'not an image'))
