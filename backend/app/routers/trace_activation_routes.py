"""溯源码段启用总单路由：总单受理、印版更正、包装工位领用。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import service_for
from app.services.trace_code import PLATE_ACCEPTED

router = APIRouter(prefix="/api/trace-activation", tags=["溯源码启用总单"])


class PlatePayload(BaseModel):
    plate_id: str | None = None
    印版编号: str | None = None
    起始码号: Any = None
    结束码号: Any = None
    资料上传成功: bool | None = None
    上传资料成功: bool | None = None
    资料上传状态: str | None = None
    负责人: str | None = None
    批次号: str | None = None
    处理原因: str | None = None
    更正原因: str | None = None

    class Config:
        extra = "allow"


class OrderPayload(BaseModel):
    order_no: str | None = None
    order_id: int | None = None
    note: str | None = "提交启用总单"
    correction_reason: str | None = None
    plates: list[PlatePayload] = Field(default_factory=list)


class CorrectPayload(BaseModel):
    reason: str | None = None
    correction_reason: str | None = None
    plate: PlatePayload


class ClaimPayload(BaseModel):
    packing_id: int
    packing_no: str | None = None


def _trace_service():
    service = service_for("trace_code")
    if service is None or not hasattr(service, "submit_activation_order"):
        raise RuntimeError("溯源码段服务不支持启用总单")
    return service


@router.get("/orders")
def list_orders() -> dict[str, Any]:
    service = _trace_service()
    orders = service.list_activation_orders()
    return {"ok": True, "items": orders, "total": len(orders)}


@router.get("/orders/{order_id}")
def get_order(order_id: int) -> dict[str, Any]:
    service = _trace_service()
    order = service.get_activation_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"启用总单 {order_id} 不存在")
    return {"ok": True, "item": order}


@router.post("/orders")
def submit_order(payload: OrderPayload) -> dict[str, Any]:
    service = _trace_service()
    plates = [plate.model_dump(exclude_none=True) for plate in payload.plates]
    order, message = service.submit_activation_order(
        plates,
        payload.order_no,
        order_id=payload.order_id,
        note=payload.note or "提交启用总单",
        correction_reason=payload.correction_reason,
    )
    return {"ok": order is not None, "message": message, "item": order}


@router.post("/orders/{order_id}/plates/{plate_key}/correct")
def correct_plate(order_id: int, plate_key: str, payload: CorrectPayload) -> dict[str, Any]:
    service = _trace_service()
    reason = payload.reason or payload.correction_reason
    order, message = service.correct_activation_plate(
        order_id, plate_key, payload.plate.model_dump(exclude_none=True), reason,
    )
    return {"ok": order is not None, "message": message, "item": order}


@router.get("/orders/{order_id}/packing-available")
def packing_available(order_id: int) -> dict[str, Any]:
    service = _trace_service()
    order = service.get_activation_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"启用总单 {order_id} 不存在")
    plates = [
        plate for plate in order.get("plates", [])
        if plate.get("status") == PLATE_ACCEPTED
    ]
    return {"ok": True, "items": plates, "total": len(plates), "item": order}


@router.post("/orders/{order_id}/plates/{plate_key}/claim")
def claim_plate(order_id: int, plate_key: str, payload: ClaimPayload) -> dict[str, Any]:
    service = _trace_service()
    usage, message = service.claim_code_range_for_packing(
        order_id, plate_key, payload.packing_id, packing_no=payload.packing_no,
    )
    return {"ok": usage is not None, "message": message, "item": usage}
