from sidecar.masters.other_masters import DesignMaster
from sidecar.schemas.domain_schemas import DesignResponse, CreateTextOp, DesignShowOnlyOp


def test_design_master_extract_context():
    master = DesignMaster()

    # Canva file path -> Canva tool
    ctx_canva = master.extract_context("banner-canva.png", None)
    assert ctx_canva["design_tool"] == "Canva"

    # Figma -> Figma
    ctx_figma = master.extract_context("FigmaFrame1", None)
    assert ctx_figma["design_tool"] == "Figma"


def test_design_master_build_prompt():
    master = DesignMaster()
    context = {
        "design_tool": "Penpot",
        "active_frame_name": "Artboard 1",
        "canvas_dimensions": [1440, 900],
        "color_tokens": {"brand": "#FF00AA"},
        "type_tokens": {"body": "Outfit Regular 14px"},
        "layers_json": "[]",
    }

    prompt = master.build_prompt("align layers", context, mem_context="")
    assert "SYSTEM:" in prompt
    assert "Penpot" in prompt
    assert "Artboard 1" in prompt
    assert "1440, 900" in prompt
    assert "brand" in prompt
    assert "Outfit" in prompt
    assert "align layers" in prompt


def test_design_master_validate_operations_canva_fallback():
    master = DesignMaster()

    resp = DesignResponse(
        injection_method="figma_mcp",  # LLM returned figma_mcp
        operations=[DesignShowOnlyOp(design_suggestion="Add more whitespace")],
        design_rationale="More modern design",
        confidence=0.9,
    )

    context = {"design_tool": "Canva"}
    ops = master.validate_operations(resp, context)
    assert len(ops) == 1
    # Check that injection method gets coerced to clipboard
    assert ops[0]["injection_method"] == "clipboard"


def test_design_master_validate_operations_auto_layout():
    master = DesignMaster()

    resp = DesignResponse(
        injection_method="figma_mcp",
        operations=[
            CreateTextOp(
                parent_frame_id="frame_123",
                text="Hello World",
                x=150,  # absolute offsets should be set to 0 under auto-layout
                y=300,
                width=100,
                font_weight="medium",
            )
        ],
        design_rationale="Add heading",
        confidence=0.9,
    )

    # Auto-layout active in frame
    context = {"design_tool": "Figma", "auto_layout_active": True}
    ops = master.validate_operations(resp, context)
    assert len(ops) == 1
    assert ops[0]["operations"][0]["x"] == 0
    assert ops[0]["operations"][0]["y"] == 0
