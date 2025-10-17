"""
License Plate Validation and Normalization
Supports multiple countries with regex patterns
"""

import re
from typing import Optional, Dict, Tuple
from loguru import logger


class PlateValidator:
    """Validates and normalizes license plates for different countries/regions"""

    # Regex patterns for USA, Mexico, and Canada
    PATTERNS: Dict[str, Dict[str, str]] = {
        'US': {
            # State-specific patterns
            'alabama': r'^[0-9]{1,2}[A-Z]{1,5}[0-9]{3}$',  # 12ABC34
            'alaska': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'arizona': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'arkansas': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'california': r'^[0-9][A-Z]{3}[0-9]{3}$',  # 1ABC234
            'colorado': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'connecticut': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'delaware': r'^[0-9]{6}$',  # 123456
            'florida': r'^[A-Z]{3}[0-9]{2}[A-Z]{1}$',  # ABC12D or similar
            'georgia': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'hawaii': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'idaho': r'^[0-9][A-Z][0-9]{5}$',  # 1A23456
            'illinois': r'^[A-Z]{2}[0-9]{5}$',  # AB12345
            'indiana': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'iowa': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'kansas': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'kentucky': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'louisiana': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'maine': r'^[0-9]{4}[A-Z]{2}$',  # 1234AB
            'maryland': r'^[0-9][A-Z]{2}[0-9]{4}$',  # 1AB2345
            'massachusetts': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'michigan': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'minnesota': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'mississippi': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'missouri': r'^[A-Z]{2}[0-9][A-Z]{2}[0-9]$',  # AB1CD2
            'montana': r'^[0-9]{1,2}[A-Z]{1,5}[0-9]{3,4}$',  # 12ABC345
            'nebraska': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'nevada': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'new_hampshire': r'^[0-9]{3}[0-9]{4}$',  # 1234567
            'new_jersey': r'^[A-Z][0-9]{2}[A-Z]{3}$',  # A12BCD
            'new_mexico': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'new_york': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'north_carolina': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'north_dakota': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'ohio': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'oklahoma': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'oregon': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'pennsylvania': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'rhode_island': r'^[0-9]{6}$',  # 123456
            'south_carolina': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'south_dakota': r'^[0-9][A-Z]{2}[0-9]{3}$',  # 1AB234
            'tennessee': r'^[A-Z]{3}[0-9]{2}[A-Z]$',  # ABC12D
            'texas': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'utah': r'^[A-Z][0-9]{2}[A-Z]{3}$',  # A12BCD
            'vermont': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'virginia': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'washington': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'west_virginia': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'wisconsin': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'wyoming': r'^[0-9]{1,2}[A-Z]{1,5}[0-9]{3}$',  # 12ABC34
            # Generic fallback for US plates
            'standard': r'^[A-Z0-9]{5,8}$',  # Generic US format
        },
        'MX': {
            # Mexico plates (varies by state)
            'standard': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234 (most common)
            'federal': r'^[A-Z]{2}[0-9]{5}$',  # AB12345
            'nuevo_leon': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'jalisco': r'^[A-Z]{2}[0-9]{5}$',  # AB12345
            'cdmx': r'^[A-Z]{3}[0-9]{3}[A-Z]$',  # ABC123D
        },
        'CA': {
            # Canadian plates (varies by province)
            'alberta': r'^[A-Z]{3}[0-9]{4}$',  # ABC1234
            'british_columbia': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'manitoba': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'new_brunswick': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'newfoundland': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'northwest_territories': r'^[0-9]{6}$',  # 123456
            'nova_scotia': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'nunavut': r'^[0-9]{6}$',  # 123456
            'ontario': r'^[A-Z]{4}[0-9]{3}$',  # ABCD123
            'prince_edward_island': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'quebec': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            'saskatchewan': r'^[0-9]{3}[A-Z]{3}$',  # 123ABC
            'yukon': r'^[A-Z]{3}[0-9]{3}$',  # ABC123
            # Generic fallback
            'standard': r'^[A-Z0-9]{6,7}$',  # Generic Canadian format
        },
    }

    def __init__(self, default_country: str = 'US', default_region: Optional[str] = None):
        """
        Initialize plate validator

        Args:
            default_country: Default country code (US, UK, EU, etc.)
            default_region: Default region/state (california, texas, etc.)
        """
        self.default_country = default_country
        self.default_region = default_region

    def normalize(self, raw_text: str) -> str:
        """
        Normalize plate text

        Args:
            raw_text: Raw OCR output

        Returns:
            Normalized plate text (uppercase, no spaces/dashes/special chars)
        """
        # Remove common OCR errors
        text = raw_text.replace('O', '0')  # O → 0 in numeric contexts
        text = text.replace('I', '1')  # I → 1 in numeric contexts
        text = text.replace('l', '1')  # lowercase L → 1

        # Remove spaces, dashes, dots
        text = re.sub(r'[\s\-\.]', '', text)

        # Remove non-alphanumeric
        text = re.sub(r'[^A-Z0-9]', '', text.upper())

        return text

    def validate(
        self,
        text: str,
        country: Optional[str] = None,
        region: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate plate against country/region patterns

        Args:
            text: Normalized plate text
            country: Country code (overrides default)
            region: Region/state code (overrides default)

        Returns:
            Tuple of (is_valid, matched_country, matched_region)
        """
        country = country or self.default_country
        region = region or self.default_region

        # Try specific region pattern first
        if region and country in self.PATTERNS:
            patterns = self.PATTERNS[country]
            if region in patterns:
                pattern = patterns[region]
                if re.match(pattern, text):
                    logger.debug(f"Plate {text} matched {country}/{region}: {pattern}")
                    return True, country, region

        # Try all patterns for this country
        if country in self.PATTERNS:
            for region_name, pattern in self.PATTERNS[country].items():
                if re.match(pattern, text):
                    logger.debug(f"Plate {text} matched {country}/{region_name}: {pattern}")
                    return True, country, region_name

        # Try all countries if no match yet
        for country_code, patterns in self.PATTERNS.items():
            for region_name, pattern in patterns.items():
                if re.match(pattern, text):
                    logger.info(f"Plate {text} matched {country_code}/{region_name} (auto-detected)")
                    return True, country_code, region_name

        logger.warning(f"Plate {text} did not match any known patterns")
        return False, None, None

    def process(
        self,
        raw_text: str,
        country: Optional[str] = None,
        region: Optional[str] = None,
        min_confidence: float = 0.0
    ) -> Optional[Dict[str, any]]:
        """
        Normalize and validate plate text

        Args:
            raw_text: Raw OCR output
            country: Country code
            region: Region/state code
            min_confidence: Minimum confidence to accept (placeholder for future use)

        Returns:
            Dict with normalized text, country, region if valid, else None
        """
        normalized = self.normalize(raw_text)

        if len(normalized) < 3:
            logger.warning(f"Plate text too short after normalization: {raw_text} → {normalized}")
            return None

        is_valid, detected_country, detected_region = self.validate(normalized, country, region)

        if is_valid:
            return {
                'text': normalized,
                'raw_text': raw_text,
                'country': detected_country,
                'region': detected_region,
                'is_valid': True
            }
        else:
            # Return normalized text even if validation failed (for manual review)
            return {
                'text': normalized,
                'raw_text': raw_text,
                'country': None,
                'region': None,
                'is_valid': False
            }


# Singleton instance
_validator = None

def get_validator(country: str = 'US', region: Optional[str] = None) -> PlateValidator:
    """Get or create singleton validator instance"""
    global _validator
    if _validator is None:
        _validator = PlateValidator(country, region)
    return _validator
