from pydantic import BaseModel, Field, field_validator
from typing import Literal, Union, List, Optional


class SlideParagraph(BaseModel):
    text: str
    bullet: bool = True
    level: int = Field(default=0, ge=0, le=4)

    @field_validator("text")
    @classmethod
    def check_non_empty(cls, v: str) -> str:
        return v

    def model_post_init(self, __context) -> None:
        if self.bullet and self.text:
            word_count = len(self.text.strip().split())
            if word_count > 7:
                raise ValueError(
                    f"Bullet paragraph text exceeds 7 words limit ({word_count} words): '{self.text}'"
                )


class UpdateShapeTextOp(BaseModel):
    type: Literal["update_shape_text"] = "update_shape_text"
    slide_index: int
    shape_id: str
    paragraphs: List[SlideParagraph]
    left: Optional[float] = None
    top: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None

    @field_validator("paragraphs")
    @classmethod
    def check_max_bullets(cls, v: List[SlideParagraph]) -> List[SlideParagraph]:
        bullets = [p for p in v if p.bullet]
        if len(bullets) > 5:
            raise ValueError(f"Maximum of 5 bullets per slide allowed, got {len(bullets)}")
        return v


class UpdateTitleOp(BaseModel):
    type: Literal["update_title"] = "update_title"
    slide_index: int
    text: str

    @field_validator("text")
    @classmethod
    def check_title_length(cls, v: str) -> str:
        word_count = len(v.strip().split())
        if word_count > 7:
            raise ValueError(f"Title exceeds 7 words limit ({word_count} words): '{v}'")
        return v


class AddSlideOp(BaseModel):
    type: Literal["add_slide"] = "add_slide"
    after_index: int
    layout_name: str = "Title and Content"
    title: Optional[str] = None
    bullets: Optional[List[str]] = None


class UpdateNotesOp(BaseModel):
    type: Literal["update_notes"] = "update_notes"
    slide_index: int
    text: str


SlideOperation = Union[UpdateShapeTextOp, UpdateTitleOp, AddSlideOp, UpdateNotesOp]


class SlideResponse(BaseModel):
    operations: List[SlideOperation]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
