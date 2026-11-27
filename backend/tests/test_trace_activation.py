"""启用总单与包装工位码段领用的领域规则测试。"""
from __future__ import annotations

import unittest

from app.services import service_for
from app.services.trace_code import (
    PLATE_ACCEPTED,
    PLATE_INDEPENDENT_ERROR,
    PLATE_PENDING_VERIFICATION,
    USAGE_TABLE,
)
from app.store import store


class TestTraceActivationOrder(unittest.TestCase):
    def setUp(self):
        # 每个用例使用独立的内存仓库，避免种子码段影响重叠判断。
        store._tables["trace_code"] = []
        store._tables["trace_activation_order"] = []
        store._tables["trace_activation_usage"] = []
        self.service = service_for("trace_code")
        self.packing = service_for("packing")
        packing, errors = self.packing.create_entry({
            "包装形式": "袋装",
            "净含量": "100",
            "登记编号": "PACK-TCA-001",
        })
        self.assertIsNotNone(packing, errors)
        self.packing_id = int(packing["id"])

    def _plates(self):
        return [
            {"印版编号": "P1", "起始码号": "TRACE-1001", "结束码号": "TRACE-1100",
             "资料上传成功": True},
            {"印版编号": "P2", "起始码号": "TRACE-2001", "结束码号": "TRACE-2100",
             "资料上传成功": True},
            {"印版编号": "P3", "起始码号": "TRACE-1050", "结束码号": "TRACE-1090",
             "资料上传成功": True},
        ]

    def test_order_accepts_each_plate_independently_and_packing_claims_first(self):
        order, message = self.service.submit_activation_order(self._plates(), order_no="TCO-T-001")
        self.assertIsNotNone(order, message)
        statuses = {p["印版编号"]: p["status"] for p in order["plates"]}
        self.assertEqual(statuses["P1"], PLATE_ACCEPTED)
        self.assertEqual(statuses["P2"], PLATE_ACCEPTED)
        self.assertEqual(statuses["P3"], PLATE_INDEPENDENT_ERROR)
        self.assertEqual(order["status"], "办理中")

        p1 = next(p for p in order["plates"] if p["印版编号"] == "P1")
        trace = store.find("trace_code", int(p1["trace_code_id"]))
        self.assertEqual(trace["status"], "已确认")
        self.assertEqual(trace["起始码号"], "TRACE-1001")
        self.assertEqual(trace["packing_id"], None)

        available = [p for p in order["plates"] if p["status"] == PLATE_ACCEPTED]
        self.assertEqual({p["印版编号"] for p in available}, {"P1", "P2"})

        usage, claim_msg = self.service.claim_code_range_for_packing(
            order["id"], "P1", self.packing_id,
        )
        self.assertIsNotNone(usage, claim_msg)
        self.assertEqual(usage["使用次数"], 1)
        self.assertEqual(usage["packing_id"], self.packing_id)
        self.assertEqual(trace["packing_id"], self.packing_id)
        self.assertEqual(len(store.rows(USAGE_TABLE)), 1)
        self.assertEqual(order["首次实际使用范围"][0]["印版编号"], "P1")
        self.assertEqual(order["实际使用范围"][0]["码段范围"], "TRACE-1001-TRACE-1100")

        # 同一项再次领取必须被拒绝，不能重复登记或重复消耗。
        again, _ = self.service.claim_code_range_for_packing(order["id"], "P1", self.packing_id)
        self.assertIsNone(again)
        self.assertEqual(len(store.rows(USAGE_TABLE)), 1)

    def test_upload_failed_plate_is_group_pending_and_cannot_be_consumed(self):
        plates = [
            {"印版编号": "P1", "起始码号": "TRACE-3001", "结束码号": "TRACE-3100",
             "资料上传成功": True},
            {"印版编号": "P2", "起始码号": "TRACE-4001", "结束码号": "TRACE-4100",
             "资料上传成功": False, "处理原因": "包装资料未上传完成"},
        ]
        order, _ = self.service.submit_activation_order(plates, order_no="TCO-T-002")
        p1, p2 = order["plates"]
        self.assertEqual(p1["status"], PLATE_ACCEPTED)
        self.assertEqual(p2["status"], PLATE_PENDING_VERIFICATION)

        usage, _ = self.service.claim_code_range_for_packing(order["id"], "P2", self.packing_id)
        self.assertIsNone(usage)
        self.assertEqual(store.rows(USAGE_TABLE), [])

        # 原总单可继续处理未办结印版。
        corrected, _ = self.service.submit_activation_order([
            {"印版编号": "P2", "起始码号": "TRACE-4001", "结束码号": "TRACE-4100",
             "资料上传成功": True},
        ], order_id=order["id"])
        self.assertEqual(len(corrected["plates"]), 2)
        p2_after = next(p for p in corrected["plates"] if p["印版编号"] == "P2")
        self.assertEqual(p2_after["status"], PLATE_ACCEPTED)

    def test_correction_keeps_previous_reason_and_records_corrected_actual_range(self):
        order, _ = self.service.submit_activation_order(self._plates(), order_no="TCO-T-003")
        p1 = next(p for p in order["plates"] if p["印版编号"] == "P1")
        self.service.claim_code_range_for_packing(order["id"], "P1", self.packing_id)

        p3 = next(p for p in order["plates"] if p["印版编号"] == "P3")
        first_reason = p3["处理原因"]
        corrected, msg = self.service.correct_activation_plate(order["id"], "P3", {
            "印版编号": "P3",
            "起始码号": "TRACE-5001",
            "结束码号": "TRACE-5100",
            "资料上传成功": True,
        }, reason="更正重叠号码")
        self.assertIsNotNone(corrected, msg)
        p3_after = next(p for p in corrected["plates"] if p["印版编号"] == "P3")
        self.assertEqual(p3_after["status"], PLATE_ACCEPTED)
        self.assertIn(first_reason, p3_after["历史处理原因"])
        self.assertEqual(p3_after["correction_history"][0]["处理原因"], first_reason)

        # 已被包装先领的 P1 仍保留一次真实使用，不被更正重复登记。
        self.assertEqual(len(store.rows(USAGE_TABLE)), 1)
        self.assertEqual(corrected["首次实际使用范围"][0]["印版编号"], "P1")
        self.assertEqual(corrected["修正后实际使用范围"][0]["印版编号"], "P1")

        second_packing, errors = self.packing.create_entry({
            "包装形式": "罐装",
            "净含量": "50",
            "登记编号": "PACK-TCA-002",
        })
        self.assertIsNotNone(second_packing, errors)
        usage, _ = self.service.claim_code_range_for_packing(
            order["id"], "P3", int(second_packing["id"]),
        )
        self.assertIsNotNone(usage)
        corrected = self.service.get_activation_order(order["id"])
        used_ids = {item["印版编号"] for item in corrected["实际使用范围"]}
        self.assertEqual(used_ids, {"P1", "P3"})
        self.assertEqual(len(corrected["首次实际使用范围"]), 1)
        self.assertEqual(len(corrected["修正后实际使用范围"]), 2)


if __name__ == "__main__":
    unittest.main()
