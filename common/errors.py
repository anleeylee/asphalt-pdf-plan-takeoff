"""Structured error classes per the implementation playbook.

Error code registry (E001..E010):

    E001 UnsupportedFile
    E002 MissingScale
    E003 AmbiguousUnit
    E004 LowConfidenceExtraction
    E005 ConflictingSpecification
    E006 DuplicateRecord
    E007 InvalidGeometry
    E008 APIError
    E009 MissingSource
    E010 CalculationValidationFailure

Every script raises typed errors so callers and the audit log can react
without string matching.
"""

from __future__ import annotations


class ADIError(Exception):
    """Base class for all Asphalt Desktop Intelligence errors."""

    code: str = "E000"
    label: str = "GenericError"

    def __init__(self, message: str, *, detail: str | None = None, code: str | None = None):
        self.message = message
        self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "message": self.message,
            "detail": self.detail,
        }


class UnsupportedFileError(ADIError):
    code = "E001"
    label = "UnsupportedFile"


class MissingScaleError(ADIError):
    code = "E002"
    label = "MissingScale"


class AmbiguousUnitError(ADIError):
    code = "E003"
    label = "AmbiguousUnit"


class LowConfidenceExtractionError(ADIError):
    code = "E004"
    label = "LowConfidenceExtraction"


class ConflictingSpecificationError(ADIError):
    code = "E005"
    label = "ConflictingSpecification"


class DuplicateRecordError(ADIError):
    code = "E006"
    label = "DuplicateRecord"


class InvalidGeometryError(ADIError):
    code = "E007"
    label = "InvalidGeometry"


class APIError(ADIError):
    code = "E008"
    label = "APIError"


class MissingSourceError(ADIError):
    code = "E009"
    label = "MissingSource"


class CalculationValidationFailure(ADIError):
    code = "E010"
    label = "CalculationValidationFailure"


ERROR_CLASSES = {
    "E001": UnsupportedFileError,
    "E002": MissingScaleError,
    "E003": AmbiguousUnitError,
    "E004": LowConfidenceExtractionError,
    "E005": ConflictingSpecificationError,
    "E006": DuplicateRecordError,
    "E007": InvalidGeometryError,
    "E008": APIError,
    "E009": MissingSourceError,
    "E010": CalculationValidationFailure,
}
