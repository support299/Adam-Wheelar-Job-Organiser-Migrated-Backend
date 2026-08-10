"""Shared DRF serializer field helpers."""

import decimal

from rest_framework import serializers


class RoundingDecimalField(serializers.DecimalField):
    """DecimalField that rounds overly-precise input instead of rejecting it.

    DRF's built-in `rounding` kwarg only applies during the post-validation
    quantize step — validate_precision() runs first and raises "no more than
    N decimal places" before rounding ever gets a chance. Round up front here
    so values computed client-side (which often carry more precision than
    the DB column allows) are accepted rather than bounced.
    """

    def validate_precision(self, value):
        if self.decimal_places is not None:
            quantizer = decimal.Decimal(1).scaleb(-self.decimal_places)
            value = value.quantize(quantizer, rounding=decimal.ROUND_HALF_UP)
        return super().validate_precision(value)
