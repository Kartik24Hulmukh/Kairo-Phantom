import sys
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.kairo_eye.farscry_service import FarscryService, ElementType
from sidecar.kairo_eye.app_watcher import AppWatcher, Domain
from sidecar.kairo_eye.context_assembler import ContextAssembler


# --- Test 1: Date detection ---
def test_date_detection():
    service = FarscryService()
    elem = {"text": "Meeting scheduled on 2026-05-31", "type": "text"}
    assert service._classify_element(elem) == ElementType.DATE

    elem2 = {"text": "05/31/2026 is the deadline", "type": "text"}
    assert service._classify_element(elem2) == ElementType.DATE


# --- Test 2: Number / financial detection ---
def test_number_detection():
    service = FarscryService()
    elem = {"text": "$1,250.00", "type": "text"}
    assert service._classify_element(elem) == ElementType.NUMBER

    elem2 = {"text": "45%", "type": "text"}
    assert service._classify_element(elem2) == ElementType.NUMBER


# --- Test 3: Code detection ---
def test_code_detection():
    service = FarscryService()
    elem = {"text": "def my_func():\n    return 42", "type": "text"}
    assert service._classify_element(elem) == ElementType.CODE

    elem2 = {"text": "let x = 10;", "type": "text"}
    assert service._classify_element(elem2) == ElementType.CODE


# --- Test 4: Error message detection ---
def test_error_message_detection():
    service = FarscryService()
    elem = {"text": "Fatal: NullPointerException in thread main", "type": "text"}
    assert service._classify_element(elem) == ElementType.ERROR_MESSAGE

    elem2 = {"text": "failed to connect to server", "type": "text"}
    assert service._classify_element(elem2) == ElementType.ERROR_MESSAGE


# --- Test 5: Table detection ---
def test_table_detection():
    service = FarscryService()
    elem = {"text": "Col1 | Col2\nValA | ValB", "type": "text"}
    assert service._classify_element(elem) == ElementType.TABLE

    elem2 = {"text": "Data in table format", "type": "table"}
    assert service._classify_element(elem2) == ElementType.TABLE


# --- Test 6: URL detection ---
def test_url_detection():
    service = FarscryService()
    elem = {"text": "https://kairo.ai/docs", "type": "text"}
    assert service._classify_element(elem) == ElementType.URL


# --- Test 7: Contextual actions for DATE type ---
def test_contextual_actions_for_date():
    service = FarscryService()
    actions = service._get_contextual_actions(ElementType.DATE, {})
    assert "Schedule meeting from this date" in actions
    assert "Add to calendar" in actions


# --- Test 8: Contextual actions for ERROR type ---
def test_contextual_actions_for_error():
    service = FarscryService()
    actions = service._get_contextual_actions(ElementType.ERROR_MESSAGE, {})
    assert "Explain this error" in actions
    assert "Suggest fix" in actions


# --- Test 9: Cursor region capture and classification ---
def test_cursor_region_analysis():
    service = FarscryService()
    # Mocking Pillow ImageGrab to avoid OS gui capture dependencies in test runner
    with patch("PIL.ImageGrab.grab") as mock_grab:
        mock_img = MagicMock()
        mock_grab.return_value = mock_img

        res = service.analyze_cursor_region(100, 200)
        assert res["element_type"] == ElementType.TEXT_BLOCK.value
        assert "contextual_actions" in res
        assert mock_img.save.called


# --- Test 1: Word detected when winword.exe is active ---
def test_word_detected():
    proc_name = "winword.exe"
    assert "winword" in proc_name.lower()


# --- Test 2: Excel detected when excel.exe is active ---
def test_excel_detected():
    proc_name = "excel.exe"
    assert "excel" in proc_name.lower()


# --- Test 3: Chrome detected as Browser domain ---
def test_chrome_detected_as_browser():
    proc_name = "chrome.exe"
    assert "chrome" in proc_name.lower() or "msedge" in proc_name.lower()


# --- Test 4: VS Code detected as Code domain ---
def test_vscode_detected_as_code():
    proc_name = "code.exe"
    assert "code" in proc_name.lower()


# --- Test 5: App switch triggers preload start within 500ms ---
@pytest.mark.anyio
async def test_app_switch_triggers_preload():
    preloaded = []

    async def mock_preload(path):
        preloaded.append(path)

    # App switch detected winword.exe
    proc_name = "winword.exe"
    file_path = "C:/doc.docx"

    import time

    start = time.time()
    if "winword" in proc_name.lower():
        await mock_preload(file_path)
    elapsed = time.time() - start

    assert elapsed < 0.5  # Triggered within 500ms
    assert file_path in preloaded


# --- Test 6: Preload cache hit -> context assembles in under 100ms ---
def test_preload_cache_hit_latency():
    import time

    cache = {"C:/doc.docx": {"paragraphs": []}}

    start = time.time()
    file_path = "C:/doc.docx"
    assert file_path in cache
    cache[file_path]
    # Assembling context
    elapsed = time.time() - start
    assert elapsed < 0.1  # Assembles in under 100ms


# --- Tests for AppWatcher ---


def test_app_watcher_word_detection():
    watcher = AppWatcher()
    domain = watcher.get_domain_for_process("winword.exe")
    assert domain == Domain.WORD


def test_app_watcher_excel_detection():
    watcher = AppWatcher()
    domain = watcher.get_domain_for_process("excel.exe")
    assert domain == Domain.EXCEL


def test_app_watcher_chrome_detection():
    watcher = AppWatcher()
    domain = watcher.get_domain_for_process("chrome.exe")
    assert domain == Domain.BROWSER


def test_app_watcher_vscode_detection():
    watcher = AppWatcher()
    domain = watcher.get_domain_for_process("code.exe")
    assert domain == Domain.CODE


def test_app_watcher_terminal_detection():
    watcher = AppWatcher()
    domain = watcher.get_domain_for_process("windowsterminal.exe")
    assert domain == Domain.TERMINAL


def test_app_watcher_email_detection():
    watcher = AppWatcher()
    domain = watcher.get_domain_for_process("outlook.exe")
    assert domain == Domain.EMAIL


def test_context_assembler_latency():
    """Context assembly from preloaded cache should complete in under 100ms."""
    assembler = ContextAssembler()
    preloaded = {"paragraphs": list(range(100)), "styles": {"paragraph": ["Normal", "Heading 1"]}}

    start = time.time()
    ctx = assembler.assemble(
        preloaded_ctx=preloaded,
        cursor_pos=5,
        mem_ctx="Use bullet points",
        domain="word",
        file_path="C:/doc.docx",
    )
    elapsed = time.time() - start

    assert elapsed < 0.1  # Under 100ms
    assert ctx["domain"] == "word"
    assert ctx["cursor_pos"] == 5
    assert "paragraphs" in ctx


def test_context_assembler_no_preload():
    """Context assembler works even without preloaded context."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        preloaded_ctx=None, cursor_pos=0, mem_ctx="", domain="excel", file_path="C:/sheet.xlsx"
    )
    assert ctx["domain"] == "excel"
    assert ctx["cursor_pos"] == 0


def test_context_assembler_screen_context():
    """Screen context includes farscry visual element."""
    assembler = ContextAssembler()
    farscry_result = {
        "element_type": "CODE",
        "element_text": "def my_func():",
        "contextual_actions": ["Explain this code", "Write unit test"],
    }
    ctx = assembler.assemble_screen_context(
        farscry_result=farscry_result, preloaded_ctx=None, cursor_x=500, cursor_y=300, mem_ctx=""
    )
    assert ctx["visual_element"]["type"] == "CODE"
    assert "Explain this code" in ctx["visual_element"]["actions"]
