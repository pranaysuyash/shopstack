from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Generator

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.schemas.models import InventoryLot, PriceObservation
from shopstack.tools.registry import ToolRegistry


SEED_ITEMS = [
    ("rice", "Basmati Rice", "grains", 5.0, "kg", "pantry", 450.0),
    ("wheat_flour", "Aashirvaad Atta", "grains", 10.0, "kg", "pantry", 380.0),
    ("toor_dal", "Toor Dal", "pulses", 2.0, "kg", "pantry", 180.0),
    ("moong_dal", "Moong Dal", "pulses", 1.0, "kg", "pantry", 150.0),
    ("chana_dal", "Chana Dal", "pulses", 1.5, "kg", "pantry", 120.0),
    ("mustard_oil", "Fortune Mustard Oil", "oils", 1.0, "L", "pantry", 185.0),
    ("sunflower_oil", "Sunflower Oil", "oils", 1.0, "L", "pantry", 140.0),
    ("salt", "Tata Salt", "spices", 1.0, "kg", "spice_box", 25.0),
    ("turmeric", "Turmeric Powder", "spices", 0.2, "kg", "spice_box", 80.0),
    ("red_chilli", "Red Chilli Powder", "spices", 0.2, "kg", "spice_box", 90.0),
    ("cumin", "Jeera", "spices", 0.1, "kg", "spice_box", 120.0),
    ("coriander_powder", "Dhania Powder", "spices", 0.2, "kg", "spice_box", 60.0),
    ("garam_masala", "MDH Garam Masala", "spices", 0.1, "kg", "spice_box", 150.0),
    ("milk", "Amul Taaza", "dairy", 2.0, "L", "fridge", 64.0),
    ("curd", "Amul Curd", "dairy", 0.5, "kg", "fridge", 40.0),
    ("paneer", "Amul Paneer", "dairy", 0.2, "kg", "fridge", 90.0),
    ("butter", "Amul Butter", "dairy", 0.1, "kg", "fridge", 56.0),
    ("onion", "Onion", "vegetables", 2.0, "kg", "fridge_drawer", 40.0),
    ("tomato", "Tomato", "vegetables", 1.0, "kg", "fridge_drawer", 30.0),
    ("potato", "Potato", "vegetables", 3.0, "kg", "fridge_drawer", 45.0),
    ("green_chilli", "Green Chilli", "vegetables", 0.1, "kg", "fridge_drawer", 15.0),
    ("ginger", "Ginger", "vegetables", 0.2, "kg", "fridge_drawer", 30.0),
    ("garlic", "Garlic", "vegetables", 0.2, "kg", "fridge_drawer", 40.0),
    ("capsicum", "Capsicum", "vegetables", 0.5, "kg", "fridge_drawer", 50.0),
    ("coriander", "Coriander Leaves", "vegetables", 0.1, "kg", "fridge_drawer", 10.0),
    ("spinach", "Palak", "vegetables", 0.5, "kg", "fridge_drawer", 20.0),
    ("banana", "Banana", "fruits", 1.0, "dozen", "kitchen", 50.0),
    ("apple", "Apple", "fruits", 1.0, "kg", "kitchen", 180.0),
    ("lemon", "Lemon", "fruits", 0.5, "kg", "kitchen", 60.0),
    ("sugar", "Sugar", "staples", 2.0, "kg", "pantry", 90.0),
    ("tea", "Tata Tea Gold", "beverages", 0.5, "kg", "pantry", 220.0),
    ("coffee", "Nescafe Classic", "beverages", 0.2, "kg", "pantry", 200.0),
    ("biscuit", "Parle-G", "snacks", 1.0, "kg", "pantry", 80.0),
    ("bread", "Britannia Bread", "bakery", 1.0, "unit", "pantry", 40.0),
    ("egg", "Eggs", "protein", 1.0, "dozen", "fridge", 80.0),
    ("chicken", "Chicken Breast", "protein", 1.0, "kg", "freezer", 250.0),
    ("soap", "Dettol Soap", "hygiene", 3.0, "unit", "bathroom_cabinet", 45.0),
    ("shampoo", "Head & Shoulders", "hygiene", 1.0, "unit", "bathroom_cabinet", 200.0),
    ("toothpaste", "Colgate", "hygiene", 1.0, "unit", "bathroom_cabinet", 95.0),
    ("detergent", "Surf Excel", "cleaning", 2.0, "kg", "cleaning_shelf", 280.0),
    ("dish_soap", "Vim Liquid", "cleaning", 1.0, "unit", "cleaning_shelf", 110.0),
    ("floor_cleaner", "Lizol", "cleaning", 1.0, "L", "cleaning_shelf", 150.0),
    ("mosquito_repellent", "Good Knight", "household", 1.0, "unit", "bedroom", 85.0),
    ("paratha", "Frozen Paratha", "frozen", 1.0, "unit", "freezer", 120.0),
    ("peas", "Frozen Peas", "frozen", 0.5, "kg", "freezer", 70.0),
    ("cornflour", "Cornflour", "thickener", 0.5, "kg", "pantry", 50.0),
    ("baking_soda", "Baking Soda", "baking", 0.1, "kg", "pantry", 25.0),
    ("vinegar", "Synthetic Vinegar", "condiment", 1.0, "L", "pantry", 35.0),
    ("soy_sauce", "Ching's Soy Sauce", "condiment", 0.2, "L", "pantry", 55.0),
    ("honey", "Dabur Honey", "condiment", 0.5, "kg", "pantry", 200.0),
]

SEED_STORES = [
    ("store_dmart", "DMart", "Koramangala", "supermarket"),
    ("store_bigbazaar", "Big Bazaar", "HSR Layout", "supermarket"),
    ("store_sharma", "Sharma Kirana", "12th Main", "kirana"),
    ("store_more", "More Supermarket", "Indiranagar", "supermarket"),
    ("store_local", "Local Vendor", "Roadside", "pushcart"),
]


SAMPLE_RECEIPT_TEXT = """Sharma General Store
Date: 08/06/2026
Bill No: 1247

ONION 2 KG 64.00
TOMATO 1 KG 35.00
POTATO 3 KG 75.00
GREEN CHILLI 100 G 12.00
GINGER 200 GM 28.00
CORIANDER LEAVES 1 BUNCH 10.00
AMUL TAAZA MILK 2 L 128.00
BREAD 1 PCS 42.00
EGG 12 PCS 85.00
SURF EXCEL 1 KG 145.00
VIM LIQUID 1 PCS 110.00
TATA SALT 1 KG 25.00
TURMERIC POWDER 200 GM 78.00

Total: Rs. 837.00
GST: 0.00
Cash Paid: 900.00
Change: 63.00
"""


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        _env_file=None,
        db_path=":memory:",
        off_the_grid=True,
        local_auto_download=False,
    )


@pytest.fixture(scope="session")
def db(settings: Settings) -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)
    yield database
    Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def providers(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(settings)


@pytest.fixture(scope="session")
def tool_registry(db: Database) -> ToolRegistry:
    return ToolRegistry(db)


@pytest.fixture(scope="session")
def bench_db() -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)

    today = date.today()
    for i, (cname, dname, cat, qty, unit, loc, price) in enumerate(SEED_ITEMS):
        lot = InventoryLot(
            canonical_name=cname,
            display_name=dname,
            category=cat,
            quantity=qty,
            unit=unit,
            storage_location_id=loc,
            purchase_date=today - timedelta(days=i % 14),
            price_paid=price,
        )
        database.add_inventory_lot(lot)

    stores_map: dict[str, str] = {}
    for sid, sname, sloc, stype in SEED_STORES:
        from shopstack.schemas.models import Store
        store = Store(store_id=sid, name=sname, location=sloc, store_type=stype)
        database.add_store(store)
        stores_map[sname] = sid

    store_names = list(stores_map.keys())
    for i in range(100):
        item = SEED_ITEMS[i % len(SEED_ITEMS)]
        cname = item[0]
        base_price = item[6]
        store_name = store_names[i % len(store_names)]
        variation = base_price * (1 + (i % 7 - 3) * 0.05)
        obs = PriceObservation(
            canonical_name=cname,
            quantity=item[3],
            unit=item[4],
            price=round(variation, 2),
            store_name=store_name,
            store_id=stores_map[store_name],
            observation_date=today - timedelta(days=i),
        )
        database.record_price(obs)

    for i in range(20):
        item = SEED_ITEMS[i % len(SEED_ITEMS)]
        from shopstack.schemas.models import PurchaseEvent
        event = PurchaseEvent(
            canonical_name=item[0],
            quantity=item[3],
            unit=item[4],
            total_price=item[6],
            source_type="manual",
            store_name=store_names[i % len(store_names)],
        )
        database.add_purchase_event(event)

    database.set_config_value("field_notes_markdown", "# Field Notes\n\nWeekly grocery planning notes.\n")

    from shopstack.schemas.models import ShoppingListItem
    sl = database.create_shopping_list(name="Weekly Groceries", goal="Restock essentials")
    for cname, qty, unit, priority in [
        ("milk", 2.0, "L", "must_buy"),
        ("bread", 1.0, "unit", "must_buy"),
        ("tomato", 1.0, "kg", "optional"),
        ("onion", 2.0, "kg", "must_buy"),
        ("egg", 1.0, "dozen", "must_buy"),
    ]:
        sli = ShoppingListItem(
            canonical_name=cname,
            requested_quantity=qty,
            unit=unit,
            priority=priority,
            reason="Benchmark seed",
        )
        database.add_list_item(sl.list_id, sli)

    yield database
    Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def bench_tools(bench_db: Database) -> ToolRegistry:
    return ToolRegistry(bench_db)


@pytest.fixture(scope="session")
def sample_receipt_text() -> str:
    return SAMPLE_RECEIPT_TEXT


@pytest.fixture()
def fresh_db() -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)
    yield database
    Path(path).unlink(missing_ok=True)


# ── Real-model fixtures (skip in CI, requires cached model weights) ──


def _glm_ocr_cache_path() -> str | None:
    """Return the cached GLM-OCR model path if available, else None."""
    import importlib
    if importlib.util.find_spec("transformers") is None:
        return None
    try:
        from transformers.models.glm_ocr import GlmOcrForConditionalGeneration  # noqa: F401
    except ImportError:
        return None

    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    model_dir_name = "models--zai-org--GLM-OCR"
    model_dir = os.path.join(cache_dir, model_dir_name)
    snapshots_dir = os.path.join(model_dir, "snapshots")
    if not os.path.isdir(snapshots_dir):
        return None
    snapshots = os.listdir(snapshots_dir)
    if not snapshots:
        return None
    snapshot_path = os.path.join(snapshots_dir, snapshots[0])
    if os.path.isfile(os.path.join(snapshot_path, "model.safetensors")):
        return snapshot_path
    return None


def _create_hindi_receipt_image() -> str:
    """Generate a bilingual Hindi-English receipt image and return its path.

    Uses Devanagari MT font for Hindi-transliterated item names mixed with
    English (e.g. PYAAZ (Onion), TAMATAR (Tomato)). Tests multilingual OCR.
    """
    from PIL import Image, ImageDraw, ImageFont

    lines = [
        "  SHARMA KIRANA STORE  ",
        "  12th Main, Koramangala",
        "  Date: 15/06/2026",
        "========================================",
        "  VATRA (ITEM)     QTY      RUPIYAH",
        "----------------------------------------",
        "1. PYAAZ (Onion)         2 KG      40",
        "2. TAMATAR (Tomato)      1 KG      35",
        "3. AALOO (Potato)        2 KG      50",
        "4. DOODH (Milk)          1 L       64",
        "5. ANDAY (Eggs)          12 PC     85",
        "6. MAKKHAN (Butter)    500 G       60",
        "7. CHEENI (Sugar)        1 KG      45",
        "8. SARSON KA TEL         1 L      185",
        "9. AATA (Wheat Flour)    1 KG      42",
        "10. CHAWAL (Rice)        1 KG      75",
        "----------------------------------------",
        "  KUUL YOG (Total)             681",
        "  AADHAA KAR (GST)              0",
        "========================================",
        "  DHANYAVAAD! THANK YOU!",
    ]
    ground_truth = "\n".join(lines)

    padding = 14
    font_size = 14
    line_height = font_size + 6
    width = 420
    height = len(lines) * line_height + padding * 2

    img = Image.new("RGB", (width, height), (248, 244, 240))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/DevanagariMT.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()

    for i, line in enumerate(lines):
        y = padding + i * line_height
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(lower.startswith(k) for k in ["kuul", "aadhaa"]):
            tw = draw.textlength(stripped, font=font)
            draw.text((width - padding - tw, y), stripped, fill="black", font=font)
        else:
            draw.text((padding, y), stripped, fill="black", font=font)

    import tempfile
    fd, path = tempfile.mkstemp(suffix=".png", prefix="glm_ocr_hindi_")
    os.close(fd)
    img.save(path)

    # Save ground truth alongside the image
    gt_path = path.replace(".png", "_ground_truth.txt")
    with open(gt_path, "w", encoding="utf-8") as f:
        f.write(ground_truth)

    return path, gt_path


def _create_receipt_image() -> str:
    """Generate a test receipt image and return its path.

    Creates a thermal-printer style receipt with 13 line items,
    store name, date, and totals. Used by GLM-OCR benchmarks.
    """
    from PIL import Image, ImageDraw, ImageFont

    receipt_text = SAMPLE_RECEIPT_TEXT

    lines = receipt_text.split("\n")
    font_size = 15
    line_height = font_size + 7
    padding = 16
    width = 380
    height = len(lines) * line_height + padding * 2

    img = Image.new("RGB", (width, height), (248, 244, 240))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()

    right_align_keys = {"total", "subtotal", "gst", "cgst", "sgst", "cash", "change", "grand", "net"}
    for i, line in enumerate(lines):
        y = padding + i * line_height
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(lower.startswith(k) for k in right_align_keys):
            tw = draw.textlength(stripped, font=font)
            draw.text((width - padding - tw, y), stripped, fill="black", font=font)
        else:
            draw.text((padding, y), stripped, fill="black", font=font)

    import tempfile
    fd, path = tempfile.mkstemp(suffix=".png", prefix="glm_ocr_bench_")
    os.close(fd)
    img.save(path)
    return path


def _mlx_model_cache_path() -> str | None:
    """Return the cached MLX model path if available, else None."""
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    model_dir_name = "models--mlx-community--Llama-3.2-3B-Instruct-4bit"
    model_dir = os.path.join(cache_dir, model_dir_name)
    snapshots_dir = os.path.join(model_dir, "snapshots")
    if not os.path.isdir(snapshots_dir):
        return None
    snapshots = os.listdir(snapshots_dir)
    if not snapshots:
        return None
    # Use the first (and usually only) snapshot
    snapshot_path = os.path.join(snapshots_dir, snapshots[0])
    if os.path.isfile(os.path.join(snapshot_path, "model.safetensors")):
        return snapshot_path
    if os.path.isfile(os.path.join(snapshot_path, "model.safetensors.index.json")):
        return snapshot_path
    return None


@pytest.fixture(scope="session")
def glm_ocr_model() -> Generator[Any, None, None]:
    """Provide a GlmOCRProvider loaded with GLM-OCR via transformers.

    Skips the test if:
    - transformers with GlmOcrForConditionalGeneration is not installed
    - The GLM-OCR model is not cached in the HuggingFace hub cache

    Yields ``(provider, image_path, warm_elapsed)`` so benchmarks can
    measure cold-start load time separately from extraction latency.
    The test receipt image is created in a temp dir and cleaned up
    on teardown.
    """
    import importlib

    if importlib.util.find_spec("transformers") is None:
        pytest.skip("transformers not installed")
    if importlib.util.find_spec("PIL") is None:
        pytest.skip("Pillow not installed")

    cache_path = _glm_ocr_cache_path()
    if cache_path is None:
        pytest.skip(
            "GLM-OCR model not cached. Run: "
            "uv run python -c 'from transformers import AutoModel; "
            "AutoModel.from_pretrained(\"zai-org/GLM-OCR\", trust_remote_code=True)'"
        )

    from shopstack.providers.ocr_provider import GlmOCRProvider

    provider = GlmOCRProvider()

    # Warm: load the model into memory once
    warm_start = __import__("time").perf_counter()
    provider.load()
    warm_elapsed = __import__("time").perf_counter() - warm_start

    # Create test receipt image
    image_path = _create_receipt_image()

    yield provider, image_path, warm_elapsed

    # Teardown: drop references and clean up temp file
    provider._model = None
    provider._processor = None
    try:
        import os as _os
        _os.unlink(image_path)
    except Exception:
        pass


@pytest.fixture(scope="session")
def llama3b_model() -> Generator[Any, None, None]:
    """Provide a LocalProvider loaded with llama-3.2-3b (MLX).

    Skips the test if:
    - mlx_lm is not installed
    - The MLX model is not cached in the HuggingFace hub cache

    Loading is deferred to the first ``complete()`` call so that
    inference-only benchmarks can measure cold-start separately.
    """
    import importlib

    if importlib.util.find_spec("mlx_lm") is None:
        pytest.skip("mlx-lm not installed")

    cache_path = _mlx_model_cache_path()
    if cache_path is None:
        pytest.skip("MLX llama-3.2-3b model not cached (run: uv run python -c 'import mlx_lm; mlx_lm.load(\"mlx-community/Llama-3.2-3B-Instruct-4bit\")')")

    from shopstack.providers.local_provider import LocalProvider

    provider = LocalProvider(
        model_dir=os.path.dirname(cache_path),
        mlx_model=cache_path,
        allow_download=False,
        auto_unload=False,  # keep loaded across benchmark calls
    )

    # Warm: load the model into memory once
    warm_start = __import__("time").perf_counter()
    provider._ensure_model()
    warm_elapsed = __import__("time").perf_counter() - warm_start

    yield provider, warm_elapsed

    # Teardown: drop reference so the model can be garbage-collected
    provider._llm = None
    provider._tokenizer = None


def _generate_test_audio() -> str:
    """Generate a short WAV file with a 440Hz sine tone and return its path.

    Creates ~1 second of mono 16-bit PCM audio at 16kHz.
    Used by real STT provider benchmarks.
    """
    import math
    import struct
    import tempfile
    import wave

    sample_rate = 16000
    duration_s = 1.0
    num_samples = int(sample_rate * duration_s)

    fd, path = tempfile.mkstemp(suffix=".wav", prefix="stt_bench_")
    os.close(fd)

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            sample = int(math.sin(2.0 * math.pi * 440.0 * i / sample_rate) * 16000)
            wf.writeframes(struct.pack("<h", sample))
    return path


# ── Real STT provider fixture ──────────────────────────────────


@pytest.fixture(scope="session")
def real_stt_model() -> Generator[Any, None, None]:
    """Provide a real STT provider (tries LocalWhisperProvider first).

    Skips the test if no real STT backend is available.
    Yields ``(provider, audio_path)`` where ``audio_path`` is a generated
    sine-tone WAV file suitable for transcription benchmarks.
    """
    provider = None

    # Try LocalWhisperProvider (mlx-whisper or faster-whisper)
    try:
        from shopstack.providers.local_whisper_provider import LocalWhisperProvider
        p = LocalWhisperProvider()
        if p.available:
            provider = p
    except Exception:
        pass

    # Fallback: SenseVoiceSTTProvider
    if provider is None:
        try:
            from shopstack.providers.stt_provider import SenseVoiceSTTProvider
            p = SenseVoiceSTTProvider()
            if p.available:
                provider = p
        except Exception:
            pass

    if provider is None:
        pytest.skip("No real STT provider available (install mlx-whisper or funasr)")

    audio_path = _generate_test_audio()
    yield provider, audio_path

    try:
        os.unlink(audio_path)
    except Exception:
        pass


# ── Real TTS provider fixture ──────────────────────────────────


@pytest.fixture(scope="session")
def real_tts_model() -> Generator[Any, None, None]:
    """Provide a real TTS provider (KokoroTTSProvider with gTTS fallback).

    Skips the test if no real TTS backend is available.
    gTTS is tried as a fallback (requires no model weights).
    Yields ``provider`` for synthesis benchmarks.
    """
    provider = None

    try:
        from shopstack.providers.tts_provider import KokoroTTSProvider
        p = KokoroTTSProvider()
        if p.healthcheck():
            provider = p
    except Exception:
        pass

    if provider is None:
        pytest.skip("No real TTS provider available (install kokoro or gtts)")

    yield provider


# ── Real Vision provider fixture ───────────────────────────────


@pytest.fixture(scope="session")
def real_vision_model() -> Generator[Any, None, None]:
    """Provide a real Vision provider (MiniCPM-V via transformers).

    Skips the test if transformers/torch are not installed or the
    model weights are not cached locally.
    Yields ``(provider, image_path, tmpdir)`` for understanding benchmarks.
    """
    import importlib

    if importlib.util.find_spec("transformers") is None:
        pytest.skip("transformers not installed")

    try:
        from shopstack.providers.vision_provider import MiniCPMVProvider
        provider = MiniCPMVProvider()
        if not provider.available:
            pytest.skip("MiniCPM-V provider not available (missing deps)")
    except Exception as e:
        pytest.skip(f"MiniCPM-V provider init failed: {e}")

    from PIL import Image
    from pathlib import Path
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    img_path = tmp / "vision_bench.png"
    Image.new("RGB", (400, 300), color="white").save(img_path)

    yield provider, str(img_path), tmp

    for f in tmp.iterdir():
        f.unlink(missing_ok=True)
    tmp.rmdir()


# ── Real Planner provider fixture ──────────────────────────────


@pytest.fixture(scope="session")
def real_planner_model() -> Generator[Any, None, None]:
    """Provide a real Planner provider (LocalProvider via MLX).

    Skips the test if MLX or the cached model weights are not available.
    Uses the same cache check as the existing ``llama3b_model`` fixture.
    Yields ``(provider, warm_elapsed)`` for planning benchmarks.
    """
    import importlib

    if importlib.util.find_spec("mlx_lm") is None:
        pytest.skip("mlx-lm not installed")

    cache_path = _mlx_model_cache_path()
    if cache_path is None:
        pytest.skip("MLX model not cached (run: uv run python -c 'import mlx_lm; mlx_lm.load(\"mlx-community/Llama-3.2-3B-Instruct-4bit\")')")

    try:
        from shopstack.providers.local_provider import LocalProvider
        provider = LocalProvider(
            model_dir=os.path.dirname(cache_path),
            mlx_model=cache_path,
            allow_download=False,
            auto_unload=False,
        )
        warm_start = __import__("time").perf_counter()
        provider._ensure_model()
        warm_elapsed = __import__("time").perf_counter() - warm_start
    except Exception as e:
        pytest.skip(f"LocalProvider init failed: {e}")

    yield provider, warm_elapsed

    provider._llm = None
    provider._tokenizer = None


def _tesseract_check() -> bool:
    """Return True if Tesseract OCR CLI is available and working."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def tesseract_model() -> Generator[Any, None, None]:
    """Provide a TesseractOCRProvider for real-model benchmarks.

    Tesseract is a CLI tool (not a neural model), so there is no model
    loading step — it's always available if the CLI is installed.

    Skips the test if:
    - pytesseract is not installed
    - The tesseract CLI binary is not found

    Yields ``(provider, image_path)`` where ``image_path`` is a generated
    thermal-printer receipt image used for extraction benchmarks.
    The temp image is cleaned up on teardown.
    """
    import importlib

    if importlib.util.find_spec("pytesseract") is None:
        pytest.skip("pytesseract not installed")
    if not _tesseract_check():
        pytest.skip("Tesseract CLI not available (brew install tesseract)")

    from shopstack.providers.tesseract_provider import TesseractOCRProvider

    provider = TesseractOCRProvider(lang="eng", psm=6)

    assert provider.available, "TesseractOCRProvider should report available"

    # Create test receipt image (reuse the GLM-OCR image generator)
    image_path = _create_receipt_image()

    yield provider, image_path

    # Teardown: clean up temp file
    try:
        import os as _os
        _os.unlink(image_path)
    except Exception:
        pass
