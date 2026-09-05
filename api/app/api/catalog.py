"""Product catalog.  Product flow screens 16 and 17.

Every product, variant and price list in one place, plus the detail view that
edits one. Writes here are catalog data, never quotation state: a price change
does NOT retro-alter an existing quote, because `quote_line.unit_price` is
copied at the time the line is added.
"""

from __future__ import annotations

import math
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session, require_roles
from app.models.enums import Role
from app.models.tables import (
    PriceList,
    PriceListItem,
    Product,
    ProductVariant,
    Stock,
    User,
)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class ProductIn(BaseModel):
    sku: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=200)
    category: str
    list_price: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    is_subscription: bool = False
    is_promoted: bool = False


class ProductPatch(BaseModel):
    name: str | None = None
    list_price: Decimal | None = Field(default=None, gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    is_promoted: bool | None = None


class VariantIn(BaseModel):
    attribute: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=120)
    extra_price: Decimal = Decimal("0")


class PriceListItemIn(BaseModel):
    price_list_id: int
    price: Decimal = Field(gt=0)


@router.get("/price-lists")
def list_price_lists(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    return [
        {"id": pl.id, "name": pl.name, "currency": pl.currency}
        for pl in session.scalars(select(PriceList).order_by(PriceList.id)).all()
    ]


@router.get("/summary")
def catalog_summary(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    products = session.scalar(select(func.count()).select_from(Product)) or 0
    variants = session.scalar(select(func.count()).select_from(ProductVariant)) or 0
    lists = session.scalar(select(func.count()).select_from(PriceList)) or 0
    currencies = session.scalars(select(PriceList.currency).distinct()).all()
    subs = session.scalar(
        select(func.count()).select_from(Product)
        .where(Product.is_subscription.is_(True))
    ) or 0
    return {
        "total_products": products,
        "subscription_products": subs,
        "price_lists": lists,
        "currencies": sorted(set(currencies)),
        "variants": variants,
    }


@router.get("/products")
def list_products(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    category: str | None = None,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    base_stmt = select(Product)
    if category and category != "all":
        base_stmt = base_stmt.where(Product.category == category)
    total_count = session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    offset = (page - 1) * page_size
    stmt = base_stmt.order_by(Product.category, Product.name).offset(offset).limit(page_size)
    rows = session.scalars(stmt).all()

    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str(total_pages)

    if not rows:
        return []

    p_ids = [p.id for p in rows]
    variant_counts = dict(
        session.execute(
            select(ProductVariant.product_id, func.count())
            .where(ProductVariant.product_id.in_(p_ids))
            .group_by(ProductVariant.product_id)
        ).all()
    )
    stock_totals = dict(
        session.execute(
            select(Stock.product_id, func.sum(Stock.qty_on_hand - Stock.qty_reserved))
            .where(Stock.product_id.in_(p_ids))
            .group_by(Stock.product_id)
        ).all()
    )
    return [
        {
            "id": p.id, "sku": p.sku, "name": p.name, "category": p.category,
            "list_price": str(p.list_price), "unit_cost": str(p.unit_cost),
            "margin_pct": str(
                ((p.list_price - p.unit_cost) / p.list_price * 100).quantize(
                    Decimal("0.1")
                )
            ) if p.list_price else "0",
            "is_subscription": p.is_subscription,
            "is_promoted": p.is_promoted,
            "variants": variant_counts.get(p.id, 0),
            "qty_available": int(stock_totals.get(p.id) or 0),
        }
        for p in rows
    ]


@router.get("/products/{product_id}")
def product_detail(
    product_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")

    variants = session.scalars(
        select(ProductVariant)
        .where(ProductVariant.product_id == product_id)
        .order_by(ProductVariant.attribute, ProductVariant.id)
    ).all()
    grouped: dict[str, list[dict]] = {}
    for v in variants:
        grouped.setdefault(v.attribute, []).append(
            {"value": v.value, "extra_price": str(v.extra_price)}
        )

    price_rows = session.execute(
        select(PriceListItem, PriceList)
        .join(PriceList, PriceListItem.price_list_id == PriceList.id)
        .where(PriceListItem.product_id == product_id)
        .order_by(PriceList.id)
    ).all()

    stock = session.execute(
        select(Stock.warehouse_id, Stock.qty_on_hand, Stock.qty_reserved)
        .where(Stock.product_id == product_id)
    ).all()

    return {
        "id": product.id, "sku": product.sku, "name": product.name,
        "category": product.category,
        "list_price": str(product.list_price),
        "unit_cost": str(product.unit_cost),
        "is_subscription": product.is_subscription,
        "is_promoted": product.is_promoted,
        # only meaningful for subscription products — the UI hides it otherwise
        "recurring_interval": "Monthly" if product.is_subscription else None,
        "qty_on_hand": sum(s.qty_on_hand for s in stock),
        "qty_reserved": sum(s.qty_reserved for s in stock),
        "variants": [
            {"attribute": attr, "values": values} for attr, values in grouped.items()
        ],
        "price_lists": [
            {"name": pl.name, "currency": pl.currency, "price": str(item.price)}
            for item, pl in price_rows
        ],
    }


@router.post("/products", status_code=201)
def create_product(
    body: ProductIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    if session.scalar(select(Product).where(Product.sku == body.sku)):
        raise HTTPException(status_code=409, detail=f"sku {body.sku} already exists")
    if body.unit_cost >= body.list_price:
        raise HTTPException(
            status_code=400,
            detail="unit_cost must be below list_price, or every line sells at a loss",
        )
    product = Product(**body.model_dump())
    session.add(product)
    session.flush()
    return product_detail(product.id, session)


@router.patch("/products/{product_id}")
def update_product(
    product_id: int,
    body: ProductPatch,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")

    updates = body.model_dump(exclude_none=True)
    new_price = updates.get("list_price", product.list_price)
    new_cost = updates.get("unit_cost", product.unit_cost)
    if new_cost >= new_price:
        raise HTTPException(
            status_code=400, detail="unit_cost must stay below list_price"
        )
    for field, value in updates.items():
        setattr(product, field, value)
    session.flush()
    return product_detail(product_id, session)


# --------------------------------------------------------------------------
# variants and price lists  (screen 17)
# --------------------------------------------------------------------------


@router.post("/products/{product_id}/variants", status_code=201)
def add_variant(
    product_id: int,
    body: VariantIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")

    duplicate = session.scalar(
        select(ProductVariant).where(
            ProductVariant.product_id == product_id,
            ProductVariant.attribute == body.attribute,
            ProductVariant.value == body.value,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"{body.attribute} '{body.value}' already exists on this product",
        )

    # A variant that takes the price below cost would sell at a loss on every
    # line that selects it — the same rule the product itself is held to.
    if product.list_price + body.extra_price <= product.unit_cost:
        raise HTTPException(
            status_code=400,
            detail=(
                f"extra_price {body.extra_price} would put the variant price at or "
                f"below unit cost {product.unit_cost}"
            ),
        )

    session.add(ProductVariant(
        product_id=product_id, attribute=body.attribute,
        value=body.value, extra_price=body.extra_price,
    ))
    session.flush()
    return product_detail(product_id, session)


@router.delete("/products/{product_id}/variants/{variant_id}")
def remove_variant(
    product_id: int,
    variant_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    variant = session.get(ProductVariant, variant_id)
    if variant is None or variant.product_id != product_id:
        raise HTTPException(status_code=404, detail="variant not on this product")
    session.delete(variant)
    session.flush()
    return product_detail(product_id, session)


@router.put("/products/{product_id}/price-list")
def set_price_list_item(
    product_id: int,
    body: PriceListItemIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    if session.get(PriceList, body.price_list_id) is None:
        raise HTTPException(
            status_code=404, detail=f"price list {body.price_list_id} not found"
        )
    if body.price <= product.unit_cost:
        raise HTTPException(
            status_code=400,
            detail=(
                f"price {body.price} is at or below unit cost {product.unit_cost} — "
                f"every sale on this list would lose money"
            ),
        )

    existing = session.scalar(
        select(PriceListItem).where(
            PriceListItem.price_list_id == body.price_list_id,
            PriceListItem.product_id == product_id,
        )
    )
    if existing is not None:
        existing.price = body.price
    else:
        session.add(PriceListItem(
            price_list_id=body.price_list_id,
            product_id=product_id,
            price=body.price,
        ))
    session.flush()
    return product_detail(product_id, session)
