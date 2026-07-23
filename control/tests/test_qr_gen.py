from imagin.qr_gen import generate_qr_png, validate_qr


def test_generate_qr_png_round_trips_through_validate_qr():
    url = "https://www.utcc.ac.th/openhouse"

    png_bytes = generate_qr_png(url)

    assert validate_qr(png_bytes, url) is True


def test_validate_qr_rejects_mismatched_url():
    png_bytes = generate_qr_png("https://www.utcc.ac.th/openhouse")

    assert validate_qr(png_bytes, "https://www.utcc.ac.th/wrong-path") is False
