"""溯源码段领域服务：激活溯源二维码码段，关联批次并校验前置门禁，关联发运单。

本模块同时承载“启用总单”聚合：一张总单可以包含多套印版，但每套印版仍逐项
受理、逐项生成可生效码段。包装工位只能领用总单中状态为“已受理”的印版。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

ORDER_TABLE = "trace_activation_order"
USAGE_TABLE = "trace_activation_usage"

PLATE_ACCEPTED = "已受理"
PLATE_PENDING_VERIFICATION = "整组等核验"
PLATE_INDEPENDENT_ERROR = "独立错误"
ORDER_IN_PROGRESS = "办理中"
ORDER_COMPLETED = "已办结"


class TraceCodeService(BaseModuleService):
    MODULE = "trace_code"
    ENTITY = "码段"
    OPERATION_TERM = "激活码段"
    LIST_FIELDS = ["起始码号", "结束码号", "激活日期", "扫码次数", "登记编号", "负责人", "生效版本", "备注说明"]
    REQUIRED_FIELDS = ["起始码号", "结束码号"]
    STATUS_ORDER = ["草稿", "待确认", "已确认", "已撤回"]
    ACTION_RULES = {"激活码段": "已确认", "提交确认": "待确认", "撤回记录": "已撤回"}
    NEGATIVE_ACTIONS = []

    def validate_entry(self, values: dict[str, Any]) -> list[str]:
        errors = []
        start = str(values.get("起始码号", "")).strip()
        end = str(values.get("结束码号", "")).strip()
        start_num = self._parse_code(start)
        end_num = self._parse_code(end)
        if start_num is not None and end_num is not None:
            if start_num >= end_num:
                errors.append("起始码号必须小于结束码号")
            if end_num - start_num > 100000:
                errors.append("单次激活码段不得超过100000个码号")

        # 码号范围重叠检查
        existing = store.rows(self.MODULE)
        for r in existing:
            if r.get("id") == values.get("id") or r.get("status") == "已撤回":
                continue
            es = self._parse_code(r.get("起始码号", ""))
            ee = self._parse_code(r.get("结束码号", ""))
            if es is None or ee is None or start_num is None or end_num is None:
                continue
            if not (end_num < es or start_num > ee):
                errors.append(f"码段范围与已有码段 {r.get('登记编号', r.get('id'))} 重叠")
        return errors

    def on_confirm(self, entry: dict[str, Any], action: str) -> tuple[bool, str | None]:
        """激活码段时检查所有前置门禁条件。"""
        if action == "激活码段":
            # 检查检测报告
            testing_svc = self._get_service("testing")
            if not testing_svc.has_valid_report():
                return False, "缺少已签收的检测报告，不允许激活溯源码段"

            # 检查认证资质
            from app.services.certification import CertificationService
            cert_svc = CertificationService()
            if not cert_svc.has_valid_certification():
                return False, "缺少有效期内的认证资质证书，不允许激活溯源码段"

            # 检查拼配确认
            batch_no = entry.get("批次号", "")
            if batch_no:
                lineage = store.get_batch_lineage_nodes(batch_no)
                has_blending = any(n["module"] == "blending" for n in lineage)
                if has_blending:
                    for n in lineage:
                        if n["module"] == "blending":
                            blend = store.find("blending", n["entry_id"])
                            if blend and blend.get("status") != "已确认":
                                return False, "该批次的拼配配方尚未确认，不能激活溯源码段"
        return True, None

    def _get_service(self, name: str):
        from app.services import service_for
        return service_for(name)

    def get_active_codes(self) -> list[dict[str, Any]]:
        """获取已激活的溯源码段。"""
        return [r for r in store.rows(self.MODULE) if r.get("status") == "已确认"]

    def assign_to_shipment(self, code_entry_id: int, shipment_entry_id: int) -> tuple[bool, str]:
        """将溯源码段分配到发运单。"""
        code_entry = store.find(self.MODULE, code_entry_id)
        if code_entry is None:
            return False, f"溯源码段 {code_entry_id} 不存在"
        if code_entry.get("status") != "已确认":
            return False, f"溯源码段 {code_entry_id} 未激活"

        shipment_entry = store.find("shipment", shipment_entry_id)
        if shipment_entry is None:
            return False, f"发运单 {shipment_entry_id} 不存在"

        code_entry["shipment_id"] = shipment_entry_id
        code_entry["shipment_no"] = shipment_entry.get("登记编号", str(shipment_entry_id))
        store.log_event(self.MODULE, code_entry_id, "assign_to_shipment",
                        {"shipment_id": shipment_entry_id})
        return True, f"溯源码段 {code_entry_id} 已关联到发运单 {shipment_entry_id}"

    def get_codes_by_shipment(self, shipment_entry_id: int) -> list[dict[str, Any]]:
        """获取关联到指定发运单的溯源码段。"""
        rows = store.rows(self.MODULE)
        return [r for r in rows if r.get("shipment_id") == shipment_entry_id]

    # ── 启用总单：印版逐项受理、包装逐项领用 ──

    @staticmethod
    def _parse_code(value: Any) -> int | None:
        """把 TRACE-0001 这类编号转为可比较的数字；无法解析时返回 None。"""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        token = text.split("-")[-1] if "-" in text else text
        try:
            return int(token)
        except ValueError:
            return None

    @staticmethod
    def _next_id(table: str) -> int:
        return max((int(row.get("id", 0)) for row in store.rows(table)), default=0) + 1

    @staticmethod
    def _plate_key(plate: dict[str, Any]) -> str:
        return str(plate.get("plate_id") or plate.get("印版编号") or "").strip()

    def _find_order(self, order_id: int | None = None, order_no: str | None = None) -> dict[str, Any] | None:
        for order in store.rows(ORDER_TABLE):
            if order_id is not None and int(order.get("id", 0)) == int(order_id):
                return order
            if order_no and str(order.get("order_no") or order.get("登记编号")) == str(order_no):
                return order
        return None

    def _find_plate(self, order: dict[str, Any], plate_key: str) -> dict[str, Any] | None:
        for plate in order.get("plates", []):
            if str(plate.get("plate_id") or plate.get("印版编号")) == str(plate_key):
                return plate
        return None

    @staticmethod
    def _upload_succeeded(plate: dict[str, Any]) -> bool:
        if "资料上传成功" in plate:
            value = plate["资料上传成功"]
        elif "上传资料成功" in plate:
            value = plate["上传资料成功"]
        elif "资料上传状态" in plate:
            return str(plate["资料上传状态"]).strip() in {"成功", "已上传", "完成"}
        else:
            value = plate.get("upload_succeeded", True)
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() not in {"false", "0", "否", "失败", ""}

    def _active_trace_ranges(self, exclude_trace_id: int | None = None) -> list[dict[str, Any]]:
        ranges = []
        for row in store.rows(self.MODULE):
            if row.get("status") != "已确认" or int(row.get("id", 0)) == exclude_trace_id:
                continue
            start = self._parse_code(row.get("起始码号"))
            end = self._parse_code(row.get("结束码号"))
            if start is not None and end is not None:
                ranges.append({"start": start, "end": end, "row": row})
        return ranges

    def _accepted_plate_ranges(
        self,
        *,
        exclude_order_id: int | None = None,
        exclude_plate_key: str | None = None,
    ) -> list[dict[str, Any]]:
        ranges = []
        for order in store.rows(ORDER_TABLE):
            for plate in order.get("plates", []):
                if plate.get("status") != PLATE_ACCEPTED:
                    continue
                if exclude_order_id is not None and int(order.get("id", 0)) == exclude_order_id and \
                        self._plate_key(plate) == str(exclude_plate_key):
                    continue
                start = self._parse_code(plate.get("起始码号"))
                end = self._parse_code(plate.get("结束码号"))
                if start is not None and end is not None:
                    ranges.append({"start": start, "end": end, "plate": plate, "order": order})
        return ranges

    def _find_overlap(self, start: int, end: int, *, order_id: int, plate_key: str) -> str | None:
        for item in self._active_trace_ranges():
            if not (end < item["start"] or start > item["end"]):
                row = item["row"]
                return f"号码 {start}-{end} 与已有激活码 {row.get('登记编号', row.get('id'))} 重叠"
        for item in self._accepted_plate_ranges(exclude_order_id=order_id, exclude_plate_key=plate_key):
            if not (end < item["start"] or start > item["end"]):
                plate = item["plate"]
                return f"号码 {start}-{end} 与已受理印版 {plate.get('印版编号', plate.get('plate_id'))} 重叠"
        return None

    def _revoke_trace_code(self, trace_id: Any, reason: str) -> None:
        if trace_id is None:
            return
        row = store.find(self.MODULE, int(trace_id))
        if row and row.get("status") == "已确认":
            row["status"] = "已撤回"
            row["pending"] = True
            row["撤回原因"] = reason
            store.log_event(self.MODULE, int(trace_id), "撤回记录", {"reason": reason})

    def _create_accepted_trace_code(self, order: dict[str, Any], plate: dict[str, Any]) -> dict[str, Any]:
        trace_id = self._next_id(self.MODULE)
        plate_key = self._plate_key(plate)
        entry = {
            "id": trace_id,
            "起始码号": plate["起始码号"],
            "结束码号": plate["结束码号"],
            "激活日期": str(date.today()),
            "扫码次数": 0,
            "登记编号": f"TCA-{int(order['id']):04d}-{plate_key}",
            "负责人": plate.get("负责人", ""),
            "生效版本": order.get("version", 1),
            "备注说明": f"启用总单 {order.get('order_no')} 受理印版 {plate_key}",
            "批次号": plate.get("批次号", ""),
            "status": "已确认",
            "pending": False,
            "abnormal": False,
            "frozen": False,
            "activation_order_id": int(order["id"]),
            "activation_order_no": order.get("order_no"),
            "plate_id": plate_key,
            "印版编号": plate.get("印版编号", plate_key),
            "受理状态": PLATE_ACCEPTED,
            "packing_id": None,
            "packing_no": None,
            "领用状态": "未领取",
        }
        store.rows(self.MODULE).append(entry)
        plate["trace_code_id"] = trace_id
        plate["trace_code_no"] = entry["登记编号"]
        store.log_event(self.MODULE, trace_id, "启用总单受理", {
            "order_id": order["id"], "plate_id": plate_key,
            "起始码号": plate["起始码号"], "结束码号": plate["结束码号"],
        })
        return entry

    @staticmethod
    def _range_text(plate: dict[str, Any]) -> str:
        return f"{plate.get('起始码号')}-{plate.get('结束码号')}"

    def _used_ranges(self, order: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "plate_id": plate.get("plate_id"),
                "印版编号": plate.get("印版编号"),
                "起始码号": plate.get("起始码号"),
                "结束码号": plate.get("结束码号"),
                "码段范围": self._range_text(plate),
                "包装批ID": plate.get("packing_id"),
                "包装批编号": plate.get("packing_no"),
                "trace_code_id": plate.get("trace_code_id"),
            }
            for plate in order.get("plates", [])
            if plate.get("usage") or plate.get("领取状态") == "已领取"
        ]

    def _refresh_order(self, order: dict[str, Any]) -> None:
        plates = order.get("plates", [])
        order["实际使用范围"] = self._used_ranges(order)
        order["actual_used_ranges"] = list(order["实际使用范围"])
        if not order.get("首次实际使用范围") and order["实际使用范围"]:
            order["首次实际使用范围"] = list(order["实际使用范围"])
        order["修正后实际使用范围"] = list(order["实际使用范围"])
        order["accepted_count"] = sum(1 for p in plates if p.get("status") == PLATE_ACCEPTED)
        order["pending_count"] = sum(1 for p in plates if p.get("status") == PLATE_PENDING_VERIFICATION)
        order["error_count"] = sum(1 for p in plates if p.get("status") == PLATE_INDEPENDENT_ERROR)
        order["status"] = ORDER_COMPLETED if plates and all(
            p.get("status") == PLATE_ACCEPTED for p in plates
        ) else ORDER_IN_PROGRESS
        order["pending"] = order["status"] == ORDER_IN_PROGRESS

    def _snapshot_submission(self, order: dict[str, Any], note: str) -> None:
        order.setdefault("submission_history", []).append({
            "version": order.get("version", 1),
            "note": note,
            "accepted_ranges": [
                self._range_text(p) for p in order["plates"] if p.get("status") == PLATE_ACCEPTED
            ],
            "pending_plates": [
                p.get("印版编号", p.get("plate_id"))
                for p in order["plates"] if p.get("status") == PLATE_PENDING_VERIFICATION
            ],
            "error_plates": [
                p.get("印版编号", p.get("plate_id"))
                for p in order["plates"] if p.get("status") == PLATE_INDEPENDENT_ERROR
            ],
            "actual_used_ranges": self._used_ranges(order),
        })

    def submit_activation_order(
        self,
        plates: list[dict[str, Any]] | dict[str, Any],
        order_no: str | None = None,
        *,
        order_id: int | None = None,
        note: str = "提交启用总单",
        correction_reason: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """提交或续办启用总单。返回 (总单, 消息)。

        每套印版独立判定：资料失败为“整组等核验”，范围重叠为“独立错误”，
        只有通过校验的印版才会正式受理并生成已激活码段。
        """
        if isinstance(plates, dict):
            payload = plates
            order_no = order_no or payload.get("order_no") or payload.get("登记编号")
            order_id = order_id or payload.get("order_id")
            correction_reason = correction_reason or payload.get("correction_reason") or payload.get("更正原因")
            plates = payload.get("plates") or payload.get("印版") or []
        if not isinstance(plates, list) or not plates:
            return None, "启用总单至少需要包含一套印版"

        existing = self._find_order(order_id, order_no)
        if existing is not None:
            order = existing
            order["version"] = int(order.get("version", 1)) + 1
            action_note = note if note != "提交启用总单" else "续办启用总单"
        else:
            order = {
                "id": self._next_id(ORDER_TABLE),
                "order_no": order_no or f"TCO-{date.today().strftime('%Y%m%d')}-{self._next_id(ORDER_TABLE):04d}",
                "登记编号": order_no or "",
                "status": ORDER_IN_PROGRESS,
                "version": 1,
                "plates": [],
                "submission_history": [],
                "实际使用范围": [],
                "actual_used_ranges": [],
                "pending": True,
                "abnormal": False,
            }
            order["登记编号"] = order["order_no"]
            store.rows(ORDER_TABLE).append(order)
            action_note = note
            store.log_event(ORDER_TABLE, int(order["id"]), "create_activation_order", {"plates": len(plates)})

        messages: list[str] = []
        for raw_plate in plates:
            plate_data = dict(raw_plate)
            plate_key = self._plate_key(plate_data) or f"P{len(order['plates']) + 1}"
            plate_data["plate_id"] = plate_key
            plate_data.setdefault("印版编号", plate_key)
            old_plate = self._find_plate(order, plate_key)

            if old_plate and old_plate.get("领取状态") == "已领取":
                old_start = str(old_plate.get("起始码号"))
                old_end = str(old_plate.get("结束码号"))
                if str(plate_data.get("起始码号")) != old_start or str(plate_data.get("结束码号")) != old_end:
                    messages.append(f"印版 {plate_key} 已被包装领用，范围不得更正")
                    continue
                # 已领取范围重复提交时保持幂等，不能重复登记第二条码段。
                continue

            history: list[dict[str, Any]] = []
            previous_reasons: list[str] = []
            old_trace_id = None
            if old_plate:
                history = list(old_plate.get("correction_history", []))
                history.append({
                    "version": old_plate.get("version", order.get("version", 1) - 1),
                    "status": old_plate.get("status"),
                    "起始码号": old_plate.get("起始码号"),
                    "结束码号": old_plate.get("结束码号"),
                    "处理原因": old_plate.get("处理原因", ""),
                    "更正原因": correction_reason or old_plate.get("更正原因", ""),
                })
                previous_reasons = list(old_plate.get("历史处理原因", []))
                if old_plate.get("处理原因") and old_plate.get("处理原因") not in previous_reasons:
                    previous_reasons.append(str(old_plate.get("处理原因")))
                old_trace_id = old_plate.get("trace_code_id")
                plate_data["usage"] = old_plate.get("usage")
                plate_data["领取状态"] = old_plate.get("领取状态", "未领取")
                plate_data["packing_id"] = old_plate.get("packing_id")
                plate_data["packing_no"] = old_plate.get("packing_no")

            start_num = self._parse_code(plate_data.get("起始码号"))
            end_num = self._parse_code(plate_data.get("结束码号"))
            reason = ""
            if not str(plate_data.get("起始码号", "")).strip() or not str(plate_data.get("结束码号", "")).strip():
                status = PLATE_INDEPENDENT_ERROR
                reason = "缺少起始码号或结束码号"
            elif start_num is None or end_num is None:
                status = PLATE_INDEPENDENT_ERROR
                reason = "码号格式无法解析"
            elif start_num >= end_num:
                status = PLATE_INDEPENDENT_ERROR
                reason = "起始码号必须小于结束码号"
            elif not self._upload_succeeded(plate_data):
                status = PLATE_PENDING_VERIFICATION
                reason = str(plate_data.get("处理原因") or "上传资料失败，整组码段等待核验")
            else:
                overlap = self._find_overlap(
                    start_num, end_num, order_id=int(order["id"]), plate_key=plate_key,
                )
                if overlap:
                    status = PLATE_INDEPENDENT_ERROR
                    reason = overlap
                else:
                    status = PLATE_ACCEPTED

            new_plate = {
                **plate_data,
                "plate_id": plate_key,
                "印版编号": plate_data.get("印版编号", plate_key),
                "status": status,
                "受理状态": status,
                "处理原因": reason,
                "历史处理原因": previous_reasons,
                "correction_history": history,
                "version": order.get("version", 1),
                "trace_code_id": None,
                "领取状态": plate_data.get("领取状态", "未领取"),
            }
            new_plate.setdefault("usage", None)

            if status == PLATE_ACCEPTED:
                same_range_trace_id = old_trace_id if old_plate and self._range_text(old_plate) == self._range_text(new_plate) else None
                if same_range_trace_id and store.find(self.MODULE, int(same_range_trace_id)):
                    new_plate["trace_code_id"] = same_range_trace_id
                else:
                    if old_trace_id:
                        self._revoke_trace_code(old_trace_id, f"印版 {plate_key} 更正后替换原码段")
                    self._create_accepted_trace_code(order, new_plate)
            elif old_trace_id:
                self._revoke_trace_code(old_trace_id, f"印版 {plate_key} 未通过受理核验：{reason}")

            if old_plate:
                old_plate.clear()
                old_plate.update(new_plate)
                new_plate = old_plate
            else:
                order["plates"].append(new_plate)
            store.log_event(ORDER_TABLE, int(order["id"]), "process_plate", {
                "plate_id": plate_key, "status": status, "reason": reason,
            })
            if status != PLATE_ACCEPTED:
                messages.append(f"印版 {plate_key}：{reason}")

        self._refresh_order(order)
        self._snapshot_submission(order, action_note)
        store.log_event(ORDER_TABLE, int(order["id"]), "submit_activation_order", {
            "version": order["version"], "messages": messages,
        })
        message = "启用总单已提交" if not messages else "启用总单已提交，部分印版未受理：" + "；".join(messages)
        return order, message

    def correct_activation_plate(
        self,
        order_id: int,
        plate_key: str,
        corrected_plate: dict[str, Any],
        reason: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """更正总单中的一套印版，并保留该印版上一版处理原因。"""
        order = self._find_order(order_id=order_id)
        if order is None:
            return None, f"启用总单 {order_id} 不存在"
        plate = self._find_plate(order, plate_key)
        if plate is None:
            return None, f"印版 {plate_key} 不在启用总单 {order_id} 中"
        payload = dict(corrected_plate)
        payload["plate_id"] = plate_key
        payload.setdefault("印版编号", plate.get("印版编号", plate_key))
        if reason:
            payload["更正原因"] = reason
        return self.submit_activation_order(
            [payload], order_id=order_id, note="更正印版", correction_reason=reason,
        )

    def claim_code_range_for_packing(
        self,
        order_id: int,
        plate_key: str,
        packing_id: int,
        *,
        packing_no: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """包装工位领用一套已受理印版；每套印版最多关联一个真实包装批一次。"""
        order = self._find_order(order_id=order_id)
        if order is None:
            return None, f"启用总单 {order_id} 不存在"
        plate = self._find_plate(order, plate_key)
        if plate is None:
            return None, f"印版 {plate_key} 未在启用总单 {order_id} 中登记"
        if plate.get("status") != PLATE_ACCEPTED:
            return None, f"印版 {plate_key} 当前状态为{plate.get('status')}，不允许包装领用"
        if plate.get("领取状态") == "已领取" or plate.get("usage"):
            return None, f"印版 {plate_key} 已领取，不能重复登记真实使用"

        packing = store.find("packing", int(packing_id))
        if packing is None and packing_no:
            for row in store.rows("packing"):
                if row.get("登记编号") == packing_no:
                    packing = row
                    break
        if packing is None:
            return None, f"包装批 {packing_id} 不存在，不能领用码段"

        # 同一真实包装批不重复挂接不同码段，避免实物码被重复消耗。
        for used in store.rows(USAGE_TABLE):
            if int(used.get("packing_id", 0)) == int(packing_id):
                return None, f"包装批 {packing_id} 已领取码段，不能重复领用"

        trace_id = plate.get("trace_code_id")
        trace_row = store.find(self.MODULE, int(trace_id)) if trace_id is not None else None
        if trace_row is None or trace_row.get("status") != "已确认":
            return None, f"印版 {plate_key} 没有可用的已受理码段"
        if trace_row.get("packing_id"):
            return None, "该码段范围已被其他包装批领取"

        packing_name = packing.get("登记编号", str(packing_id))
        usage = {
            "id": self._next_id(USAGE_TABLE),
            "order_id": int(order_id),
            "order_no": order.get("order_no"),
            "plate_id": plate_key,
            "印版编号": plate.get("印版编号", plate_key),
            "trace_code_id": int(trace_id),
            "packing_id": int(packing_id),
            "packing_no": packing_name,
            "包装批编号": packing_name,
            "起始码号": plate.get("起始码号"),
            "结束码号": plate.get("结束码号"),
            "码段范围": self._range_text(plate),
            "使用次数": 1,
        }
        store.rows(USAGE_TABLE).append(usage)
        plate["领取状态"] = "已领取"
        plate["usage"] = usage
        plate["use_count"] = 1
        plate["packing_id"] = int(packing_id)
        plate["packing_no"] = packing_name
        plate["实际包装批ID"] = int(packing_id)
        trace_row["packing_id"] = int(packing_id)
        trace_row["packing_name"] = packing_name
        trace_row["packing_no"] = packing_name
        trace_row["领用状态"] = "已领取"
        if packing.get("批次号"):
            trace_row["批次号"] = packing["批次号"]

        self._refresh_order(order)
        order.setdefault("usage_history", []).append(usage)
        store.log_event(ORDER_TABLE, int(order_id), "claim_for_packing", {
            "plate_id": plate_key, "packing_id": packing_id, "trace_code_id": trace_id,
        })
        return usage, f"印版 {plate_key} 已由包装批 {packing_name} 领取"

    def list_activation_orders(self) -> list[dict[str, Any]]:
        return list(store.rows(ORDER_TABLE))

    def get_activation_order(self, order_id: int) -> dict[str, Any] | None:
        return self._find_order(order_id=order_id)

    # 兼容不同调用命名。
    def receive_code_range_for_packing(self, *args: Any, **kwargs: Any):
        return self.claim_code_range_for_packing(*args, **kwargs)

    def claim_for_packing(self, *args: Any, **kwargs: Any):
        return self.claim_code_range_for_packing(*args, **kwargs)
