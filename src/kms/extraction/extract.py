# extract.py - Script för att orkestrera chunking och pdf_extractor scripts.
# Kod: Engelska
# Kommentarer: Svenska
#
# Scriptet vet endast VAD som ska hända med dokument och i vilken ordning
# Scriptet har ingen aning om HUR stegen utförs, det ligger i ovannämnda script + hashing.py.
# Exakt samma uppdelning av arbete som ingest.py redan använder sig utav
#
# Hämta det som har status PENDING ur Postgres, läs källfilen från disk och kontrollera den mot file_hash,
# konvertera till text, chunka upp filen, skriv chunk rader och uppdatera status i Postgres.

import re
import enum
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, selectinload

from kms.config import settings
from kms.db.models import Chunk, Document, DocumentStatus, FailureReason
from kms.extraction.chunker import MIN_CHUNK_SIZE, Section, chunk_document
from kms.extraction.pdf_extractor import PdfExtractionError, extract_pages
from kms.hashing import compute_file_hash

# Regex constants
MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
CODE_FENCE = re.compile(r"^\s*(```|~~~)")
TRANSCRIPT_TIMESTAMP = re.compile(r"^\*\*\[((?:\d{1,2}:)?\d{2}:\d{2})\]\*\*\s*(.*)$")
TRANSCRIPT_FRONT_MATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.S)
# Projektets namespace för vector_id.
# Genererats och genereras EN gång med uuid.uuid4() och ändras ALDRIG.
# Varje vector_id byggs på den här. Bor i KODEN och inte i .env
KMS_NAMESPACE = uuid.UUID("16acb480-21a4-4d26-8490-cfaa394ffa7b")


# --- 1: Extraherings outcome ---
# Vad händer med -ett- dokument under en körning
class ExtractionOutcome(str, enum.Enum):
    """
    Result of processing ONE document in ONE run.

    Not the same thing as DocumentStatus by design.
    SKIPPED is not a state a document can be in, a skipped document
    is still pending and unprocessed.

    Skipped only describes the previous/current RUN, not the DOCUMENT ITSELF.
    """

    EXTRACTED = "extracted"
    FAILED = "failed"
    SKIPPED = "skipped"


# --- 2: Section byggande, en per filtyp ---
def build_sections_from_pdfs(local_path: Path) -> list[Section]:
    """
    Turns a PDF into chunkable units that chunk_document()-function expects.

    Only thing carried over from PDF-structure is the page number.
    Its course, filename and source_type are already columns on the Document row,
    all are reachable through their document_id.
    """
    pages = extract_pages(local_path)
    return [
        Section(text=page.text, source_location={"page": page.page_number})
        for page in pages
    ]


# --- 3: Funktion för att göra sections av mina .md filer ---
def build_sections_from_markdown(local_path: Path) -> list[Section]:
    """
    Turns a markdown file into chunkable units, one heading per block.

    The heading line stays INSIDE the section text on purpose, it is the most
    descriptive sentence in the block and what makes the chunk findable later.

    Text before the first heading becomes its own section with heading=None.
    A README opening with three paragraphs before its first heading must not lose them.

    Raises nothing. extract_one_document() only catches PdfExtractionError around
    this call, so an exception here would end the ENTIRE run instead of failing
    one single document.
    """
    lines = local_path.read_text(encoding="utf-8", errors="replace").splitlines()

    sections: list[Section] = []
    buffer: list[str] = []
    heading: str | None = None
    start_line = 1

    def close_section(end_line: int) -> None:
        if not buffer:
            return
        sections.append(
            Section(
                text="\n".join(buffer),
                source_location={
                    "heading": heading,
                    "line_start": start_line,
                    "line_end": end_line,
                },
            )
        )

    in_code_fence = False

    for line_number, line in enumerate(lines, start=1):
        # Markören vänder tillståndet och är alltid innehåll, aldrig en rubrik.
        if CODE_FENCE.match(line):
            in_code_fence = not in_code_fence
            buffer.append(line)
            continue

        # Inuti ett kodblock är "# something" en kommentar i kod, inte ett avsnitt.
        if in_code_fence:
            buffer.append(line)
            continue

        match = MARKDOWN_HEADING.match(line)
        if match:
            # Rubriken stänger föregående sektion på raden FÖRE sig själv
            close_section(line_number - 1)
            heading = match.group(2).strip()
            buffer = [line]
            start_line = line_number
        else:
            buffer.append(line)

    close_section(len(lines))

    return sections


# --- 4: Funktion för att bygga sektioner ifrån YT transcripts ---
def build_sections_from_transcripts(local_path: Path) -> list[Section]:
    """
    Turns a YouTube transcript into cunks, one time-segment per block.

    The timestamp is kept OUT of the text and placed in source_location instead.
    That is the opposite choice from the markdown builder, and done deliberately.
    A heading is a descriptive sentence worth embedding, a timestamp is a coordinate.

    Raises nothing. Same contract as build_sections_from_markdown().
    """
    raw = local_path.read_text(encoding="utf-8", errors="replace")
    body = TRANSCRIPT_FRONT_MATTER.sub("", raw)

    sections: list[Section] = []
    timestamp: str | None = None
    buffer: list[str] = []

    def close_section() -> None:
        text = "\n".join(buffer).strip()
        if not text:
            return
        sections.append(Section(text=text, source_location={"timestamp": timestamp}))

    for line in body.splitlines():
        match = TRANSCRIPT_TIMESTAMP.match(line)
        if match:
            # Stämpeln stänger föregående block och öppnar nästa i samma steg.
            close_section()
            timestamp = match.group(1)
            buffer = [match.group(2)]
        elif timestamp is not None:
            # Rader före första stämpeln är rubriken '# titel', dom hör inte till något block.
            buffer.append(line)

    close_section()

    return sections


# Registret över filtyper systemet kan hantera.
# nyckel = Document.source_type, värde = funktionen som kan just den filtypen.
#
# Att lägga till markdown eller transkript senare är EN ny funktion och EN rad här.
SECTION_BUILDERS: dict[str, Callable[[Path], list[Section]]] = {
    "pdf": build_sections_from_pdfs,
    "markdown": build_sections_from_markdown,
    "transcript": build_sections_from_transcripts,
}


# --- 5: Helper funktion för dokument som misslyckas ---
# privat funktion FAAFO
def _mark_failed(
    session: Session,
    document: Document,
    reason: FailureReason,
    message: str,
) -> ExtractionOutcome:
    """
    Marks a document as unusable, and documents why - twice, on purpose.

    Reason is machine readable and is what a targeted backfill queries on.

    Commit here instead of later in the run.
    A later commit during run leads to a later crash and information
    cannot erase what was already learned about earlier documents.

    error_message is a note to a human, not a log line,
    capped and truncated to 1000 chars.
    """
    document.status = DocumentStatus.FAILED
    document.failure_reason = reason
    document.error_message = message[:1000]
    session.commit()
    print(
        f"[FAILED:{reason.name}] document {document.id} ({document.filename}): {message}"
    )
    return ExtractionOutcome.FAILED


# --- 6: Funktion för vector_id och deterministiskt ID per chunk ---
def make_vector_id(file_hash: str, chunk_index: int) -> uuid.UUID:
    """
    Deterministic ID for ONE chunk:
    Same content + same position -> same id, every run, on every machine.

    Written to chunks.vector_id here, used as the record id in Chroma.
    file_hash and not the chunk text: Transcript copies with identical text
    must not collaps into ONE id.
    """
    return uuid.uuid5(KMS_NAMESPACE, f"{file_hash}:{chunk_index}")


# --- 7: Funktion för sidmått (Endast PDF'er) ---
def measure_pages(sections: list[Section]) -> tuple[int, int, int]:
    """
    Page metrics for ONE PDF: (page_count, empty_page_count, short_page_count).

    Only VALID PDFs - build_sections_from_pdfs give exactly one section per page.
    Same strip() and MIN_CHUNK_SIZE as the chunker so "short" means exactly:
    had text, but the chunker threw it away.
    """
    lengths = [len(section.text.strip()) for section in sections]
    empty = sum(1 for n in lengths if n == 0)
    short = sum(1 for n in lengths if 0 < n < MIN_CHUNK_SIZE)
    return len(lengths), empty, short


# --- 8: Funktion för att extrahera ETT dokument ---
def extract_one_document(
    document: Document,
    repos_root: Path,
    session: Session,
) -> ExtractionOutcome:
    """
    Only ONE document is processed.

    document.id already exists - the row came from a SELECT and not from session.add().
    document.source_files is already loaded by run_extraction() with selectinload,
    reading it here sends no query.

    The source file is read straight from disk, the copy registered FIRST (lowest source_files.id),
    and checked against documents.file_hash BEFORE anything is extracted.
    Missing file: FAILED (SOURCE_MISSING). Other read error: SKIPPED.
    Different hash: RuntimeError, the whole run stops loud.
    """
    # KeyError här betyder att frågan längst ner hämtade en filtyp som inte finns i registret
    # KeyError innebär alltså ett fel i koden här och inte i ett dokument.
    builder = SECTION_BUILDERS[document.source_type]

    # --- Exemplaret: det som registrerades FÖRST, lägst source_files.id ---
    # selectinload garanterar INGEN ordning på listan, därför min() på id och inte [0].
    # Ingestion skriver alltid dokumentet och dess första exemplar i SAMMA commit.
    # Ett dokument utan exemplar ger ValueError här, ett fel i datan och inte i ett dokument.
    first_copy = min(document.source_files, key=lambda source_file: source_file.id)
    local_path = repos_root / first_copy.source_path

    # --- Kontrollen: filen på disk mot innehållets identitet, FÖRE all extraktion ---
    try:
        file_hash = compute_file_hash(local_path)
    except FileNotFoundError:
        # PERMANENT fel: filen finns inte där source_files pekar. Fakta om DOKUMENTET.
        # FileNotFoundError ärver OSError och måste därför fångas FÖRE OSError.
        return _mark_failed(
            session,
            document,
            FailureReason.SOURCE_MISSING,
            f"source file missing on disk: {first_copy.source_path}",
        )
    except OSError as e:
        # TRANSIENT fel: filen finns men går inte att läsa just nu (behörighet, låst fil).
        # Fakta om MILJÖN. FAILED hade raderat PENDING, det enda som gör en omkörning möjlig.
        print(f"[SKIPPING] could not read {first_copy.source_path}: {e}")
        return ExtractionOutcome.SKIPPED

    if file_hash != document.file_hash:
        # Samma regel som ingestionen när en känd sökväg fått nytt innehåll: stoppa HÖGT.
        # Annars blir det chunkar av NY text under GAMMAL file_hash, och avstämningen går ändå grön.
        # Dokument som redan är klara står kvar som EXTRACTED, resten som PENDING.
        raise RuntimeError(
            f"'{first_copy.source_path}' has changed on disk since ingestion, "
            f"its hash no longer matches documents.file_hash. "
            f"Run tools/rebuild.py - only a full rebuild updates the index!"
        )

    # --- Gör om filen till TEXT ---
    try:
        sections = builder(local_path)
    except PdfExtractionError as e:
        # Filen kan inte läsas. Fakta om DOKUMENTET (se extraction_logic_flowchart_mvp_v2)
        return _mark_failed(
            session,
            document,
            FailureReason.UNREADABLE_SOURCE,
            f"extraction failed: {e}",
        )

    # --- Sidmått: Bara PDF, ska mötas FÖRE noll-chunk-koll ---
    # PDF som blir FAILED (bilder) ska få sina sidor räknade, _mark_failed committar
    # den tillsammans med status
    if document.source_type == "pdf":
        page_count, empty_pages, short_pages = measure_pages(sections)
        document.page_count = page_count
        document.empty_page_count = empty_pages
        document.short_page_count = short_pages

    chunks = chunk_document(sections)

    # --- Mätpunkt: två skilda verkligheter bakom samma tomma lista ---
    # Noll chunks kan betyda två helt olika saker, och dom blir lösta av olika arbeten:
    # NOLL tecken text -> innehållet ÄR bild och innebär att bara OCR hjälper mig,
    # text finns, men varje sektion är UNDER MIN_CHUNK_SIZE -> en tröskelfråga.
    # Skillnaden mäts här, en gång, istället för att gissa i efterhand.
    # Teckenantalet följer med i meddelandet så att marginalen syns som output.
    if not chunks:
        extracted_chars = sum(len(section.text.strip()) for section in sections)
        if extracted_chars == 0:
            return _mark_failed(
                session,
                document,
                FailureReason.NO_TEXT_EXTRACTED,
                "0 chunks: no text extracted, content is most LIKELY image-based",
            )
        return _mark_failed(
            session,
            document,
            FailureReason.TEXT_BELOW_THRESHOLD,
            f"0 chunks: {extracted_chars} chars extracted, "
            f"all sections below MIN_CHUNK_SIZE",
        )

    # --- Sidoeffekt: skriv till Postgres med EN transaktion ---
    # Rensar först eventuella chunk-rader från tidigare försök som blivit avbrutna.
    # Körningen ska gå att göra om UTAN att lämna dubbletter efter sig.
    # (Idempotens)
    session.execute(delete(Chunk).where(Chunk.document_id == document.id))

    # source_location skickas som en vanlig dict(hash table) här.
    # Postgres columnen är JSONB(binary) och tar emot dicten direkt.
    session.add_all(
        [
            Chunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                source_location=chunk.source_location,
                char_count=chunk.char_count,
                vector_id=make_vector_id(document.file_hash, chunk.chunk_index),
            )
            for chunk in chunks
        ]
    )
    document.status = DocumentStatus.EXTRACTED
    document.error_message = None
    document.failure_reason = None
    session.commit()

    return ExtractionOutcome.EXTRACTED


# --- 9: Funktion som fungerar som min ORKESTRERING ---
def run_extraction() -> None:
    """
    Sets up the connection, ITERATES over every PENDING document then prints a summary in terminal.

    Same shape as run_ingestion() by design: a function that only wires things
    up and iterates is the same thing as a Airflow task,
    this way in MVP v5 there will be no need rewrite this file.
    """
    engine = create_engine(settings.database_url)

    counts = {outcome: 0 for outcome in ExtractionOutcome}

    # expire_on_commit=False: dokumenten och exemplaren hämtas EN gång och används efter varje commit.
    # Med standardvärdet True blir alla laddade objekt inaktuella vid varje commit,
    # och varje kvarvarande dokument hämtas om med två nya frågor (N+1 i smyg).
    # Säkert här: inget annat skriver i documents medan extraktionen kör.
    with Session(engine, expire_on_commit=False) as session:
        # Filter på source_type läses direkt UR registret.
        # Ska jag lägga till andra filtyper gör jag det i
        # build_sections_from_pdfs()-FUNKTIONEN och då expanderar den här frågan automatiskt.
        # Filtyper som inte ännu har en byggare hämtas aldrig, dom hoppas alltså inte över i tystnad
        # dom ligger endast kvar som PENDING tills modulen finns/är byggd.
        # selectinload: exemplaren för ALLA dokument hämtas i ett fast antal frågor,
        # WHERE document_id IN (...), 500 dokument per fråga. Inte en fråga per dokument (N+1).
        # Samma tanke som minnet i run_ingestion(): hämta en gång, slå upp i loopen.
        statement = (
            select(Document)
            .options(selectinload(Document.source_files))
            .where(Document.status == DocumentStatus.PENDING)
            .where(Document.source_type.in_(SECTION_BUILDERS.keys()))
            .order_by(Document.id)
        )

        # .all() istället för att streama: raderna innehåller lite metadata,
        # och commitas inne i loopen.
        # Att iterera över en öppen databas-markör samtidigt som man committar är en fälla att undvika.
        # Därför ska allting hämtas klart först.
        documents = session.execute(statement).scalars().all()
        print(
            f"Found {len(documents)} PENDING documents "
            f"of type: {sorted(SECTION_BUILDERS)}"
        )

        for document in documents:
            outcome = extract_one_document(
                document, settings.COURSE_REPOS_ROOT, session
            )
            counts[outcome] += 1

    print(
        f"DONE - {counts[ExtractionOutcome.EXTRACTED]} EXTRACTED, "
        f"{counts[ExtractionOutcome.FAILED]} FAILED, "
        f"{counts[ExtractionOutcome.SKIPPED]} SKIPPED."
    )


# === ENTRYPOINT ===
if __name__ == "__main__":
    run_extraction()
