"""
Parsing utilities for numbers, currencies, and commissions per country.
Follows rules in PRD §6.11 and configurations in config/number_formats.yaml.
"""

import re
from typing import Optional, Tuple
from app.config import NUMBER_FORMATS_CONFIG


class NumberParser:
    @staticmethod
    def clean_raw_string(val: Optional[str]) -> str:
        if val is None:
            return ""
        # Remove non-breaking spaces and strip
        return str(val).replace("\xa0", " ").strip()

    @classmethod
    def parse_currency_amount(
        cls,
        raw_val: Optional[str],
        country_code: str
    ) -> Tuple[Optional[float], bool]:
        """
        Parses a currency amount string for a given country.
        Returns:
            (parsed_numeric_value, is_abbreviated)
        If parsing fails or raw_val is empty, returns (None, False).
        """
        raw = cls.clean_raw_string(raw_val)
        if not raw or raw in ["-", "N/A", "null", "None"]:
            return None, False

        country_rule = NUMBER_FORMATS_CONFIG.get(country_code.upper())
        if not country_rule:
            country_rule = NUMBER_FORMATS_CONFIG.get("ID", {})

        currency_symbol = country_rule.get("currency_symbol", "")
        suffixes = country_rule.get("suffixes", {})

        # Remove currency symbol
        cleaned = raw
        if currency_symbol:
            cleaned = re.sub(re.escape(currency_symbol), "", cleaned, flags=re.IGNORECASE)

        cleaned = cleaned.replace("$", "").strip()

        # Check for suffixes (case-insensitive)
        multiplier = 1.0
        is_abbreviated = False

        # Sort suffixes by length descending
        sorted_suffixes = sorted(suffixes.keys(), key=lambda s: len(str(s)), reverse=True)
        for sfx in sorted_suffixes:
            pattern = re.compile(rf"{re.escape(str(sfx))}\s*$", re.IGNORECASE)
            if pattern.search(cleaned):
                multiplier = float(suffixes[sfx])
                is_abbreviated = True
                cleaned = pattern.sub("", cleaned).strip()
                break

        # If not matched against country-specific suffix, also check standard K, M, B
        if not is_abbreviated:
            for sfx, mult in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
                pattern = re.compile(rf"{sfx}\s*$", re.IGNORECASE)
                if pattern.search(cleaned):
                    multiplier = mult
                    is_abbreviated = True
                    cleaned = pattern.sub("", cleaned).strip()
                    break

        # Remove any stray characters except digits, dot, comma, minus
        cleaned = re.sub(r"[^\d.,-]", "", cleaned).strip()
        if not cleaned or cleaned in [".", ",", "-", "-.", "-,"]:
            return None, False

        # Handle separator logic
        if is_abbreviated:
            # When abbreviated (e.g. 1.2K or 1,2jt), any dot or comma is a decimal point
            cleaned = cleaned.replace(",", ".")
        else:
            # Full numbers without suffix:
            # Case 1: Both comma and dot present, e.g. 1,500.50 or 2.500.000,50
            if "." in cleaned and "," in cleaned:
                last_dot = cleaned.rfind(".")
                last_comma = cleaned.rfind(",")
                if last_dot > last_comma:
                    # Dot is decimal, comma is thousand separator (e.g. 1,500.50)
                    cleaned = cleaned.replace(",", "")
                else:
                    # Comma is decimal, dot is thousand separator (e.g. 1.500,50)
                    cleaned = cleaned.replace(".", "").replace(",", ".")
            elif "." in cleaned:
                # Only dot: could be thousand separator (2.500.000) or decimal (99.99)
                parts = cleaned.split(".")
                # If multiple dots, e.g. 2.500.000 -> thousand separators
                if len(parts) > 2:
                    cleaned = "".join(parts)
                elif len(parts) == 2:
                    # If exactly 3 digits after dot and country uses dot as thousand separator
                    if len(parts[1]) == 3 and country_rule.get("thousand_separator") == ".":
                        cleaned = parts[0] + parts[1]
                    else:
                        # Otherwise decimal point (e.g. 99.99)
                        pass
            elif "," in cleaned:
                # Only comma: could be thousand separator (15,000) or decimal (99,99)
                parts = cleaned.split(",")
                if len(parts) > 2:
                    cleaned = "".join(parts)
                elif len(parts) == 2:
                    if len(parts[1]) == 3 and country_rule.get("thousand_separator") == ",":
                        cleaned = parts[0] + parts[1]
                    else:
                        cleaned = parts[0] + "." + parts[1]

        try:
            num = float(cleaned)
            val = round(num * multiplier, 2)
            return (val, is_abbreviated)
        except ValueError:
            return None, False

    @classmethod
    def parse_integer_sales(cls, raw_val: Optional[str], country_code: str = "ID") -> Optional[int]:
        """
        Parses sales volume count (e.g. '1.2K', '500', '10.500').
        Returns integer or None.
        """
        val, _ = cls.parse_currency_amount(raw_val, country_code)
        if val is None:
            return None
        return int(round(val))

    @classmethod
    def parse_commission_rate(cls, raw_val: Optional[str]) -> Optional[float]:
        """
        Parses commission rate string into decimal 0.0 - 1.0.
        E.g.: '15%' -> 0.15, '0.15' -> 0.15, '10.5%' -> 0.105.
        Returns None if empty or invalid (> 1.0 or < 0.0).
        """
        raw = cls.clean_raw_string(raw_val)
        if not raw or raw in ["-", "N/A", "null", "None"]:
            return None

        is_pct = "%" in raw
        cleaned = raw.replace("%", "").strip()

        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")

        cleaned = re.sub(r"[^\d.-]", "", cleaned)
        if not cleaned:
            return None

        try:
            val = float(cleaned)
            if is_pct:
                val = val / 100.0
            elif 1.0 < val <= 100.0:
                val = val / 100.0

            if 0.0 <= val <= 1.0:
                return round(val, 4)
            return None
        except ValueError:
            return None
