# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: `seeded_regression C-002@11`

Output (rút gọn):
```
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
   1 handoff            {"request_id": "REQ-C-002", ... "allowed_tools": ["lookup_order", ...]}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "delay_days": 2, ...}}}
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"]}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, report `E-seeded_regression-20261118-0a46` (eval set `0a46cc2a69dd`); cùng lỗi xuất hiện ở cả 5 seed của E-002, và ở `swarm` C-002@55 trong baseline `E-swarm-20261118-0a46` |
| Triệu chứng | Grader fail: `pass_rate` (status resolved ≠ denied), `refund_amount_correct` (ledger 20.000 ≠ label 0), `db_fact_kept` (1 override event). Reply nói "đã hoàn 20.000đ" và ledger **cũng** ghi 20.000 — reply khớp ledger nên FM-08 không fire; lỗi nằm ở chỗ khoản hoàn lẽ ra không được tồn tại. |
| Bước sai đầu tiên | Event **#3 `model_override`** `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | #1 handoff đúng contract (đúng claim, tool chỉ đọc); #2 investigator đọc đúng đơn O-202 của P-100 với `delay_days = 2`. Từ #3 agent thay số của DB bằng số khách tự khai trong ticket ("giao trễ 5 ngày"), nên #4 quote tính theo 5 ngày → entitled 20.000; mọi bước sau chỉ là hệ quả. |
| Failure mode | **FM-03 ticket_trust** (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: không có `model_override`; #3 quote `{"amount_vnd": 0, "reason": "no_entitlement"}` → `denied`, ledger 0, mọi grader PASS. Khác biệt duy nhất là bước #3. |
| Regression test | `src/tests/test_lab9_trace_case.py::test_trace_case_c002_ticket_trust_is_caught` (assert `model_override` đứng trước `quote`, `db_fact_kept`/`refund_amount_correct`/`pass_rate` = fail) và `::test_trace_case_c002_fixed_is_clean` (cùng claim@seed trên `fixed` sạch). Đã chạy: fail-detect trên variant lỗi, pass trên `fixed` (`pytest -m student -k lab9` 14 passed). Thêm `::test_trace_case_c008_misreport_is_caught_only_by_fm08_metric` cho FM-08 (C-008@11: lab8 PASS nhưng reply 35.000đ ≠ ledger 20.000). Item E-002 trong eval set có `provenance.from_trace` trỏ về trace này. |
| Chưa chắc chắn | Trace không cho biết *vì sao* model tin ticket (MockLLM là luật cứng theo công tắc/seed); với LLM thật, nguyên nhân có thể là prompt hay ngữ cảnh. Trace cũng không ghi kết quả gọi `issue_refund` của host, nên phải đọc ledger để biết tiền đã đi. `db_fact_kept` chỉ bắt được override **có để lại event**; biến thể `quiet_override` (tin ticket nhưng không ghi event) sẽ chỉ bị bắt qua `refund_amount_correct`/`pass_rate`. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
