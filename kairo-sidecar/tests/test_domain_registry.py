from unittest.mock import patch
from sidecar.domain_registry import (
    load_registry,
    set_domain_mode,
    get_domain_mode,
)
from sidecar.router import DomainMasterRouter, KairoRequest


def test_load_save_registry(tmp_path):
    # Mock REGISTRY_PATH to use a temp path
    test_path = tmp_path / "domain_registry.json"
    with patch("sidecar.domain_registry.REGISTRY_PATH", test_path):
        data = load_registry()
        assert "Word" in data
        assert data["Word"] == "Real"

        # Modify and save
        set_domain_mode("Word", "PromptOnly")
        assert get_domain_mode("Word") == "PromptOnly"

        # Case insensitivity
        assert get_domain_mode("word") == "PromptOnly"
        assert get_domain_mode("WORD") == "PromptOnly"

        # Set back to Real
        set_domain_mode("word", "Real")
        assert get_domain_mode("Word") == "Real"


def test_router_blocks_prompt_only_domain(tmp_path):
    test_path = tmp_path / "domain_registry.json"
    with patch("sidecar.domain_registry.REGISTRY_PATH", test_path):
        # Set Excel domain to PromptOnly
        set_domain_mode("Excel", "PromptOnly")

        router = DomainMasterRouter()
        request = KairoRequest(
            user_id="test_user",
            domain="excel",
            user_prompt="Insert a sum formula in cell A1",
            file_path="dummy.xlsx",
        )

        res = router.route(request)
        assert res.type == "error"
        assert res.domain == "excel"
        assert "Domain Excel is unavailable. Operating in PromptOnly mode." in res.error
