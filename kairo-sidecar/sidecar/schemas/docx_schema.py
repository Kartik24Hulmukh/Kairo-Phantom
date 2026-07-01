from pydantic import BaseModel, Field
from typing import Literal, Union, List


class ParagraphRun(BaseModel):
    text: str
    bold: bool = False
    italic: bool = False


class InsertParagraphOp(BaseModel):
    type: Literal["insert_paragraph"]
    after_paragraph_index: int  # -1 = append to end
    style: str  # must be valid Word style: "Normal", "Heading1"..."Heading6", "ListBullet", "ListNumber", "Quote"
    runs: List[ParagraphRun]


class ReplaceParagraphOp(BaseModel):
    type: Literal["replace_paragraph"]
    paragraph_index: int
    style: str
    runs: List[ParagraphRun]


class AppendToRunOp(BaseModel):
    type: Literal["append_to_run"]
    paragraph_index: int
    runs: List[ParagraphRun]


class InsertTableOp(BaseModel):
    type: Literal["insert_table"]
    after_paragraph_index: int
    headers: List[str]
    rows: List[List[str]]


class DeleteParagraphOp(BaseModel):
    type: Literal["delete_paragraph"]
    paragraph_index: int


DocxOperation = Union[
    InsertParagraphOp, ReplaceParagraphOp, AppendToRunOp, InsertTableOp, DeleteParagraphOp
]


class DocxResponse(BaseModel):
    operations: List[DocxOperation]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=200)
    style_validation_mode: Literal["strict", "fuzzy"] = "fuzzy"
