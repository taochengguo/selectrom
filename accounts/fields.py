from pathlib import PurePosixPath
from django.core.files.base import ContentFile
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from config.images import encode_webp


class WebPImageFieldFile(ImageFieldFile):
    def save(self, name, content, save=True):
        content.seek(0)
        encoded = encode_webp(content)
        name = str(PurePosixPath(name).with_suffix('.webp'))
        super().save(name, ContentFile(encoded), save=save)


class WebPImageField(ImageField):
    attr_class = WebPImageFieldFile
