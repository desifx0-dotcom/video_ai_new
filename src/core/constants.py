"""
Application constants and enums.
"""

from enum import Enum


class VideoFormats(str, Enum):
    """Supported video formats."""

    MP4 = "mp4"
    AVI = "avi"
    MOV = "mov"
    MKV = "mkv"
    WEBM = "webm"
    FLV = "flv"
    WMV = "wmv"
    MPEG = "mpeg"
    MPG = "mpg"
    M4V = "m4v"
    _3GP = "3gp"
    OGV = "ogv"


class VideoQuality(str, Enum):
    """Video quality levels."""

    SD = "480p"
    HD = "720p"
    FULL_HD = "1080p"
    UHD_4K = "4k"
    UHD_4K_HDR = "4k+hdr"


class VideoCodec(str, Enum):
    """Video codecs."""

    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    AV1 = "av1"


class AudioCodec(str, Enum):
    """Audio codecs."""

    AAC = "aac"
    MP3 = "mp3"
    OPUS = "opus"
    VORBIS = "vorbis"


class ProcessingPriority(int, Enum):
    """Processing priority levels."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    VIP = 20


class ThumbnailStyle(str, Enum):
    """Thumbnail generation styles."""

    DEFAULT = "default"
    CINEMATIC = "cinematic"
    BRIGHT = "bright"
    DARK = "dark"
    VIBRANT = "vibrant"
    MINIMAL = "minimal"
    TEXT_HEAVY = "text_heavy"
    FACE_CLOSEUP = "face_closeup"
    ACTION_SHOT = "action_shot"


class Language(str, Enum):
    """Supported languages for transcription and translation."""

    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    CHINESE_SIMPLIFIED = "zh-CN"
    CHINESE_TRADITIONAL = "zh-TW"
    JAPANESE = "ja"
    KOREAN = "ko"
    RUSSIAN = "ru"
    PORTUGUESE = "pt"
    ITALIAN = "it"
    DUTCH = "nl"
    ARABIC = "ar"
    HINDI = "hi"
    BENGALI = "bn"
    URDU = "ur"
    TURKISH = "tr"
    VIETNAMESE = "vi"
    THAI = "th"
    INDONESIAN = "id"
    MALAY = "ms"
    SWAHILI = "sw"
    # Add more as needed


class AIModel(str, Enum):
    """AI models used in the system."""

    # Transcription
    WHISPER_SMALL = "whisper-1"
    WHISPER_MEDIUM = "whisper-medium"
    WHISPER_LARGE = "whisper-large"

    # Text Generation
    GEMINI_FLASH = "gemini-1.5-flash"
    GEMINI_PRO = "gemini-1.5-pro"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"

    # Image Generation
    STABLE_DIFFUSION_3_5 = "sd-3.5-medium"
    STABLE_DIFFUSION_XL = "sd-xl"
    STABLE_DIFFUSION_3_6_TURBO = "sd-3.6-turbo"

    # Vision
    GEMINI_PRO_VISION = "gemini-1.5-pro-vision"
    GPT_4_VISION = "gpt-4-vision"


class StorageProvider(str, Enum):
    """Storage providers."""

    LOCAL = "local"
    AWS_S3 = "s3"
    GOOGLE_CLOUD_STORAGE = "gcs"
    AZURE_BLOB = "azure"
    CLOUDFLARE_R2 = "r2"


class DatabaseProvider(str, Enum):
    """Database providers."""

    FIREBASE = "firebase"
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    MEMORY = "memory"


class EmailProvider(str, Enum):
    """Email providers."""

    SENDGRID = "sendgrid"
    RESEND = "resend"
    CONSOLE = "console"  # For development
    MOCK = "mock"  # For testing


class NotificationChannel(str, Enum):
    """Notification channels."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    WEBSOCKET = "websocket"
    IN_APP = "in_app"


# File size limits in bytes
FILE_SIZE_LIMITS = {
    "free": 100 * 1024 * 1024,  # 100MB
    "starter": 500 * 1024 * 1024,  # 500MB
    "pro": 2 * 1024 * 1024 * 1024,  # 2GB
    "plus": 5 * 1024 * 1024 * 1024,  # 5GB
    "enterprise": 10 * 1024 * 1024 * 1024,  # 10GB
}

# Video duration limits in seconds
DURATION_LIMITS = {
    "free": 3 * 60,  # 3 minutes
    "starter": 30 * 60,  # 30 minutes
    "pro": 60 * 60,  # 60 minutes
    "plus": 120 * 60,  # 120 minutes
    "enterprise": 300 * 60,  # 300 minutes (5 hours)
}

# Monthly video limits
MONTHLY_LIMITS = {
    "free": 3,
    "starter": 50,
    "pro": 100,
    "plus": 500,
    "enterprise": 10000,  # Essentially unlimited
}

# Video retention periods in days
RETENTION_PERIODS = {
    "free": 1,
    "starter": 7,
    "pro": 30,
    "plus": 90,
    "enterprise": 365,
}

# AI thumbnail steps per tier
THUMBNAIL_STEPS = {
    "free": 20,
    "starter": 30,
    "pro": 40,
    "plus": 50,
    "enterprise": 50,
}

# Text generation models per tier
TEXT_MODELS = {
    "free": AIModel.GEMINI_FLASH,
    "starter": AIModel.GEMINI_FLASH,
    "pro": AIModel.GEMINI_PRO,
    "plus": AIModel.GPT_4_TURBO,
    "enterprise": AIModel.GPT_4_TURBO,
}

# Processing queue priorities
QUEUE_PRIORITIES = {
    "free": "normal",
    "starter": "priority",
    "pro": "express",
    "plus": "vip",
    "enterprise": "vip",
}

# Default FFmpeg presets per quality
FFMPEG_PRESETS = {
    "480p": "ultrafast",
    "720p": "veryfast",
    "1080p": "medium",
    "4k": "slow",
    "4k+hdr": "veryslow",
}

# Default video bitrates per quality (in bps)
VIDEO_BITRATES = {
    "480p": 1_000_000,  # 1 Mbps
    "720p": 2_000_000,  # 2 Mbps
    "1080p": 5_000_000,  # 5 Mbps
    "4k": 15_000_000,  # 15 Mbps
    "4k+hdr": 25_000_000,  # 25 Mbps
}

# Default audio bitrates (in bps)
AUDIO_BITRATES = {
    "free": 128_000,  # 128 kbps
    "starter": 192_000,  # 192 kbps
    "pro": 256_000,  # 256 kbps
    "plus": 320_000,  # 320 kbps
    "enterprise": 320_000,
}

# Supported video styles
VIDEO_STYLES = [
    # Basic styles (available to all tiers)
    "cinematic",
    "bright",
    "dark",
    "vibrant",
    # Advanced styles (starter+)
    "gaming",
    "educational",
    "vlog",
    "documentary",
    # Professional styles (pro+)
    "corporate",
    "wedding",
    "real_estate",
    "travel",
    # Premium styles (plus+)
    "cinematic_pro",
    "artistic",
    "retro",
    "futuristic",
    # Custom styles (enterprise)
    "custom",
]

# Supported translation languages (ISO 639-1 codes)
SUPPORTED_LANGUAGES = [
    "en",
    "es",
    "fr",
    "de",
    "zh-CN",
    "zh-TW",
    "ja",
    "ko",
    "ru",
    "pt",
    "it",
    "nl",
    "ar",
    "hi",
    "bn",
    "ur",
    "tr",
    "vi",
    "th",
    "id",
    "ms",
    "sw",
    "pl",
    "uk",
    "ro",
    "hu",
    "sv",
    "da",
    "fi",
    "no",
    "cs",
    "el",
    "he",
    "fa",
    "bg",
    "sr",
    "hr",
    "sk",
    "sl",
    "et",
    "lv",
    "lt",
    "mt",
    "ga",
    "cy",
    "is",
    "mk",
    "sq",
    "bs",
    "ka",
    "hy",
    "az",
    "eu",
    "gl",
    "ca",
    "af",
    "zu",
    "xh",
    "st",
    "tn",
    "ts",
    "ss",
    "ve",
    "nr",
    "nso",
    "tw",
    "ak",
    "am",
    "bm",
    "ceb",
    "co",
    "eo",
    "fy",
    "gd",
    "gn",
    "gu",
    "ha",
    "haw",
    "hmn",
    "ig",
    "jw",
    "km",
    "ku",
    "ky",
    "lo",
    "lb",
    "lg",
    "ln",
    "lu",
    "mg",
    "mi",
    "mn",
    "mr",
    "my",
    "ne",
    "ny",
    "om",
    "pa",
    "ps",
    "rw",
    "sd",
    "si",
    "sm",
    "sn",
    "so",
    "su",
    "tg",
    "ti",
    "tk",
    "tl",
    "tt",
    "ug",
    "uz",
    "yi",
    "yo",
    "zza",
]
SUPPORTED_LANGUAGE_CODES = SUPPORTED_LANGUAGES

# Language metadata with names and native names
LANGUAGE_METADATA = {
    "en": {"name": "English", "native": "English", "rtl": False, "region": "Global"},
    "es": {
        "name": "Spanish",
        "native": "Español",
        "rtl": False,
        "region": "Europe/Americas",
    },
    "fr": {"name": "French", "native": "Français", "rtl": False, "region": "Europe"},
    "de": {"name": "German", "native": "Deutsch", "rtl": False, "region": "Europe"},
    "it": {"name": "Italian", "native": "Italiano", "rtl": False, "region": "Europe"},
    "pt": {
        "name": "Portuguese",
        "native": "Português",
        "rtl": False,
        "region": "Europe/Americas",
    },
    "ru": {
        "name": "Russian",
        "native": "Русский",
        "rtl": False,
        "region": "Europe/Asia",
    },
    "zh-CN": {
        "name": "Chinese (Simplified)",
        "native": "简体中文",
        "rtl": False,
        "region": "Asia",
    },
    "zh-TW": {
        "name": "Chinese (Traditional)",
        "native": "繁體中文",
        "rtl": False,
        "region": "Asia",
    },
    "ja": {"name": "Japanese", "native": "日本語", "rtl": False, "region": "Asia"},
    "ko": {"name": "Korean", "native": "한국어", "rtl": False, "region": "Asia"},
    "ar": {"name": "Arabic", "native": "العربية", "rtl": True, "region": "Middle East"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "rtl": False, "region": "Asia"},
    "bn": {"name": "Bengali", "native": "বাংলা", "rtl": False, "region": "Asia"},
    "ur": {"name": "Urdu", "native": "اردو", "rtl": True, "region": "Asia"},
    "tr": {
        "name": "Turkish",
        "native": "Türkçe",
        "rtl": False,
        "region": "Europe/Asia",
    },
    "vi": {
        "name": "Vietnamese",
        "native": "Tiếng Việt",
        "rtl": False,
        "region": "Asia",
    },
    "th": {"name": "Thai", "native": "ไทย", "rtl": False, "region": "Asia"},
    "id": {
        "name": "Indonesian",
        "native": "Bahasa Indonesia",
        "rtl": False,
        "region": "Asia",
    },
    "ms": {"name": "Malay", "native": "Bahasa Melayu", "rtl": False, "region": "Asia"},
    "sw": {"name": "Swahili", "native": "Kiswahili", "rtl": False, "region": "Africa"},
    "pl": {"name": "Polish", "native": "Polski", "rtl": False, "region": "Europe"},
    "uk": {
        "name": "Ukrainian",
        "native": "Українська",
        "rtl": False,
        "region": "Europe",
    },
    "ro": {"name": "Romanian", "native": "Română", "rtl": False, "region": "Europe"},
    "hu": {"name": "Hungarian", "native": "Magyar", "rtl": False, "region": "Europe"},
    "sv": {"name": "Swedish", "native": "Svenska", "rtl": False, "region": "Europe"},
    "da": {"name": "Danish", "native": "Dansk", "rtl": False, "region": "Europe"},
    "fi": {"name": "Finnish", "native": "Suomi", "rtl": False, "region": "Europe"},
    "no": {"name": "Norwegian", "native": "Norsk", "rtl": False, "region": "Europe"},
    "cs": {"name": "Czech", "native": "Čeština", "rtl": False, "region": "Europe"},
    "el": {"name": "Greek", "native": "Ελληνικά", "rtl": False, "region": "Europe"},
    "he": {"name": "Hebrew", "native": "עברית", "rtl": True, "region": "Middle East"},
    "fa": {"name": "Persian", "native": "فارسی", "rtl": True, "region": "Middle East"},
    "bg": {
        "name": "Bulgarian",
        "native": "Български",
        "rtl": False,
        "region": "Europe",
    },
    "sr": {"name": "Serbian", "native": "Српски", "rtl": False, "region": "Europe"},
    "hr": {"name": "Croatian", "native": "Hrvatski", "rtl": False, "region": "Europe"},
    "sk": {"name": "Slovak", "native": "Slovenčina", "rtl": False, "region": "Europe"},
    "sl": {
        "name": "Slovenian",
        "native": "Slovenščina",
        "rtl": False,
        "region": "Europe",
    },
    "et": {"name": "Estonian", "native": "Eesti", "rtl": False, "region": "Europe"},
    "lv": {"name": "Latvian", "native": "Latviešu", "rtl": False, "region": "Europe"},
    "lt": {
        "name": "Lithuanian",
        "native": "Lietuvių",
        "rtl": False,
        "region": "Europe",
    },
    "mt": {"name": "Maltese", "native": "Malti", "rtl": False, "region": "Europe"},
    "ga": {"name": "Irish", "native": "Gaeilge", "rtl": False, "region": "Europe"},
    "cy": {"name": "Welsh", "native": "Cymraeg", "rtl": False, "region": "Europe"},
    "is": {"name": "Icelandic", "native": "Íslenska", "rtl": False, "region": "Europe"},
    "mk": {
        "name": "Macedonian",
        "native": "Македонски",
        "rtl": False,
        "region": "Europe",
    },
    "sq": {"name": "Albanian", "native": "Shqip", "rtl": False, "region": "Europe"},
    "bs": {"name": "Bosnian", "native": "Bosanski", "rtl": False, "region": "Europe"},
    "ka": {
        "name": "Georgian",
        "native": "ქართული",
        "rtl": False,
        "region": "Europe/Asia",
    },
    "hy": {"name": "Armenian", "native": "Հայերեն", "rtl": False, "region": "Asia"},
    "az": {
        "name": "Azerbaijani",
        "native": "Azərbaycan",
        "rtl": False,
        "region": "Asia",
    },
    "eu": {"name": "Basque", "native": "Euskara", "rtl": False, "region": "Europe"},
    "gl": {"name": "Galician", "native": "Galego", "rtl": False, "region": "Europe"},
    "ca": {"name": "Catalan", "native": "Català", "rtl": False, "region": "Europe"},
    "af": {
        "name": "Afrikaans",
        "native": "Afrikaans",
        "rtl": False,
        "region": "Africa",
    },
    "zu": {"name": "Zulu", "native": "isiZulu", "rtl": False, "region": "Africa"},
    "xh": {"name": "Xhosa", "native": "isiXhosa", "rtl": False, "region": "Africa"},
    "st": {"name": "Sesotho", "native": "Sesotho", "rtl": False, "region": "Africa"},
    "tn": {"name": "Setswana", "native": "Setswana", "rtl": False, "region": "Africa"},
    "ts": {"name": "Tsonga", "native": "Xitsonga", "rtl": False, "region": "Africa"},
    "ss": {"name": "Swati", "native": "SiSwati", "rtl": False, "region": "Africa"},
    "ve": {"name": "Venda", "native": "Tshivenḓa", "rtl": False, "region": "Africa"},
    "nr": {"name": "Ndebele", "native": "isiNdebele", "rtl": False, "region": "Africa"},
    "nso": {
        "name": "Northern Sotho",
        "native": "Sesotho sa Leboa",
        "rtl": False,
        "region": "Africa",
    },
    "tw": {"name": "Twi", "native": "Twi", "rtl": False, "region": "Africa"},
    "ak": {"name": "Akan", "native": "Akan", "rtl": False, "region": "Africa"},
    "am": {"name": "Amharic", "native": "አማርኛ", "rtl": False, "region": "Africa"},
    "bm": {"name": "Bambara", "native": "Bamanankan", "rtl": False, "region": "Africa"},
    "ceb": {"name": "Cebuano", "native": "Cebuano", "rtl": False, "region": "Asia"},
    "co": {"name": "Corsican", "native": "Corsu", "rtl": False, "region": "Europe"},
    "eo": {
        "name": "Esperanto",
        "native": "Esperanto",
        "rtl": False,
        "region": "Constructed",
    },
    "fy": {"name": "Frisian", "native": "Frysk", "rtl": False, "region": "Europe"},
    "gd": {
        "name": "Scottish Gaelic",
        "native": "Gàidhlig",
        "rtl": False,
        "region": "Europe",
    },
    "gn": {"name": "Guaraní", "native": "Avañe'ẽ", "rtl": False, "region": "Americas"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "rtl": False, "region": "Asia"},
    "ha": {"name": "Hausa", "native": "Hausa", "rtl": False, "region": "Africa"},
    "haw": {
        "name": "Hawaiian",
        "native": "ʻŌlelo Hawaiʻi",
        "rtl": False,
        "region": "Oceania",
    },
    "hmn": {"name": "Hmong", "native": "Hmoob", "rtl": False, "region": "Asia"},
    "ig": {"name": "Igbo", "native": "Igbo", "rtl": False, "region": "Africa"},
    "jw": {"name": "Javanese", "native": "Basa Jawa", "rtl": False, "region": "Asia"},
    "km": {"name": "Khmer", "native": "ភាសាខ្មែរ", "rtl": False, "region": "Asia"},
    "ku": {"name": "Kurdish", "native": "Kurdî", "rtl": True, "region": "Middle East"},
    "ky": {"name": "Kyrgyz", "native": "Кыргызча", "rtl": False, "region": "Asia"},
    "lo": {"name": "Lao", "native": "ລາວ", "rtl": False, "region": "Asia"},
    "lb": {
        "name": "Luxembourgish",
        "native": "Lëtzebuergesch",
        "rtl": False,
        "region": "Europe",
    },
    "lg": {"name": "Ganda", "native": "Luganda", "rtl": False, "region": "Africa"},
    "ln": {"name": "Lingala", "native": "Lingála", "rtl": False, "region": "Africa"},
    "lu": {
        "name": "Luba-Katanga",
        "native": "Tshiluba",
        "rtl": False,
        "region": "Africa",
    },
    "mg": {"name": "Malagasy", "native": "Malagasy", "rtl": False, "region": "Africa"},
    "mi": {
        "name": "Māori",
        "native": "Te Reo Māori",
        "rtl": False,
        "region": "Oceania",
    },
    "mn": {"name": "Mongolian", "native": "Монгол", "rtl": False, "region": "Asia"},
    "mr": {"name": "Marathi", "native": "मराठी", "rtl": False, "region": "Asia"},
    "my": {"name": "Burmese", "native": "မြန်မာစာ", "rtl": False, "region": "Asia"},
    "ne": {"name": "Nepali", "native": "नेपाली", "rtl": False, "region": "Asia"},
    "ny": {"name": "Nyanja", "native": "Chichewa", "rtl": False, "region": "Africa"},
    "om": {"name": "Oromo", "native": "Afaan Oromoo", "rtl": False, "region": "Africa"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "rtl": False, "region": "Asia"},
    "ps": {"name": "Pashto", "native": "پښتو", "rtl": True, "region": "Asia"},
    "rw": {
        "name": "Kinyarwanda",
        "native": "Ikinyarwanda",
        "rtl": False,
        "region": "Africa",
    },
    "sd": {"name": "Sindhi", "native": "سنڌي", "rtl": True, "region": "Asia"},
    "si": {"name": "Sinhala", "native": "සිංහල", "rtl": False, "region": "Asia"},
    "sm": {
        "name": "Samoan",
        "native": "Gagana Sāmoa",
        "rtl": False,
        "region": "Oceania",
    },
    "sn": {"name": "Shona", "native": "chiShona", "rtl": False, "region": "Africa"},
    "so": {"name": "Somali", "native": "Soomaali", "rtl": False, "region": "Africa"},
    "su": {"name": "Sundanese", "native": "Basa Sunda", "rtl": False, "region": "Asia"},
    "tg": {"name": "Tajik", "native": "Тоҷикӣ", "rtl": False, "region": "Asia"},
    "ti": {"name": "Tigrinya", "native": "ትግርኛ", "rtl": False, "region": "Africa"},
    "tk": {"name": "Turkmen", "native": "Türkmen", "rtl": False, "region": "Asia"},
    "tl": {"name": "Tagalog", "native": "Tagalog", "rtl": False, "region": "Asia"},
    "tt": {"name": "Tatar", "native": "Татарча", "rtl": False, "region": "Asia"},
    "ug": {"name": "Uyghur", "native": "ئۇيغۇرچە", "rtl": True, "region": "Asia"},
    "uz": {"name": "Uzbek", "native": "Oʻzbek", "rtl": False, "region": "Asia"},
    "yi": {"name": "Yiddish", "native": "ייִדיש", "rtl": True, "region": "Europe"},
    "yo": {"name": "Yoruba", "native": "Yorùbá", "rtl": False, "region": "Africa"},
    "zza": {"name": "Zaza", "native": "Zazaki", "rtl": False, "region": "Asia"},
}

# Language detection confidence thresholds
LANGUAGE_CONFIDENCE_THRESHOLDS = {
    "high": 0.9,
    "medium": 0.7,
    "low": 0.5,
}

# Rate limit configurations (requests per hour)
RATE_LIMITS = {
    "free": 10,
    "starter": 50,
    "pro": 200,
    "plus": 1000,
    "enterprise": 10000,
}

# API endpoints that don't require authentication
PUBLIC_ENDPOINTS = [
    "/health",
    "/metrics",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/billing/webhook/stripe",
]

# Default pagination settings
PAGINATION_DEFAULTS = {
    "page": 1,
    "per_page": 20,
    "max_per_page": 100,
}

# Timezone constants
TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Australia/Sydney",
]

# MIME types for video files
VIDEO_MIME_TYPES = [
    "video/mp4",
    "video/x-msvideo",  # AVI
    "video/quicktime",  # MOV
    "video/x-matroska",  # MKV
    "video/webm",
    "video/x-flv",
    "video/x-ms-wmv",
    "video/mpeg",
]

# File extensions for video files
VIDEO_EXTENSIONS = [
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".flv",
    ".wmv",
    ".mpeg",
    ".mpg",
    ".m4v",
    ".3gp",
    ".ogv",
]

# Maximum file upload size in bytes (500mb)
MAX_UPLOAD_SIZE = 500 * 1024 * 1024

# Session timeout in seconds
SESSION_TIMEOUT = 3600  # 1 hour

# JWT token expiration in seconds
JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 hour
JWT_REFRESH_TOKEN_EXPIRES = 2592000  # 30 days

# Default currency
DEFAULT_CURRENCY = "USD"

# Supported currencies
SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"]

# Price tiers in USD
PRICE_TIERS = {
    "free": 0,
    "starter": 24,
    "pro": 79,
    "plus": 250,
    "enterprise": 999,  # Starting price
}

# Yearly discount percentage
YEARLY_DISCOUNT = 20  # 20% discount for yearly billing

# Trial period in days
TRIAL_PERIOD = 14

# Grace period for failed payments in days
PAYMENT_GRACE_PERIOD = 3

# Default language for new users
DEFAULT_LANGUAGE = "en"

# Default timezone for new users
DEFAULT_TIMEZONE = "UTC"

# Default video quality for new users
DEFAULT_QUALITY = "720p"

# Default video style for new users
DEFAULT_STYLE = "cinematic"

# Maximum retry attempts for failed processing
MAX_RETRY_ATTEMPTS = 3

# Delay between retries in seconds
RETRY_DELAYS = [60, 300, 900]  # 1 min, 5 min, 15 min

# Cleanup schedule for temporary files (in hours)
CLEANUP_SCHEDULE = 24

# Maximum age of temporary files in hours
MAX_TEMP_FILE_AGE = 24

# WebSocket event names
WEBSOCKET_EVENTS = {
    "CONNECT": "connect",
    "DISCONNECT": "disconnect",
    "VIDEO_UPLOADED": "video_uploaded",
    "VIDEO_PROCESSING": "video_processing",
    "VIDEO_COMPLETED": "video_completed",
    "VIDEO_FAILED": "video_failed",
    "PROGRESS_UPDATE": "progress_update",
    "TIER_UPGRADED": "tier_upgraded",
    "CREDITS_UPDATED": "credits_updated",
}

# Email templates
EMAIL_TEMPLATES = {
    "WELCOME": "welcome",
    "VERIFY_EMAIL": "verify_email",
    "PASSWORD_RESET": "password_reset",
    "TIER_UPGRADED": "tier_upgraded",
    "PAYMENT_RECEIVED": "payment_received",
    "PAYMENT_FAILED": "payment_failed",
    "VIDEO_COMPLETED": "video_completed",
    "VIDEO_FAILED": "video_failed",
    "CREDITS_LOW": "credits_low",
    "MONTHLY_SUMMARY": "monthly_summary",
}

# Feature flags
FEATURE_FLAGS = {
    "ENABLE_SILENT_DETECTION": True,
    "ENABLE_TRANSLATION": True,
    "ENABLE_VIDEO_STYLES": True,
    "ENABLE_AI_THUMBNAILS": True,
    "ENABLE_BATCH_PROCESSING": False,
    "ENABLE_CUSTOM_STYLES": False,
    "ENABLE_API_ACCESS": True,
    "ENABLE_WEBHOOKS": True,
    "ENABLE_ANALYTICS": True,
}

# Monitoring metrics
METRICS = {
    "ACTIVE_USERS": "active_users",
    "VIDEOS_PROCESSED": "videos_processed",
    "PROCESSING_TIME": "processing_time",
    "AI_COSTS": "ai_costs",
    "REVENUE": "revenue",
    "CONVERSION_RATE": "conversion_rate",
    "ERROR_RATE": "error_rate",
    "QUEUE_LENGTH": "queue_length",
    "UPTIME": "uptime",
}

# Environment modes
ENVIRONMENT = {
    "DEVELOPMENT": "development",
    "TESTING": "testing",
    "STAGING": "staging",
    "PRODUCTION": "production",
}

ALLOWED_VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
ALLOWED_VIDEO_MIME_TYPES = VIDEO_MIME_TYPES
