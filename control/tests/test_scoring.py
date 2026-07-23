from imagin.brand.scoring import score_logo_candidate, classify_score


def test_jsonld_svg_and_filename_hint_alone_is_still_excluded_below_threshold():
    # 30 (jsonld) + 15 (svg) + 10 (filename hint) = 55, below PROVISIONAL_THRESHOLD (60),
    # so per PROD.md §7.1a/§7.3 this candidate MUST NOT be auto-usable or provisional.
    scored = score_logo_candidate(["organization_jsonld"], is_svg=True, filename_hint="official-logo.svg")

    assert scored.score == 55
    assert scored.status == "excluded"


def test_jsonld_plus_header_reuse_plus_svg_and_filename_hint_reaches_provisional():
    # 30 (jsonld) + 20 (header reuse) + 15 (svg) + 10 (filename hint, "logo.svg" matches) = 75.
    scored = score_logo_candidate(["organization_jsonld", "repeated_header_use"], is_svg=True, filename_hint="logo.svg")

    assert scored.score == 75
    assert scored.status == "provisional"


def test_official_brand_guideline_plus_jsonld_and_svg_is_auto_accepted():
    # 40 (official brand guideline) + 30 (jsonld) + 15 (svg) = 85, clears AUTO_USE_THRESHOLD (80).
    scored = score_logo_candidate(["official_brand_guideline", "organization_jsonld"], is_svg=True)

    assert scored.score == 85
    assert scored.status == "auto_accepted"


def test_favicon_only_is_excluded():
    scored = score_logo_candidate(["favicon_only"])

    assert scored.score == -15
    assert scored.status == "excluded"


def test_classify_score_boundaries():
    assert classify_score(80) == "auto_accepted"
    assert classify_score(79) == "provisional"
    assert classify_score(60) == "provisional"
    assert classify_score(59) == "excluded"
