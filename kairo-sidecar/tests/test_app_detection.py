import sys
from pathlib import Path

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.farscry_service import _label_for_process, _domain_for_label

TEST_APP_CASES = [
    # (process_name, expected_domain)
    ("WINWORD.EXE", "word"),
    ("winword.exe", "word"),
    ("excel.exe", "excel"),
    ("EXCEL.EXE", "excel"),
    ("powerpnt.exe", "powerpoint"),
    ("POWERPNT.EXE", "powerpoint"),
    ("chrome.exe", "browser"),
    ("chrome", "browser"),
    ("msedge.exe", "browser"),
    ("msedge", "browser"),
    ("firefox.exe", "browser"),
    ("firefox", "browser"),
    ("code.exe", "code"),
    ("code", "code"),
    ("notepad.exe", "notes"),
    ("notepad", "notes"),
    ("notepad++.exe", "code"),
    ("notepad++", "code"),
    ("powershell.exe", "terminal"),
    ("powershell", "terminal"),
    ("cmd.exe", "terminal"),
    ("cmd", "terminal"),
    ("windowsterminal.exe", "terminal"),
    ("windowsterminal", "terminal"),
    ("acrobat.exe", "pdf"),
    ("acrobat", "pdf"),
    ("outlook.exe", "word"),  # Outlook mail uses Word-like editor
    ("outlook", "word"),
    # Let's add variations / extensions / unrecognized ones for robustness
    ("WINWORD2.EXE", "word"),
    ("excel_custom.exe", "excel"),
    ("powerpnt_view.exe", "powerpoint"),
    ("chrome_dev.exe", "browser"),
    ("firefox_developer.exe", "browser"),
    ("code_insiders.exe", "code"),
    ("notepad_temp.exe", "notes"),
    ("powershell_ise.exe", "terminal"),
    # Unknowns -> should map to general
    ("unknown_proc.exe", "general"),
    ("spotify.exe", "general"),
    ("slack.exe", "general"),
    ("discord.exe", "general"),
    ("steam.exe", "general"),
    ("teams.exe", "general"),
    ("zoom.exe", "general"),
    ("calc.exe", "general"),
    ("explorer.exe", "general"),
    ("taskmgr.exe", "general"),
    ("cmd2.exe", "terminal"),
    ("powershell7.exe", "terminal"),
    ("notepad3.exe", "notes"),
    ("edge.exe", "browser"),
]


def test_app_detection_accuracy():
    assert len(TEST_APP_CASES) == 50

    correct_count = 0

    for proc_name, expected_domain in TEST_APP_CASES:
        label = _label_for_process(proc_name)
        domain = _domain_for_label(label)
        if domain == expected_domain:
            correct_count += 1

    accuracy = correct_count / len(TEST_APP_CASES)

    # Assert 95%+ accuracy
    assert (
        accuracy >= 0.95
    ), f"App detection accuracy was only {accuracy * 100:.1f}%, expected >= 95%"
