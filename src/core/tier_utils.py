"""Tier utilities for determining user capabilities and limits."""

from typing import Dict, List, Any, Tuple
from datetime import datetime


def get_languages() -> List[Dict[str, str]]:
    """Get list of 120+ supported languages."""
    return [
        # Most Common Languages (Top 20)
        {
            "code": "en",
            "name": "English",
            "native": "English",
            "region": "Global",
            "rtl": False,
        },
        {
            "code": "es",
            "name": "Spanish",
            "native": "Español",
            "region": "Europe/Americas",
            "rtl": False,
        },
        {
            "code": "fr",
            "name": "French",
            "native": "Français",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "de",
            "name": "German",
            "native": "Deutsch",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "it",
            "name": "Italian",
            "native": "Italiano",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "pt",
            "name": "Portuguese",
            "native": "Português",
            "region": "Europe/Americas",
            "rtl": False,
        },
        {
            "code": "ru",
            "name": "Russian",
            "native": "Русский",
            "region": "Europe/Asia",
            "rtl": False,
        },
        {
            "code": "zh",
            "name": "Chinese (Simplified)",
            "native": "简体中文",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "zh-TW",
            "name": "Chinese (Traditional)",
            "native": "繁體中文",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ja",
            "name": "Japanese",
            "native": "日本語",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ko",
            "name": "Korean",
            "native": "한국어",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ar",
            "name": "Arabic",
            "native": "العربية",
            "region": "Middle East",
            "rtl": True,
        },
        {
            "code": "hi",
            "name": "Hindi",
            "native": "हिन्दी",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "bn",
            "name": "Bengali",
            "native": "বাংলা",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "pa",
            "name": "Punjabi",
            "native": "ਪੰਜਾਬੀ",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "jv",
            "name": "Javanese",
            "native": "Basa Jawa",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "te",
            "name": "Telugu",
            "native": "తెలుగు",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "mr",
            "name": "Marathi",
            "native": "मराठी",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ta",
            "name": "Tamil",
            "native": "தமிழ்",
            "region": "Asia",
            "rtl": False,
        },
        {"code": "ur", "name": "Urdu", "native": "اردو", "region": "Asia", "rtl": True},
        # European Languages
        {
            "code": "nl",
            "name": "Dutch",
            "native": "Nederlands",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "el",
            "name": "Greek",
            "native": "Ελληνικά",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "sv",
            "name": "Swedish",
            "native": "Svenska",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "da",
            "name": "Danish",
            "native": "Dansk",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "no",
            "name": "Norwegian",
            "native": "Norsk",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "fi",
            "name": "Finnish",
            "native": "Suomi",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "is",
            "name": "Icelandic",
            "native": "Íslenska",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "ga",
            "name": "Irish",
            "native": "Gaeilge",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "cy",
            "name": "Welsh",
            "native": "Cymraeg",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "gd",
            "name": "Scottish Gaelic",
            "native": "Gàidhlig",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "kw",
            "name": "Cornish",
            "native": "Kernewek",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "br",
            "name": "Breton",
            "native": "Brezhoneg",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "ca",
            "name": "Catalan",
            "native": "Català",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "gl",
            "name": "Galician",
            "native": "Galego",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "eu",
            "name": "Basque",
            "native": "Euskara",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "oc",
            "name": "Occitan",
            "native": "Occitan",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "sq",
            "name": "Albanian",
            "native": "Shqip",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "bs",
            "name": "Bosnian",
            "native": "Bosanski",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "hr",
            "name": "Croatian",
            "native": "Hrvatski",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "sr",
            "name": "Serbian",
            "native": "Српски",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "mk",
            "name": "Macedonian",
            "native": "Македонски",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "bg",
            "name": "Bulgarian",
            "native": "Български",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "ro",
            "name": "Romanian",
            "native": "Română",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "hu",
            "name": "Hungarian",
            "native": "Magyar",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "pl",
            "name": "Polish",
            "native": "Polski",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "cs",
            "name": "Czech",
            "native": "Čeština",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "sk",
            "name": "Slovak",
            "native": "Slovenčina",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "sl",
            "name": "Slovenian",
            "native": "Slovenščina",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "lv",
            "name": "Latvian",
            "native": "Latviešu",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "lt",
            "name": "Lithuanian",
            "native": "Lietuvių",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "et",
            "name": "Estonian",
            "native": "Eesti",
            "region": "Europe",
            "rtl": False,
        },
        {
            "code": "mt",
            "name": "Maltese",
            "native": "Malti",
            "region": "Europe",
            "rtl": False,
        },
        # Asian Languages
        {
            "code": "vi",
            "name": "Vietnamese",
            "native": "Tiếng Việt",
            "region": "Asia",
            "rtl": False,
        },
        {"code": "th", "name": "Thai", "native": "ไทย", "region": "Asia", "rtl": False},
        {"code": "lo", "name": "Lao", "native": "ລາວ", "region": "Asia", "rtl": False},
        {
            "code": "my",
            "name": "Burmese",
            "native": "မြန်မာစာ",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "km",
            "name": "Khmer",
            "native": "ភាសាខ្មែរ",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "id",
            "name": "Indonesian",
            "native": "Bahasa Indonesia",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ms",
            "name": "Malay",
            "native": "Bahasa Melayu",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "fil",
            "name": "Filipino",
            "native": "Filipino",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ceb",
            "name": "Cebuano",
            "native": "Cebuano",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "hmn",
            "name": "Hmong",
            "native": "Hmoob",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "mn",
            "name": "Mongolian",
            "native": "Монгол",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ne",
            "name": "Nepali",
            "native": "नेपाली",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "si",
            "name": "Sinhala",
            "native": "සිංහල",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "gu",
            "name": "Gujarati",
            "native": "ગુજરાતી",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "kn",
            "name": "Kannada",
            "native": "ಕನ್ನಡ",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ml",
            "name": "Malayalam",
            "native": "മലയാളം",
            "region": "Asia",
            "rtl": False,
        },
        {"code": "or", "name": "Odia", "native": "ଓଡ଼ିଆ", "region": "Asia", "rtl": False},
        {
            "code": "as",
            "name": "Assamese",
            "native": "অসমীয়া",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "mai",
            "name": "Maithili",
            "native": "मैथिली",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "sat",
            "name": "Santali",
            "native": "ᱥᱟᱱᱛᱟᱲᱤ",
            "region": "Asia",
            "rtl": False,
        },
        {
            "code": "ks",
            "name": "Kashmiri",
            "native": "कॉशुर",
            "region": "Asia",
            "rtl": True,
        },
        {
            "code": "sd",
            "name": "Sindhi",
            "native": "سنڌي",
            "region": "Asia",
            "rtl": True,
        },
        {
            "code": "ps",
            "name": "Pashto",
            "native": "پښتو",
            "region": "Asia",
            "rtl": True,
        },
        {
            "code": "dv",
            "name": "Divehi",
            "native": "ދިވެހި",
            "region": "Asia",
            "rtl": True,
        },
        # Middle Eastern & African Languages
        {
            "code": "fa",
            "name": "Persian",
            "native": "فارسی",
            "region": "Middle East",
            "rtl": True,
        },
        {
            "code": "ku",
            "name": "Kurdish",
            "native": "Kurdî",
            "region": "Middle East",
            "rtl": True,
        },
        {
            "code": "he",
            "name": "Hebrew",
            "native": "עברית",
            "region": "Middle East",
            "rtl": True,
        },
        {
            "code": "yi",
            "name": "Yiddish",
            "native": "ייִדיש",
            "region": "Europe",
            "rtl": True,
        },
        {
            "code": "am",
            "name": "Amharic",
            "native": "አማርኛ",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ti",
            "name": "Tigrinya",
            "native": "ትግርኛ",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "om",
            "name": "Oromo",
            "native": "Afaan Oromoo",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "so",
            "name": "Somali",
            "native": "Soomaali",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "sw",
            "name": "Swahili",
            "native": "Kiswahili",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "rw",
            "name": "Kinyarwanda",
            "native": "Ikinyarwanda",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "rn",
            "name": "Kirundi",
            "native": "Ikirundi",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "mg",
            "name": "Malagasy",
            "native": "Malagasy",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "st",
            "name": "Sesotho",
            "native": "Sesotho",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "tn",
            "name": "Setswana",
            "native": "Setswana",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ts",
            "name": "Tsonga",
            "native": "Xitsonga",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ss",
            "name": "Swati",
            "native": "SiSwati",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ve",
            "name": "Venda",
            "native": "Tshivenḓa",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "xh",
            "name": "Xhosa",
            "native": "isiXhosa",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "zu",
            "name": "Zulu",
            "native": "isiZulu",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "af",
            "name": "Afrikaans",
            "native": "Afrikaans",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ha",
            "name": "Hausa",
            "native": "Hausa",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ig",
            "name": "Igbo",
            "native": "Igbo",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "yo",
            "name": "Yoruba",
            "native": "Yorùbá",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "ff",
            "name": "Fulah",
            "native": "Fulfulde",
            "region": "Africa",
            "rtl": False,
        },
        {
            "code": "wo",
            "name": "Wolof",
            "native": "Wolof",
            "region": "Africa",
            "rtl": False,
        },
        # Indigenous & Regional Languages
        {
            "code": "mi",
            "name": "Māori",
            "native": "Te Reo Māori",
            "region": "Oceania",
            "rtl": False,
        },
        {
            "code": "haw",
            "name": "Hawaiian",
            "native": "ʻŌlelo Hawaiʻi",
            "region": "Oceania",
            "rtl": False,
        },
        {
            "code": "sm",
            "name": "Samoan",
            "native": "Gagana Sāmoa",
            "region": "Oceania",
            "rtl": False,
        },
        {
            "code": "to",
            "name": "Tongan",
            "native": "Lea faka-Tonga",
            "region": "Oceania",
            "rtl": False,
        },
        {
            "code": "fj",
            "name": "Fijian",
            "native": "Na Vosa Vakaviti",
            "region": "Oceania",
            "rtl": False,
        },
        {
            "code": "ty",
            "name": "Tahitian",
            "native": "Reo Tahiti",
            "region": "Oceania",
            "rtl": False,
        },
        {
            "code": "iu",
            "name": "Inuktitut",
            "native": "ᐃᓄᒃᑎᑐᑦ",
            "region": "Americas",
            "rtl": False,
        },
        {
            "code": "cr",
            "name": "Cree",
            "native": "ᓀᐦᐃᔭᐍᐏᐣ",
            "region": "Americas",
            "rtl": False,
        },
        {
            "code": "oj",
            "name": "Ojibwe",
            "native": "ᐊᓂᔑᓈᐯᒧᐎᓐ",
            "region": "Americas",
            "rtl": False,
        },
        {
            "code": "qu",
            "name": "Quechua",
            "native": "Runa Simi",
            "region": "Americas",
            "rtl": False,
        },
        {
            "code": "ay",
            "name": "Aymara",
            "native": "Aymar aru",
            "region": "Americas",
            "rtl": False,
        },
        {
            "code": "gn",
            "name": "Guaraní",
            "native": "Avañe'ẽ",
            "region": "Americas",
            "rtl": False,
        },
        {
            "code": "nv",
            "name": "Navajo",
            "native": "Diné bizaad",
            "region": "Americas",
            "rtl": False,
        },
        # Constructed Languages
        {
            "code": "eo",
            "name": "Esperanto",
            "native": "Esperanto",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "ia",
            "name": "Interlingua",
            "native": "Interlingua",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "vo",
            "name": "Volapük",
            "native": "Volapük",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "tlh",
            "name": "Klingon",
            "native": "tlhIngan Hol",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "qya",
            "name": "Quenya",
            "native": "Quenya",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "sjn",
            "name": "Sindarin",
            "native": "Sindarin",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "doth",
            "name": "Dothraki",
            "native": "Dothraki",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "val",
            "name": "Valyrian",
            "native": "Valyrio",
            "region": "Constructed",
            "rtl": False,
        },
        {
            "code": "navi",
            "name": "Na'vi",
            "native": "Lì'fya leNa'vi",
            "region": "Constructed",
            "rtl": False,
        },
    ]


def get_timezones() -> List[str]:
    """Get list of common timezones."""
    return [
        "UTC",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Phoenix",
        "America/Anchorage",
        "America/Honolulu",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Europe/Rome",
        "Europe/Madrid",
        "Europe/Amsterdam",
        "Europe/Brussels",
        "Europe/Vienna",
        "Europe/Stockholm",
        "Europe/Oslo",
        "Europe/Copenhagen",
        "Europe/Warsaw",
        "Europe/Prague",
        "Europe/Budapest",
        "Europe/Athens",
        "Europe/Helsinki",
        "Europe/Istanbul",
        "Europe/Moscow",
        "Asia/Dubai",
        "Asia/Kolkata",
        "Asia/Bangkok",
        "Asia/Hong_Kong",
        "Asia/Shanghai",
        "Asia/Tokyo",
        "Asia/Seoul",
        "Asia/Singapore",
        "Australia/Perth",
        "Australia/Adelaide",
        "Australia/Sydney",
        "Australia/Brisbane",
        "Australia/Melbourne",
        "Pacific/Auckland",
        "Pacific/Honolulu",
    ]


def get_available_qualities(tier: str) -> List[Dict[str, Any]]:
    """Get available video qualities based on user tier."""
    all_qualities = [
        {
            "value": "480p",
            "label": "480p (SD)",
            "available": True,
            "required_tier": "free",
        },
        {
            "value": "720p",
            "label": "720p (HD)",
            "available": True,
            "required_tier": "free",
        },
        {
            "value": "1080p",
            "label": "1080p (Full HD)",
            "available": True,
            "required_tier": "starter",
        },
        {
            "value": "1440p",
            "label": "1440p (2K)",
            "available": False,
            "required_tier": "pro",
        },
        {
            "value": "2160p",
            "label": "2160p (4K)",
            "available": False,
            "required_tier": "plus",
        },
    ]

    tier_rank = {"free": 0, "starter": 1, "pro": 2, "plus": 3, "enterprise": 4}

    user_rank = tier_rank.get(tier, 0)

    for quality in all_qualities:
        required_rank = tier_rank.get(quality["required_tier"], 0)
        quality["available"] = user_rank >= required_rank

    return all_qualities


def get_available_styles(tier: str) -> List[Dict[str, Any]]:
    """Get available video styles based on user tier."""
    all_styles = [
        {
            "id": "cinematic",
            "name": "Cinematic",
            "description": "Movie-like color grading and aspect ratio",
            "available": True,
            "required_tier": "free",
        },
        {
            "id": "vintage",
            "name": "Vintage",
            "description": "Warm, retro film look with grain",
            "available": True,
            "required_tier": "free",
        },
        {
            "id": "black_and_white",
            "name": "Black & White",
            "description": "Classic monochrome effect",
            "available": True,
            "required_tier": "free",
        },
        {
            "id": "educational",
            "name": "Educational",
            "description": "Bright, clear visuals with text overlay support",
            "available": True,
            "required_tier": "starter",
        },
        {
            "id": "gaming",
            "name": "Gaming",
            "description": "High contrast, vibrant colors for gameplay",
            "available": True,
            "required_tier": "starter",
        },
        {
            "id": "vlog",
            "name": "Vlog",
            "description": "Natural, balanced look for personal videos",
            "available": True,
            "required_tier": "starter",
        },
        {
            "id": "cinematic_pro",
            "name": "Cinematic Pro",
            "description": "Advanced color grading with LUT support",
            "available": False,
            "required_tier": "pro",
        },
        {
            "id": "anime",
            "name": "Anime",
            "description": "Stylized filter for animated content",
            "available": False,
            "required_tier": "pro",
        },
        {
            "id": "music_video",
            "name": "Music Video",
            "description": "Dynamic effects and transitions",
            "available": False,
            "required_tier": "plus",
        },
        {
            "id": "corporate",
            "name": "Corporate",
            "description": "Professional, clean look for business",
            "available": False,
            "required_tier": "enterprise",
        },
        {
            "id": "custom_lut",
            "name": "Custom LUT",
            "description": "Upload and apply your own LUTs",
            "available": False,
            "required_tier": "enterprise",
        },
    ]

    tier_rank = {"free": 0, "starter": 1, "pro": 2, "plus": 3, "enterprise": 4}

    user_rank = tier_rank.get(tier, 0)

    for style in all_styles:
        required_rank = tier_rank.get(style["required_tier"], 0)
        style["available"] = user_rank >= required_rank

    return all_styles


def get_rate_limits() -> Dict[str, int]:
    """Get API rate limits per tier."""
    return {"free": 100, "starter": 500, "pro": 2000, "plus": 5000, "enterprise": 10000}


def get_tier_color(tier: str) -> str:
    """Get Bootstrap color class for tier badge."""
    colors = {
        "free": "secondary",
        "starter": "primary",
        "pro": "success",
        "plus": "warning",
        "enterprise": "danger",
    }
    return colors.get(tier, "secondary")


def get_max_duration(tier: str) -> int:
    """Get max video duration in minutes based on tier."""
    durations = {"free": 3, "starter": 15, "pro": 60, "plus": 120, "enterprise": 240}
    return durations.get(tier, 3)


def get_retention_days(tier: str) -> int:
    """Get video retention period in days based on tier."""
    retention = {"free": 1, "starter": 7, "pro": 30, "plus": 90, "enterprise": 365}
    return retention.get(tier, 1)


def get_max_quality(tier: str) -> str:
    """Get max video quality based on tier."""
    qualities = {
        "free": "720p",
        "starter": "1080p",
        "pro": "1440p",
        "plus": "2160p",
        "enterprise": "2160p",
    }
    return qualities.get(tier, "720p")


def get_ai_thumbnails_count(tier: str) -> int:
    """Get number of AI-generated thumbnails based on tier."""
    counts = {"free": 1, "starter": 3, "pro": 5, "plus": 10, "enterprise": 20}
    return counts.get(tier, 1)


def get_queue_priority(tier: str) -> str:
    """Get processing queue priority based on tier."""
    priorities = {
        "free": "Normal",
        "starter": "Normal",
        "pro": "High",
        "plus": "Highest",
        "enterprise": "Real-time",
    }
    return priorities.get(tier, "Normal")


def get_monthly_video_limit(tier: str) -> int:
    """Get monthly video processing limit based on tier."""
    limits = {"free": 3, "starter": 50, "pro": 100, "plus": 500, "enterprise": 10000}
    return limits.get(tier, 3)


def get_credits_per_minute(tier: str) -> float:
    """Get credits consumed per minute of video based on tier."""
    rates = {"free": 1.0, "starter": 0.8, "pro": 0.5, "plus": 0.3, "enterprise": 0.1}
    return rates.get(tier, 1.0)


def can_use_feature(tier: str, feature: str) -> bool:
    """Check if tier can use a specific feature."""
    features = {
        "silent_video_detection": ["free", "starter", "pro", "plus", "enterprise"],
        "auto_translate": ["starter", "pro", "plus", "enterprise"],
        "custom_styles": ["pro", "plus", "enterprise"],
        "batch_processing": ["pro", "plus", "enterprise"],
        "api_access": ["starter", "pro", "plus", "enterprise"],
        "priority_support": ["plus", "enterprise"],
        "white_label": ["enterprise"],
        "sso": ["enterprise"],
    }

    allowed_tiers = features.get(feature, [])
    return tier in allowed_tiers


def get_upgrade_options(current_tier: str) -> List[Dict[str, Any]]:
    """Get available upgrade options from current tier."""
    all_tiers = ["free", "starter", "pro", "plus", "enterprise"]
    current_index = all_tiers.index(current_tier) if current_tier in all_tiers else 0

    options = []
    for i, tier in enumerate(all_tiers):
        if i > current_index:
            options.append(
                {
                    "tier": tier,
                    "name": tier.capitalize(),
                    "price_monthly": get_price(tier, "monthly"),
                    "price_yearly": get_price(tier, "yearly"),
                    "video_limit": get_monthly_video_limit(tier),
                    "max_duration": get_max_duration(tier),
                    "quality": get_max_quality(tier),
                    "retention": get_retention_days(tier),
                    "ai_thumbnails": get_ai_thumbnails_count(tier),
                    "priority": get_queue_priority(tier),
                }
            )

    return options


def get_price(tier: str, interval: str = "monthly") -> float:
    """Get price for tier."""
    prices = {
        "free": {"monthly": 0, "yearly": 0},
        "starter": {"monthly": 24, "yearly": 240},
        "pro": {"monthly": 79, "yearly": 790},
        "plus": {"monthly": 249, "yearly": 2490},
        "enterprise": {"monthly": 999, "yearly": 9990},
    }
    return prices.get(tier, {}).get(interval, 0)
