"""Abertura de fotos enviadas pelo celular, inclusive no formato HEIC (padrão de iPhones e de vários Android)."""
from PIL import Image, ImageOps, UnidentifiedImageError

try:  # suporte a HEIC/HEIF; se a biblioteca faltar, o resto continua funcionando
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

EXTENSOES_FOTO = {"jpg", "jpeg", "png", "webp", "heic", "heif"}


def abrir_foto(stream):
    """Devolve a imagem já na posição certa (celulares gravam a rotação à parte) ou None se não for uma foto."""
    try:
        imagem = Image.open(stream)
        return ImageOps.exif_transpose(imagem).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        return None
