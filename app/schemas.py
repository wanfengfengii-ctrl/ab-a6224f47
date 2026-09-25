"""请求体的 Pydantic 校验模型。"""
from pydantic import BaseModel, Field, model_validator

MAX_DIM = 10000
MAX_PHASE = 1_000_000


class DamageIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    width: int = Field(ge=1, le=MAX_DIM)
    height: int = Field(ge=1, le=MAX_DIM)
    phaseMin: int = Field(ge=0, le=MAX_PHASE)
    phaseMax: int = Field(ge=0, le=MAX_PHASE)

    @model_validator(mode="after")
    def _check_phase_range(self):
        if self.phaseMax < self.phaseMin:
            raise ValueError("phaseMax 必须不小于 phaseMin")
        return self


class Region(BaseModel):
    x: int = Field(ge=0, le=MAX_DIM)
    y: int = Field(ge=0, le=MAX_DIM)
    width: int = Field(ge=1, le=MAX_DIM)
    height: int = Field(ge=1, le=MAX_DIM)


class ScrapIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    region: Region
    period: int = Field(ge=1, le=MAX_DIM)
    origin: int = Field(ge=0, le=MAX_PHASE)
    maxUses: int = Field(ge=1, le=100)


class SolveRequest(BaseModel):
    damages: list[DamageIn] = Field(min_length=3, max_length=5)
    scraps: list[ScrapIn] = Field(min_length=4, max_length=8)

    @model_validator(mode="after")
    def _check_unique_ids(self):
        damage_ids = [d.id for d in self.damages]
        if len(set(damage_ids)) != len(damage_ids):
            raise ValueError("破损 id 必须唯一")
        scrap_ids = [s.id for s in self.scraps]
        if len(set(scrap_ids)) != len(scrap_ids):
            raise ValueError("边料 id 必须唯一")
        return self
