from pathlib import Path

from django.core.validators import FileExtensionValidator


IMAGE_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp', 'gif', 'avif')
VIDEO_EXTENSIONS = ('mp4', 'webm', 'mov', 'm4v', 'ogv')
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS

media_file_validator = FileExtensionValidator(allowed_extensions=MEDIA_EXTENSIONS)


def media_type_from_name(name):
    """Return the frontend media type for a stored file name."""
    if not name:
        return None
    extension = Path(str(name)).suffix.lower().lstrip('.')
    return 'video' if extension in VIDEO_EXTENSIONS else 'image'
