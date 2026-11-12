# cleaning.py - Script för att rensa sektionernas text INNAN chunking sker.
# Syftet med scriptet är att agera som T'et i 'ETL'.
#
# Kod: Engelska
# Kommentarer: Svenska
#
# Scriptet ska vara SOURCE AGNOSTIC(Källagnostiskt): Samma regler ska gälla oavsett om text kom ur PDF, markdown eller transcript.
# Ren och dum funktion, ingen I/O, ingen databas. Lätt att testa med str precis som chunker.py scriptet.
#
# Version 0 - Naivaste och lättaste versionen som är mätt mot hela korpusen.

import html
import re

# ====== Konstanter ======
# Markörer för ett block av kod, allt som är inuti ett kodblock är innehåll som ALDRIG ska röras.
CODE_FENCE = re.compile(r"^\s*(```|~~~)")


# HTML-taggar som är kända. Tar ej bort allt mellan '< och >' då det hade raderat placeholders som placerats där med flit.
KNOWN_HTML_TAGS = (
    "a|img|br|td|tr|th|table|tbody|thead|details|summary|b|i|u|s|em|strong"
    "|li|ul|ol|p|div|span|h[1-6]|center|sup|sub|hr|code|pre|font|blockquote"
    "|figure|figcaption|iframe|video|source"
)

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG = re.compile(rf"</?\s*(?:{KNOWN_HTML_TAGS})\b[^>]*>", re.IGNORECASE)
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
SOUND_MARKER = re.compile(r"\[(?:Music|Applause|Laughter|Musik)\]", re.IGNORECASE)
REPEATED_SPACES = re.compile(r"[ \t]{2,}")
EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


# ====== 1: Regler för text som INTE är KOD ======
# Priv funktion, FAAFO
def _clean_prose(text: str) -> str:
    """
    Applies the v0 cleaning(transform) rules to text outside of known code blocks, in a fixed order.
    The order here matters, each step assumes the previous one is done.
    """
    # 1) Kommentarer FÖRE taggar. En kommentar KAN innehålla taggar.
    text = HTML_COMMENT.sub("", text)

    # 2) Taggarna <img> försvinner HELT och alt-texten med den.
    # Mätning visar att den ofta är felkopierad mellan lectures
    text = HTML_TAG.sub("", text)

    # 3) Entiteter EFTER taggarna.
    # &lt;div&gt; är text OM html, ska bli <div> som text och INTE tas bort som en tagg.
    text = html.unescape(text).replace("\xa0", " ")

    # 4) Bilder FÖRE länkar, ![alt](url) innehåller en [alt](url).
    # Bilder i markdowns alt-text är specifik för korpusen och står kvar.
    text = MARKDOWN_IMAGE.sub(r"\1", text)
    text = MARKDOWN_LINK.sub(r"\1", text)

    # 5) Audiomarkers [music] i transkripten ska bort.
    text = SOUND_MARKER.sub("", text)

    # 6) WHITESPACE trimmas bort och städas sist EFTER regel 1-5 gått igenom för att
    # rensa upp alla spår efter dom.
    lines = [REPEATED_SPACES.sub(" ", line).rstrip() for line in text.split("\n")]
    return EXTRA_BLANK_LINES.sub("\n\n", "\n".join(lines))


# ====== 2: Sektionernas text, kodblocken förblir ORÖRDA ======
# Funktion för cleaning
def clean_text(text: str) -> str:
    """
    Cleans ONE sections text before chunking it up.

    Lines inside a code block pass through untouched by design, fence markers included.
    Everything between the code blocks is cleaned by _clean_prose() as one piece,
    so a rule can span across several lines, like a multi-line HTML comment.

    An unclosed code block treats the rest of the text as code. This is
    the same rule build_sections_from_markdown() follows.
    """
    output: list[str] = []
    prose: list[str] = []
    in_code_fence = False

    def flush_prose() -> None:
        # Rensar texten som samlats sedan förra kodblocket, i ETT anrop.
        if prose:
            output.append(_clean_prose("\n".join(prose)))
            prose.clear()

    for line in text.split("\n"):
        if CODE_FENCE.match(line):
            # Ett kodblock börjar, rensa texten före det INNAN en marker läggs till.
            if not in_code_fence:
                flush_prose()
            in_code_fence = not in_code_fence
            output.append(line)
            continue

        if in_code_fence:
            output.append(line)
        else:
            prose.append(line)

    flush_prose()

    return "\n".join(output).strip()
