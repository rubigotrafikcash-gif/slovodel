"""A2: reproducible letter-frequency comparison to a *local*, user-supplied corpus.

There is NO built-in, certified normative Russian corpus. A local profile is
not representative of the language and never replaces norm_letter_deviation.
All rights/provenance assertions are self-declared, not independently verified.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import unicodedata

PROFILE_METHOD_VERSION = "0.3.0"  # Profile contract unchanged by A5
from .metrics import RU_ALPHABET, RU_LETTERS, cleaned, measurement, unavailable

PROFILE_FORMAT = "slovodel.local-letter-reference.v1"
MIN_REFERENCE_LETTERS = 10_000
MIN_SAMPLE_LETTERS = 100


class ProfileError(ValueError):
    """Fixed error code; never reveal the profile's contents."""


def _nonblank(value: object, maximum: int = 512) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum


def _canonical(profile: dict) -> bytes:
    return json.dumps(
        profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def count_letters(text: str) -> dict[str, int]:
    """Exactly match A1: NFC, URL/email masking, casefold, Russian letters."""
    safe = cleaned(unicodedata.normalize("NFC", text))
    counts = Counter(ch for ch in safe.casefold() if ch in RU_LETTERS)
    return {ch: counts[ch] for ch in RU_ALPHABET}


def make_profile(
    raw: bytes, text: str, *, source_label: str, source_url: str,
    genre: str, corpus_version: str, license_id: str, rights_basis: str,
) -> dict:
    metadata = (source_label, source_url, genre, corpus_version,
                license_id, rights_basis)
    if any(not _nonblank(x) for x in metadata):
        raise ProfileError("PROFILE_MISSING_PROVENANCE")
    counts = count_letters(text)
    total = sum(counts.values())
    if total == 0:
        raise ProfileError("PROFILE_NO_RUSSIAN_LETTERS")
    profile = {
        "format": PROFILE_FORMAT,
        "profile_kind": "user_supplied_non_normative",
        "license_status": "self_declared_unverified",
        "source_label": source_label,
        "source_url": source_url,
        "genre": genre,
        "corpus_version": corpus_version,
        "license_id": license_id,
        "rights_basis": rights_basis,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "method_version": PROFILE_METHOD_VERSION,
        "preprocessing": "NFC+exclude_URL_email+casefold+count_RU33",
        "total_letters": total,
        "counts": counts,
    }
    validate(profile)
    return profile


def validate(profile: object) -> dict:
    """Strict shape, checksum syntax, integer total, 33-key and version checks."""
    if not isinstance(profile, dict):
        raise ProfileError("PROFILE_INVALID_SHAPE")
    required = {
        "format", "profile_kind", "license_status", "source_label",
        "source_url", "genre", "corpus_version", "license_id",
        "rights_basis", "source_sha256", "method_version",
        "preprocessing", "total_letters", "counts",
    }
    if set(profile) != required:
        raise ProfileError("PROFILE_INVALID_SHAPE")
    for key in ("source_label", "source_url", "genre", "corpus_version",
                "license_id", "rights_basis"):
        if not _nonblank(profile[key]):
            raise ProfileError("PROFILE_MISSING_PROVENANCE")
    if (profile["format"] != PROFILE_FORMAT
            or profile["profile_kind"] != "user_supplied_non_normative"
            or profile["license_status"] != "self_declared_unverified"
            or profile["preprocessing"]
                != "NFC+exclude_URL_email+casefold+count_RU33"):
        raise ProfileError("PROFILE_INVALID_METHOD")
    if profile["method_version"] != PROFILE_METHOD_VERSION:
        raise ProfileError("PROFILE_VERSION_MISMATCH")
    digest = profile["source_sha256"]
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise ProfileError("PROFILE_INVALID_SOURCE_HASH")
    counts = profile["counts"]
    if not isinstance(counts, dict) or set(counts) != set(RU_ALPHABET):
        raise ProfileError("PROFILE_INVALID_ALPHABET")
    if any(type(v) is not int or v < 0 for v in counts.values()):
        raise ProfileError("PROFILE_INVALID_COUNTS")
    total = profile["total_letters"]
    if type(total) is not int or total <= 0 or sum(counts.values()) != total:
        raise ProfileError("PROFILE_INVALID_TOTAL")
    return profile


def parse_profile(text: str) -> tuple[dict, str]:
    """Reject duplicate JSON keys before provenance is accepted."""
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProfileError("PROFILE_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        obj = json.loads(text, object_pairs_hook=no_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             ProfileError("PROFILE_INVALID_JSON")))
    except ProfileError:
        raise
    except (ValueError, TypeError):
        raise ProfileError("PROFILE_INVALID_JSON") from None
    profile = validate(obj)
    digest = hashlib.sha256(_canonical(profile)).hexdigest()
    return profile, "local-sha256:" + digest


def _round(value: float) -> float:
    return round(value, 8)


def compare_rate(observed: int, observed_total: int,
                 baseline: int, baseline_total: int
                 ) -> tuple[float | None, float | None]:
    """delta_pp = 100*(p-q); ratio = p/q (undefined if q=0).

    N=0 never yields 0 as if an observed proportion were measured.
    """
    if (any(type(v) is not int or v < 0
            for v in (observed, observed_total, baseline, baseline_total))
            or observed_total == 0 or baseline_total == 0
            or observed > observed_total or baseline > baseline_total):
        return None, None
    p = observed / observed_total
    q = baseline / baseline_total
    delta = _round(100.0 * (p - q))
    ratio = _round(p / q) if baseline > 0 else None
    return delta, ratio


def calculate_reference(text: str, profile: dict, dataset_id: str) -> list[dict]:
    """Generate explicitly *local-reference* metrics, never normative scores."""
    validate(profile)
    if (not isinstance(dataset_id, str)
            or not dataset_id.startswith("local-sha256:")
            or len(dataset_id) != 77
            or any(ch not in "0123456789abcdef" for ch in dataset_id[13:])):
        raise ProfileError("PROFILE_INVALID_DATASET_ID")
    counts = count_letters(text)
    total = sum(counts.values())
    reference_total = profile["total_letters"]
    warnings = ["LOCAL_REFERENCE_NOT_NORMATIVE", "LICENSE_SELF_DECLARED_UNVERIFIED"]
    if reference_total < MIN_REFERENCE_LETTERS:
        warnings.append("SMALL_REFERENCE_CORPUS")
    if total < MIN_SAMPLE_LETTERS:
        warnings.append("SMALL_SAMPLE")
    result = []
    for ch in RU_ALPHABET:
        delta, ratio = compare_rate(
            counts[ch], total, profile["counts"][ch], reference_total
        )
        for suffix, value, unit in (
            ("delta_pp", delta, "percentage_points"),
            ("ratio", ratio, "ratio"),
        ):
            identifier = "local_ref_" + ch + "_" + suffix
            if value is None:
                reason = ("NO_RUSSIAN_SAMPLE_LETTERS" if total == 0
                          else "ZERO_BASELINE_FREQUENCY")
                result.append(unavailable(identifier, reason))
            else:
                row = measurement(
                    identifier, value, unit, total, "a2.local_reference",
                    warnings.copy()
                )
                row["dataset_id"] = dataset_id
                result.append(row)
    return result
