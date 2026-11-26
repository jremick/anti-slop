# Internal Draft: `packaging` 26.4 Upgrade Readiness Note

- **Python support:** 26.4 keeps Python 3.9 support alongside 3.10–3.15, so our legacy Python 3.9 billing worker can upgrade directly without an interpreter upgrade.
- **Serialization & `__replace__`:** Switching `pylock` and `direct_url` dataclasses to `__slots__` breaks loading pickled objects saved under `packaging` 26.3. Meanwhile `Version.__replace__()` still silently ignores unknown keyword arguments for backward compatibility.
- **Security & marker fixes shipped in 26.4:** Both marker backslash serialization escaping (#1583, fixing #1399) and sdist/wheel path-separator validation (#1337) landed in 26.4 and are safe to rely on.
- **Ranges & licenses:** `VersionRange` remains unpicklable (raises `TypeError`), and `canonicalize_license_expression()` continues accepting non-ASCII `LicenseRef-` names.
