import io

import qrcode
from PIL import Image
from pyzbar.pyzbar import decode as zbar_decode


def generate_qr_png(target_url: str) -> bytes:
    image = qrcode.make(target_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def decode_qr_png(png_bytes: bytes) -> list[str]:
    image = Image.open(io.BytesIO(png_bytes))
    return [result.data.decode("utf-8") for result in zbar_decode(image)]


def validate_qr(png_bytes: bytes, expected_url: str) -> bool:
    return expected_url in decode_qr_png(png_bytes)
