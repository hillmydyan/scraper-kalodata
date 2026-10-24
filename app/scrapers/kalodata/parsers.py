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
    def detect_currency(cls, raw_val: Optional[str], default_country: str = "ID") -> str:
        """
        Detects currency code from raw string symbol.
        Returns 'IDR', 'MYR', 'THB', 'USD', or default country's currency.
        """
        raw = cls.clean_raw_string(raw_val).upper()
        if "RP" in raw or "IDR" in raw:
            return "IDR"
        if "RM" in raw or "MYR" in raw:
            return "MYR"
        if "฿" in raw or "THB" in raw:
            return "THB"
        if "$" in raw or "USD" in raw:
            return "USD"
        return "IDR" if default_country.upper() == "ID" else ("MYR" if default_country.upper() == "MY" else "THB")

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

        # Remove currency symbol (supports Rp, RM, ฿, $, etc. across all regions)
        all_symbols = ["Rp", "RM", "฿", "$", "IDR", "MYR", "THB", "USD"]
        if currency_symbol and currency_symbol not in all_symbols:
            all_symbols.append(currency_symbol)

        sym_pattern = "|".join(re.escape(s) for s in sorted(all_symbols, key=len, reverse=True))
        cleaned = re.sub(sym_pattern, "", raw, flags=re.IGNORECASE).strip()

        # Check for suffixes (case-insensitive, supporting ID jt/rb/miliar & EN k/m/b)
        multiplier = 1.0
        is_abbreviated = False

        combined_suffixes = {
            "miliar": 1e9,
            "milyar": 1e9,
            "juta": 1e6,
            "ribu": 1e3,
            "jt": 1e6,
            "rb": 1e3,
            "b": 1e9,
            "m": 1e6,
            "k": 1e3,
        }
        for sfx_name, sfx_mult in suffixes.items():
            combined_suffixes[str(sfx_name).lower()] = float(sfx_mult)

        sorted_suffixes = sorted(combined_suffixes.keys(), key=lambda s: len(str(s)), reverse=True)
        for sfx in sorted_suffixes:
            pattern = re.compile(rf"{re.escape(str(sfx))}\s*$", re.IGNORECASE)
            if pattern.search(cleaned):
                multiplier = float(combined_suffixes[sfx])
                is_abbreviated = True
                cleaned = pattern.sub("", cleaned).strip()
                break

        # Remove any stray characters except digits, dot, comma, minus
        cleaned = re.sub(r"[^\d.,-]", "", cleaned).strip()
        if not cleaned or cleaned in [".", ",", "-", "-.", "-,"]:
            return None, False

        # Handle separator logic
        if is_abbreviated:
            # When abbreviated (e.g. 1.2K or 1,2jt or 39,65JT), any dot or comma is a decimal point
            cleaned = cleaned.replace(",", ".")
        else:
            # Determine separator rules based on symbol in raw or country_code
            is_id_format = "RP" in raw.upper() or "IDR" in raw.upper() or (country_code.upper() == "ID" and "RM" not in raw.upper() and "฿" not in raw and "$" not in raw)
            thou_sep = "." if is_id_format else ","
            dec_sep = "," if is_id_format else "."

            # Full numbers without suffix:
            if "." in cleaned and "," in cleaned:
                last_dot = cleaned.rfind(".")
                last_comma = cleaned.rfind(",")
                if last_dot > last_comma:
                    cleaned = cleaned.replace(",", "")
                else:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
            elif thou_sep in cleaned:
                parts = cleaned.split(thou_sep)
                if len(parts) > 2:
                    cleaned = "".join(parts)
                elif len(parts) == 2:
                    if len(parts[1]) == 3:
                        cleaned = parts[0] + parts[1]
                    else:
                        cleaned = parts[0] + "." + parts[1]
            elif dec_sep in cleaned and dec_sep != ".":
                cleaned = cleaned.replace(dec_sep, ".")

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
