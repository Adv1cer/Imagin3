from ..qr_gen import validate_qr


def check_qr(png_bytes: bytes, expected_url: str) -> bool:
    # Always re-decoded fresh against the expected target; never cached (PROD.md §7.4).
    return validate_qr(png_bytes, expected_url)
