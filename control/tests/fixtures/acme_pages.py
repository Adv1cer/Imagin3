"""Fictional 'Acme University' fixtures for deterministic offline tests.
Never represents real UTCC data — see plan Global Constraints."""

ACME_HOME_PAGE_HTML = b"""
<html>
<head>
<script type="application/ld+json">
{"@type": "Organization", "name": "Acme University", "logo": "https://acme.example/brand/logo.svg"}
</script>
<link rel="icon" href="https://acme.example/favicon.ico">
<meta property="og:image" content="https://acme.example/social-banner.png">
</head>
<body>
<header><img src="https://acme.example/brand/logo.svg"></header>
</body>
</html>
"""
