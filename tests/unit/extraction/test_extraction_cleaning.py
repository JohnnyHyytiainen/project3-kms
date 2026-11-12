# test_extraction_cleaning.py - tester för rensningen av sektionernas text (cleaning.py).
# Botten av testpyramiden
# Kod: Engelska
# Kommentarer: Svenska
# ====================
# Testerna är delade i 3 delar.
#
# Del 1: Det som ska bort (städas/tvättas/rensas)
# A1: Ett riktigt fall ur korpusen, silver-README'n, ska endast bli rubriken och meningen.
# B1: <img> ska försvinna helt, alt-texten ska följa med.
# C1: En HTML-kommentar över flera rader ska försvinna.
# D1: Ljudmarkörerna([music]) i transkripten ska försvinna. Dessa skapades automatiskt vid scraping
# E1: Luckorna efter borttagna taggar blir högst en tomrad, dubbla mellanslag blir ett
#
# Del 2: Det som ska stå kvar i filerna
# A2: Kodblock med språk efter markören är orörda, även med HTML-kod inuti
# B2: Ett kodblock som aldrig stängs: resten av texten är kod
# C2: Platshållare så som <branch_name> eller <your_password> är inte HTML och ska därför stå kvar
# D2: Länkens text står kvar, adressen försvinner
#
# Del 3: Ordningen mellan reglerna
# A3: Entiteter avkodas EFTER taggarna, &lt;div&gt; blir texten <div>
# B3: Bilder före länkar, ![alt](url) blir alt och inte !alt
#

from kms.extraction.cleaning import clean_text


# ===== Del 1: Det som ska tas bort(standardiseras) =====
# =======================================================
# A1
def test_silver_readme_section_keeps_heading_and_sentence():
    """
    Test A1 - The first section of cloud_databricks_azure_course/06_silver_layer/README.md,
    exactly as build_sections_from_markdown() hands it over today.
    """
    raw = (
        "# Silver layer\n"
        "\n"
        "In the silver layer we build an One Big Table (OBT) and clean the data.\n"
        "\n"
        '<a href="https://youtu.be/WtPp32w-wTQ" target="_blank">\n'
        '  <img src="https://github.com/kokchun/assets/blob/main/databricks/'
        'silver_layer.png?raw=true" alt="silver layer coding" width="600">\n'
        "</a>\n"
    )
    # Taggarna ska bli tomma rader, whitespace-regeln slår ihop dom och strip() tar hand om leading+trailing whitespace.
    assert clean_text(raw) == (
        "# Silver layer\n"
        "\n"
        "In the silver layer we build an One Big Table (OBT) and clean the data."
    )


# B1
def test_img_tag_removed_together_with_its_alt_text():
    """
    Test B1 - The alt text is often copy-pasted between lessons, it goes with the tag.
    """
    raw = (
        "Text before.\n"
        '<img src="x.png" alt="pydantic for data validation" width="600">\n'
        "Text after."
    )
    result = clean_text(raw)
    assert "pydantic" not in result
    assert result == "Text before.\n\nText after."


# C1
def test_multiline_html_comment_removed():
    """
    Test C1 - A comment can span lines, the rules see all prose between code blocks at once.
    """
    raw = "Keep this.\n<!--\nvariety of big data\n-->\nKeep this too."
    assert clean_text(raw) == "Keep this.\n\nKeep this too."


# D1
def test_sound_markers_removed():
    """
    Test D1 - [Music] and [Applause] are generated sound markers in transcripts and not speech.
    """
    raw = "[Music] so welcome to this video [Applause] about dbt"
    assert clean_text(raw) == "so welcome to this video about dbt"


# E1
def test_gaps_left_by_removed_tags_collapse():
    """
    Test E1 - Removed tags leave empty lines and spaces behind, whitespace runs last.
    """
    raw = "Before.\n<details>\n<summary>\n</summary>\n</details>\nAfter  two   spaces. Or  more  "
    assert clean_text(raw) == "Before.\n\nAfter two spaces. Or more"


# ===== Del 2: Det som ska stå kvar och behållas =====
# ====================================================
# A2
def test_code_blocks_with_language_are_untouched():
    """
    Test A2 - A language after the fence marker is still a code block, the HTML inside stays.
    """
    raw = (
        "```py\n"
        "uv pip install pandas ipykernel # more packages ...\n"
        "```\n"
        "\n"
        "Remember that you need to activate the environment first\n"
        "\n"
        "```html\n"
        '<img src="x.png" alt="example">\n'
        "```"
    )
    assert clean_text(raw) == raw


# B2
def test_unclosed_code_block_treats_rest_as_code():
    """
    Test B2 - Same rule as build_sections_from_markdown(), an open fence that never closes.
    """
    raw = "Intro text.\n```sql\nSELECT '<b>' AS tag;"
    assert clean_text(raw) == raw


# C2
def test_placeholders_are_not_html():
    """
    Test C2 - <branch_name> starts with b, the word boundary keeps it from matching <b>.
    """
    raw = "Run git checkout <branch_name> as <your_user>."
    raw_pass = "Enter your <super_secret_password> in your env file."
    assert clean_text(raw) == raw
    assert clean_text(raw_pass) == raw_pass


# D2
def test_link_keeps_text_and_drops_url():
    """
    Test D2 - The link text is content and the address is not.
    """
    raw = "Read the [pydantic docs](https://docs.pydantic.dev/latest/) first."
    assert clean_text(raw) == "Read the pydantic docs first."


# ===== Del 3: Ordningen mellan reglerna =====
# ============================================
# A3
def test_entities_decoded_after_tags():
    """
    Test A3 - &lt;div&gt; is text ABOUT html and must survive as <div>.
    """
    raw = "Use &lt;div&gt; for blocks&nbsp;here."
    assert clean_text(raw) == "Use <div> for blocks here."


# B3
def test_markdown_image_keeps_alt_without_exclamation_mark():
    """
    Test B3 - An image contains a link, so images are handled first.
    """
    raw = "![hierarchy of snowflake securable objects](assets/hierarchy.png)"
    assert clean_text(raw) == "hierarchy of snowflake securable objects"
