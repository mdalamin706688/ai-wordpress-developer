"""Map 制作タイプ column → v2 production type handlers."""

from __future__ import annotations

from enum import Enum


class ProductionType(str, Enum):
    """Client hearing-sheet production types (v2 only)."""

    TYPE1_SHINKI = "type1"  # 新規 — clone BBS standard website template
    TYPE2_RENEWAL = "type2"  # リニューアル — renew existing client site (既存URL / 既存ページ)
    TYPE3_SATELLITE = "type3"  # サテライト
    TYPE4_SATELLITE_RENEWAL = "type4"  # サテライトリニューアル
    UNKNOWN = "unknown"


_LABEL_TO_TYPE: dict[str, ProductionType] = {
    "新規": ProductionType.TYPE1_SHINKI,
    "リニューアル": ProductionType.TYPE2_RENEWAL,
    "サテライト": ProductionType.TYPE3_SATELLITE,
    "サテライトリニューアル": ProductionType.TYPE4_SATELLITE_RENEWAL,
}


def detect_production_type(raw: str | None) -> ProductionType:
    key = str(raw or "").strip()
    return _LABEL_TO_TYPE.get(key, ProductionType.UNKNOWN)


def production_type_label(pt: ProductionType) -> str:
    for label, value in _LABEL_TO_TYPE.items():
        if value == pt:
            return label
    return str(pt.value)
