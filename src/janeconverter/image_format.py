"""Convert downloaded still images to the user's selected image format."""

from __future__ import annotations

import os

from PIL import Image, ImageOps


_FORMATS = {
    "jpg": ("JPEG", ".jpg"),
    "jpeg": ("JPEG", ".jpeg"),
    "png": ("PNG", ".png"),
    "webp": ("WEBP", ".webp"),
}
_IMAGE_QUALITY = {"best": 95, "high": 90, "balanced": 80, "small": 65}


def convert_image_format(image_path: str, target_format: str | None, quality: str = "best") -> str:
    """Convert an image in place when a concrete output format is selected."""
    normalized_format = str(target_format or "source").lower().strip().lstrip(".")
    if normalized_format in ("source", "original", ""):
        return image_path
    if normalized_format not in _FORMATS:
        raise ValueError(f"Unsupported image format: {target_format}")

    pillow_format, extension = _FORMATS[normalized_format]
    with Image.open(image_path) as source:
        source_format = source.format
        if source_format == pillow_format:
            return image_path

        source.load()
        image = ImageOps.exif_transpose(source)
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        icc_profile = image.info.get("icc_profile")
        output_path = os.path.splitext(image_path)[0] + extension
        quality_value = _IMAGE_QUALITY.get(str(quality).lower().strip(), 95)
        save_options = {"icc_profile": icc_profile} if icc_profile else {}

        if pillow_format == "JPEG":
            if has_alpha:
                rgba = image.convert("RGBA")
                output = Image.new("RGB", rgba.size, "white")
                output.paste(rgba, mask=rgba.getchannel("A"))
            else:
                output = image.convert("RGB")
            save_options.update(quality=quality_value, optimize=True, progressive=True)
        elif pillow_format == "PNG":
            if has_alpha:
                output = image.convert("RGBA")
            elif image.mode in ("1", "L", "LA", "P", "RGB", "I", "I;16"):
                output = image.copy()
            else:
                output = image.convert("RGB")
            save_options["compress_level"] = 9
        else:
            output = image.convert("RGBA" if has_alpha else "RGB")
            save_options.update(quality=quality_value, method=6)

        output.save(output_path, format=pillow_format, **save_options)

    if os.path.abspath(output_path) != os.path.abspath(image_path):
        os.remove(image_path)
    return output_path
