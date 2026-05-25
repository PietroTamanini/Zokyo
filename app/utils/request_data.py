"""
request_data.py
---------------
Helpers to normalize request payloads from JSON, form, or multipart.
"""
from __future__ import annotations

from typing import Any, Tuple

from flask import request


def get_request_data() -> Tuple[dict[str, Any], str]:
    """
    Return (data, source) for JSON/form/multipart requests.
    Source is one of: json, form, multipart, empty.
    """
    if request.is_json:
        return request.get_json(silent=True) or {}, "json"

    if request.files:
        data = request.form.to_dict(flat=True)
        data["_files"] = request.files
        return data, "multipart"

    if request.form:
        return request.form.to_dict(flat=True), "form"

    return {}, "empty"
