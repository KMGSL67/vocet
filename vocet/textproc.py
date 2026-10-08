"""Post-processing: from what the model heard to what gets inserted.

Deterministic rules only, no language model, so nothing is ever rewritten
behind your back. Each step is something you switched on or typed in yourself:

1. Filler words are removed, per language ("um", "uh"; German "äh", "ähm"; French "euh";
   Spanish "eh"; Chinese 嗯, 呃; Hindi अं, उम्म) (setting, on by default).
2. Dictionary replacements: "cube ernetes" -> "Kubernetes" (whole words, any case).
3. Snippets: saying a trigger phrase inserts its text ("my address" -> the address).

Per-language writing rules: Chinese gets no spaces between characters and full-width
punctuation (，。？！：；); Hindi stays in Devanagari (nothing here changes the script).

The dictionary also feeds the speech model a hint list (see speech.py), so it
tends to hear those words right in the first place. The replacements here are
the safety net for when it doesn't.
"""

import re

# Fillers per language, whole words only. They must be per language: "um" is filler in English but a
# real German word ("um halb drei" = at half past two). Only sounds that are never words in that
# language ("mm" is not one: "5 mm"); softer fillers (ben, este, 那个, मतलब) carry meaning elsewhere,
# so only the AI formatter may drop them.
_FILLERS = {
    "en": re.compile(r"(?<![\w'])(?:um+|uh+|uhm+|erm+|hmm+)(?![\w'])[,.]?\s*", re.IGNORECASE),
    "de": re.compile(r"(?<![\w'])(?:äh+m*|öh+m*|hmm+)(?![\w'])[,.]?\s*", re.IGNORECASE),
}
_OTHER_FILLERS = {"fr": r"euh+m*|heu+|hum+|hm+", "es": r"eh+m*|em+|mmm+|hmm+", "zh": r"[嗯呃]+",
                  "hi": r"अं+|उम्+म*|हम्म+|अम्म+"}
_DEVANAGARI = "\u0900-\u097f"
_CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_FULL_WIDTH = "\u3000-\u303f\uff00-\uffef"   # CJK punctuation (。、「」) and full-width forms (，？！)


def remove_fillers(text: str, language: str = "en") -> str:
    if language in _OTHER_FILLERS:
        return _remove_other_fillers(text, language)
    pattern = _FILLERS.get(language)
    if pattern is None:
        return text
    out = pattern.sub("", text)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.!?;:])", r"\1", out)
    if out and text[:1].isupper():  # "Um, so we..." -> "So we..."
        out = out[0].upper() + out[1:]
    return out


def _remove_other_fillers(text: str, language: str) -> str:
    """French, Spanish, Chinese, Hindi. A filler between two commas takes both commas with it."""
    w = _OTHER_FILLERS[language]
    if language == "zh":                  # no spaces in Chinese: nothing to join with
        out = re.sub(rf"[，,、]\s*(?:{w})\s*[，,、]", "，", text)
        out = re.sub(rf"(?:^|(?<=[，。！？、；：,.!?;:\s]))(?:{w})[，,、。.]?\s*", "", out)
        if "嗯" in text and not re.search(rf"[{_CJK}\w]", out):
            # 嗯 on its own is often an answer ("mm-hm, yes"), not a filler: keep it.
            return text.strip()
    else:
        left, right = rf"(?<![\w'{_DEVANAGARI}])", rf"(?![\w'{_DEVANAGARI}])"   # vowel signs aren't \w
        out = re.sub(rf"\s*,\s*{left}(?:{w}){right}\s*,\s*", " ", text, flags=re.IGNORECASE)
        out = re.sub(rf"{left}(?:{w}){right}[,.।]?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    # French puts a space before : ; ! ? ("objectif : "), so only , and . lose theirs there.
    out = re.sub(r"[ \t]+([,.])" if language == "fr" else r"[ \t]+([,.!?;:।])", r"\1", out)
    first = next((i for i, c in enumerate(out) if c.isalpha()), None)   # "Eh, ¿vienes?" -> "¿Vienes?"
    if first is not None and text.lstrip("¿¡")[:1].isupper():
        out = out[:first] + out[first].upper() + out[first + 1:]
    return out


_ZH_PUNCT = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}


def tidy_chinese(text: str) -> str:
    """Chinese is written without spaces and with full-width punctuation. Whisper (with ZH_PROMPT)
    writes "教授指出,记者" and "声明。": ASCII , . ? ! : ; right after a Chinese character become
    full-width (not in "3.5" or "Python."), and spaces between two Chinese characters go.
    Full-width punctuation already there is kept as it is."""
    text = re.sub(rf"(?<=[{_CJK}])[,.?!:;](?=\s|$|[{_CJK}{_FULL_WIDTH}\w])",
                  lambda m: _ZH_PUNCT[m.group()], text)
    text = re.sub(rf"(?<=[{_CJK}{_FULL_WIDTH}])[ \t]+(?=[{_CJK}{_FULL_WIDTH}])", "", text)
    return re.sub(rf"(?<=[{_FULL_WIDTH}])[ \t]+(?=\S)", "", text) if re.search(f"[{_CJK}]", text) else text


def join_pieces(texts: list[str]) -> str:
    """Joins the parts of a long recording: with a space, except between Chinese text."""
    out = ""
    for t in (t.strip() for t in texts):
        if not t:
            continue
        glue = "" if not out or re.match(f"[{_CJK}{_FULL_WIDTH}]", t) or re.search(f"[{_CJK}{_FULL_WIDTH}]$", out) \
            else " "
        out += glue + t
    return out


def ends_without_space(text: str) -> bool:
    """No space goes after text that ends in Chinese (a character or full-width punctuation):
    the next dictation continues right after it, as Chinese is written."""
    return bool(re.search(f"[{_CJK}{_FULL_WIDTH}]$", text))


def _phrase_pattern(phrase: str) -> re.Pattern:
    """Whole words only, except at a Chinese edge: Chinese has no spaces, so a Chinese word
    matches wherever it appears."""
    words = [re.escape(w) for w in phrase.split()]
    cjk = f"[{_CJK}]"
    left = "" if re.match(cjk, phrase.strip()) else rf"(?<![\w'{_DEVANAGARI}])"
    right = "" if re.search(f"{cjk}$", phrase.strip()) else rf"(?![\w'{_DEVANAGARI}])"
    return re.compile(left + r"[\s,]+".join(words) + right, re.IGNORECASE)


def apply_replacements(text: str, replacements: list[dict]) -> str:
    """replacements: [{"heard": "cube ernetes", "write": "Kubernetes"}, ...]"""
    for r in replacements:
        heard, write = r.get("heard", "").strip(), r.get("write", "").strip()
        if heard and write:
            text = _phrase_pattern(heard).sub(lambda _m, w=write: w, text)
    return text


def apply_snippets(text: str, snippets: list[dict]) -> str:
    """snippets: [{"trigger": "my email", "text": "me@example.com"}, ...]

    If the whole dictation is just the trigger ("My email."), the result is only
    the snippet, without the sentence punctuation the model added around it.
    """
    for s in snippets:
        trigger, expansion = s.get("trigger", "").strip(), s.get("text", "")
        if not trigger or not expansion:
            continue
        pattern = _phrase_pattern(trigger)
        if pattern.fullmatch(text.strip().strip(".!?,").strip()):
            return expansion
        text = pattern.sub(lambda _m, e=expansion: e, text)
    return text


def process(text: str, *, fillers: bool = True, replacements=(), snippets=(), language: str = "en") -> str:
    if fillers:
        text = remove_fillers(text, language)
    if language == "zh":
        text = tidy_chinese(text)
    text = apply_replacements(text, list(replacements))
    text = apply_snippets(text, list(snippets))
    return text.strip()


def vocabulary_prompt(words: list[str]) -> str:
    """The hint text given to Whisper. A plain comma list works well; keep it short,
    because Whisper only reads the first ~220 tokens of a prompt."""
    unique = list(dict.fromkeys(w.strip() for w in words if w.strip()))
    return ", ".join(unique[:60]) + "." if unique else ""
