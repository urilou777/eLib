"""Shared request schemas used by the API routers."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DATE_PATTERN = r"^(\d{4}-\d{2}-\d{2})?$"


class OwnerIn(BaseModel):
    name: str
    kind: str = "maison_mere"
    reverse_pct: float = 100
    priority: int = 1
    color: Optional[str] = "#6c8cff"


class BookIn(BaseModel):
    code: str
    title: str
    series: Optional[str] = None
    volume: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    category: Optional[str] = "Standard"
    type: Optional[str] = None
    location: Optional[str] = None
    price: float = 0
    min_stock: int = 2
    is_pack: int = 0


class BookEnrichIn(BaseModel):
    code: Optional[str] = Field(None, max_length=100)
    title: Optional[str] = Field(None, max_length=300)
    series: Optional[str] = Field(None, max_length=200)
    volume: Optional[str] = Field(None, max_length=100)
    author: Optional[str] = Field(None, max_length=200)
    publisher: Optional[str] = Field(None, max_length=200)
    price: Optional[float] = Field(None, ge=0, le=100000)


class PackItem(BaseModel):
    book_id: int
    qty: int = 1


class LotIn(BaseModel):
    book_id: int
    owner_id: int
    qty_in: int = Field(ge=1, le=100000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    unit_cost: Optional[float] = Field(None, ge=0, le=100000)
    reverse_pct: Optional[float] = Field(None, ge=0, le=100)
    note: Optional[str] = Field(None, max_length=300)


class AdjIn(BaseModel):
    delta: int = Field(ge=-100000, le=100000)
    reason: Optional[str] = Field("Ajustement", max_length=300)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)


class AllocIn(BaseModel):
    book_id: Optional[int] = None
    lot_id: int
    qty: int = Field(ge=1, le=1000)


class LineIn(BaseModel):
    book_id: int
    qty: int = Field(1, ge=1, le=1000)
    unit_price: Optional[float] = Field(None, ge=0, le=100000)
    allocations: List[AllocIn] = Field(default_factory=list, max_length=50)


class PaymentPartIn(BaseModel):
    payment: str = Field(max_length=60)
    amount: float = Field(gt=0, le=100000)


class SaleIn(BaseModel):
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    payment: Optional[str] = Field("Espèces", max_length=200)
    payments: Optional[List[PaymentPartIn]] = None
    note: Optional[str] = Field(None, max_length=300)
    customer_gender: Optional[str] = Field(None, max_length=20)
    customer_age_group: Optional[str] = Field(None, max_length=40)
    is_star: Optional[int] = 0
    service_moment: Optional[str] = Field(None, max_length=60)
    lines: List[LineIn] = Field(min_length=1, max_length=200)


class CashMovementIn(BaseModel):
    user_name: str = Field(max_length=60)
    type: Literal["DEPOSIT", "WITHDRAWAL"]
    channel: Literal["ESPECES", "WERO", "PAYPAL"]
    amount: float = Field(gt=0, lt=100000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    note: Optional[str] = Field(None, max_length=300)


class SettleIn(BaseModel):
    owner_id: int
    amount: float = Field(gt=-1000000, lt=1000000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    note: Optional[str] = Field(None, max_length=300)


class LocalCardSettingIn(BaseModel):
    enabled: bool


class ResIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = Field(None, max_length=300)
    qty: int = Field(1, ge=1, le=1000)
    status: str = Field("En attente", max_length=40)
    note: Optional[str] = Field(None, max_length=300)


class DropdownItemIn(BaseModel):
    group_key: Literal["category", "type", "payment", "publisher", "service_moment"]
    label: str = Field(min_length=1, max_length=80)


class OcrScanIn(BaseModel):
    image_base64: str


class DropdownItemRenameIn(BaseModel):
    new_label: str = Field(min_length=1, max_length=80)
    cascade: bool = True


class UserIn(BaseModel):
    name: str = Field(max_length=60)


class PairIn(BaseModel):
    code: str = Field(min_length=8, max_length=64)
    name: Optional[str] = Field(None, max_length=60)
    device_key: Optional[str] = Field(None, min_length=16, max_length=80)
    previous_token: Optional[str] = Field(None, min_length=20, max_length=100)


class ActiveBasketItem(BaseModel):
    title: str
    qty: int = 1
    price: float = 0.0


class ActiveBasketIn(BaseModel):
    user_name: Optional[str] = "Libraire"
    device_key: Optional[str] = Field(None, min_length=16, max_length=80)
    total: float = 0.0
    qty: int = 0
    items: List[ActiveBasketItem] = Field(default_factory=list)
    mode: Optional[str] = "sale"
    moment: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    star: Optional[int] = 0
    battery: Optional[float] = None
    is_charging: Optional[bool] = None
    action: Optional[dict] = None


class ActivityEventIn(BaseModel):
    type: str
    user_name: Optional[str] = "Libraire"
    title: Optional[str] = None
    detail: Optional[str] = None
    data: Optional[dict] = None
