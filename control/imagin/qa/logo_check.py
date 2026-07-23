def check_logo_provenance(used_asset_sha256: str, approved_asset_sha256: str) -> bool:
    return used_asset_sha256 == approved_asset_sha256
