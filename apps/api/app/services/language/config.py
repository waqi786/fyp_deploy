from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Language:
    code: str
    english_name: str
    native_name: str
    direction: str = "ltr"
    provider_code: str | None = None

SUPPORTED_LANGUAGES = (
    Language("en", "English", "English"),
    Language("ur", "Urdu", "\u0627\u0631\u062f\u0648", "rtl"),
    Language("ar", "Arabic", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629", "rtl"),
    Language("fa", "Persian", "\u0641\u0627\u0631\u0633\u06cc", "rtl"),
    Language("hi", "Hindi", "\u0939\u093f\u0928\u094d\u0926\u0940"),
    Language("bn", "Bengali", "\u09ac\u09be\u0982\u09b2\u09be"),
    Language("pa-Arab", "Punjabi (Shahmukhi)", "\u067e\u0646\u062c\u0627\u0628\u06cc", "rtl", "pa"),
    Language("tr", "Turkish", "T\u00fcrk\u00e7e"),
    Language("id", "Indonesian", "Bahasa Indonesia"),
    Language("ms", "Malay", "Bahasa Melayu"),
    Language("zh-Hans", "Chinese (Simplified)", "\u7b80\u4f53\u4e2d\u6587", "ltr", "zh-CN"),
    Language("zh-Hant", "Chinese (Traditional)", "\u7e41\u9ad4\u4e2d\u6587", "ltr", "zh-TW"),
    Language("ja", "Japanese", "\u65e5\u672c\u8a9e"),
    Language("ko", "Korean", "\ud55c\uad6d\uc5b4"),
    Language("vi", "Vietnamese", "Ti\u1ebfng Vi\u1ec7t"),
    Language("th", "Thai", "\u0e44\u0e17\u0e22"),
    Language("es", "Spanish", "Espa\u00f1ol"),
    Language("pt-BR", "Portuguese (Brazil)", "Portugu\u00eas (Brasil)", "ltr", "pt"),
    Language("pt-PT", "Portuguese (Portugal)", "Portugu\u00eas (Portugal)", "ltr", "pt"),
    Language("fr", "French", "Fran\u00e7ais"),
    Language("de", "German", "Deutsch"),
    Language("it", "Italian", "Italiano"),
    Language("nl", "Dutch", "Nederlands"),
    Language("pl", "Polish", "Polski"),
    Language("ru", "Russian", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439"),
    Language("uk", "Ukrainian", "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430"),
    Language("sv", "Swedish", "Svenska"),
    Language("el", "Greek", "\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac"),
    Language("ro", "Romanian", "Rom\u00e2n\u0103"),
    Language("cs", "Czech", "\u010ce\u0161tina"),
    Language("hu", "Hungarian", "Magyar"),
    Language("he", "Hebrew", "\u05e2\u05d1\u05e8\u05d9\u05ea", "rtl", "iw"),
    Language("sw", "Swahili", "Kiswahili"),
    Language("ta", "Tamil", "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd"),
    Language("ps", "Pashto", "\u067e\u069a\u062a\u0648", "rtl"),
    Language("sd", "Sindhi", "\u0633\u0646\u068c\u06cc", "rtl"),
    Language("mr", "Marathi", "\u092e\u0930\u093e\u0920\u0940"),
    Language("te", "Telugu", "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41"),
    Language("gu", "Gujarati", "\u0a97\u0ac1\u0a9c\u0ab0\u0abe\u0aa4\u0ac0"),
    Language("kn", "Kannada", "\u0c95\u0ca8\u0ccd\u0ca8\u0ca1"),
    Language("ml", "Malayalam", "\u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02"),
    Language("pa-Guru", "Punjabi (Gurmukhi)", "\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40", "ltr", "pa"),
    Language("fil", "Filipino", "Filipino"),
    Language("ha", "Hausa", "Hausa"),
    Language("am", "Amharic", "\u12a0\u121b\u122d\u129b"),
    Language("yo", "Yoruba", "\u00c8d\u00e8 Yor\u00f9b\u00e1"),
    Language("jv", "Javanese", "Basa Jawa"),
)
LANGUAGES_BY_CODE = {language.code.casefold(): language for language in SUPPORTED_LANGUAGES}
LANGUAGE_ALIASES = {"zh": "zh-hans", "zh-cn": "zh-hans", "zh-sg": "zh-hans", "zh-tw": "zh-hant", "zh-hk": "zh-hant", "pa": "pa-arab", "pnb": "pa-arab", "pa-guru": "pa-guru", "pa-in": "pa-guru", "pt": "pt-br", "iw": "he"}

def canonical_language_code(value: str | None, *, default: str = "en") -> str:
    key = (value or default).strip().replace("_", "-").casefold()
    key = LANGUAGE_ALIASES.get(key, key)
    language = LANGUAGES_BY_CODE.get(key)
    if language is None:
        raise ValueError(f"Unsupported language code: {value}")
    return language.code

def language_profile(value: str | None) -> Language:
    return LANGUAGES_BY_CODE[canonical_language_code(value).casefold()]

def detect_language(text: str) -> tuple[str, float]:
    """Fast script/lexical detector; common-script guesses stay deliberately low-confidence."""
    value = (text or "").strip().casefold()
    if not value:
        return "en", 0.0
    chars = list(value)
    urdu_specific = set("\u0679\u0688\u0691\u06ba\u06be\u06c1\u06af\u0698\u0686\u067e\u06d2")
    persian_specific = set("\u067e\u0686\u0698\u06af\u06a9\u06cc")
    arabic_count = sum("\u0600" <= c <= "\u06ff" for c in chars)
    urdu_count = sum(c in urdu_specific for c in chars)
    persian_count = sum(c in persian_specific for c in chars)
    if arabic_count:
        if urdu_count >= 2:
            return "ur", min(0.99, 0.68 + urdu_count / max(len(chars), 1))
        if persian_count >= 2:
            return "fa", min(0.96, 0.66 + persian_count / max(len(chars), 1))
        return "ar", min(0.94, 0.6 + arabic_count / max(len(chars), 1))
    ranges = (("hi", "\u0900", "\u097f"), ("bn", "\u0980", "\u09ff"), ("ta", "\u0b80", "\u0bff"), ("th", "\u0e00", "\u0e7f"), ("he", "\u0590", "\u05ff"), ("mr", "\u0900", "\u097f"), ("te", "\u0c00", "\u0c7f"), ("gu", "\u0a80", "\u0aff"), ("kn", "\u0c80", "\u0cff"), ("ml", "\u0d00", "\u0d7f"), ("pa-Guru", "\u0a00", "\u0a7f"))
    for code, low, high in ranges:
        count = sum(low <= c <= high for c in chars)
        if count >= 2:
            return code, min(0.99, 0.72 + count / max(len(chars), 1))
    if any("\u3400" <= c <= "\u9fff" for c in chars):
        return "zh-Hans", 0.75
    if any("\u3040" <= c <= "\u30ff" for c in chars):
        return "ja", 0.92
    if any("\uac00" <= c <= "\ud7af" for c in chars):
        return "ko", 0.92
    markers = {
        "es": (" el ", " la ", " de ", " y ", "\u00f3n"),
        "pt-BR": (" n\u00e3o ", " uma ", " para ", "\u00e7\u00e3o", "\u00f5es"),
        "fr": (" le ", " les ", " des ", " une ", "\u00e7"),
        "de": (" der ", " die ", " und ", " f\u00fcr ", " nicht "),
        "tr": (" ve ", " i\u00e7in ", " bir ", " olan "),
        "id": (" yang ", " dan ", " untuk ", " dengan "),
        "ru": ("\u0438", "\u0434\u043b\u044f", "\u043d\u0435"),
        "uk": ("\u0442\u0430", "\u0434\u043b\u044f", "\u0446\u0435"),
    }
    padded = f" {value} "
    ranked = sorted(((sum(marker in padded for marker in values), code) for code, values in markers.items()), reverse=True)
    if ranked and ranked[0][0] >= 2:
        return ranked[0][1], min(0.78, 0.5 + ranked[0][0] * 0.08)
    return "en", 0.55
