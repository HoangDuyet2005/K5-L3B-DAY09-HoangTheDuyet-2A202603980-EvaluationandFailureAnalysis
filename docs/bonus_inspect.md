# Bonus: port grader sang Inspect AI và so khớp với pydantic-evals

## Làm gì
- **Framework:** [Inspect AI](https://inspect.aisi.org.uk/) `inspect-ai==0.3.291` (`src/requirements-bonus.txt`; CI không cài, test bonus tự skip).
- **Grader được port (4):** `approval_bypass`, `secret_leak`, `refund_amount_correct`, `reply_amount_matches_ledger` (FM-08). Mỗi cái là một `@scorer(metrics=[mean()])` của Inspect, **viết lại độc lập** từ định nghĩa metric trong `lab9/bonus_inspect.py`, không gọi `lab9.graders`; nếu gọi lại thì phép so khớp chỉ chứng minh một hàm bằng chính nó.
- **Cách so khớp công bằng:** agent chạy **một lần** cho mỗi `(item, seed)`; cùng một trial được chấm bởi pydantic-evals (`Dataset` + `lab9.graders`) và Inspect AI (`Task` + `MemoryDataset` + scorer). Lệch nào cũng là lệch grader, không phải nhiễu agent.
- **Chạy offline:** Inspect cần một model để khởi động eval; dùng `mockllm/model` có sẵn, solver `replay_trial` chỉ trả lại state (trial đã được Lab 8 shape tạo trước), nên không gọi model, không cần API key.
- **Đủ hai nhánh:** `swarm`/`fixed`/`seeded_regression` không bao giờ làm lộ secret hay ghi dòng ledger lạ, nên chỉ so được nhánh "không vi phạm". Bổ sung 4 shape thăm dò một công tắc lỗi (`leaky_trace`, `sibling_refund`, `misreport`, `ignore_denied`, đăng ký trong bộ nhớ như `lab9.variants`, không sửa `lab8/` hay `variants.py`) để mọi metric đều có ca fail.

```bash
cd src
pip install -r requirements-bonus.txt
python -m lab9.bonus_inspect                       # v1: swarm, fixed, seeded_regression + 4 probe
python -m lab9.bonus_inspect --spec config/metric_spec_v2.yaml \
  --shapes swarm,fixed,honest_refactor,slice_regression,flaky_regression --out reports/bonus_inspect_compare_v2.json
python -m pytest -q -m student -o addopts= tests/test_lab9_bonus_inspect.py
```

## Kết quả (eval set v1 `0a46cc2a69dd`, seeds 11/22/33/44/55) — `src/reports/bonus_inspect_compare.json`

Giá trị: safety = số vi phạm (phải 0), capability = tỉ lệ đạt.

| Shape | approval_bypass (pyd / Inspect) | secret_leak | refund_amount_correct | reply_amount_matches_ledger | Khớp từng trial |
|---|---|---|---|---|---|
| swarm | 0 / 0 | 0 / 0 | 0.9857 / 0.9857 | 1.0 / 1.0 | 70/70 × 4 |
| fixed | 0 / 0 | 0 / 0 | 1.0 / 1.0 | 1.0 / 1.0 | 70/70 × 4 |
| seeded_regression | 0 / 0 | 0 / 0 | 0.8571 / 0.8571 | 0.7857 / 0.7857 | 70/70 × 4 |
| probe_leaky_trace | 0 / 0 | **70 / 70** | 1.0 / 1.0 | 1.0 / 1.0 | 70/70 × 4 |
| probe_sibling_refund | **20 / 20** | 0 / 0 | 0.7143 / 0.7143 | 1.0 / 1.0 | 70/70 × 4 |
| probe_misreport | 0 / 0 | 0 / 0 | 1.0 / 1.0 | **0.8571 / 0.8571** | 70/70 × 4 |
| probe_ignore_denied | 0 / 0 | 0 / 0 | 1.0 / 1.0 | **0.8571 / 0.8571** | 70/70 × 4 |

Eval set v2 (`7e68394b7267`, 28 item × 5 seed) trên `swarm, fixed, honest_refactor, slice_regression, flaky_regression`: **700/700 trial khớp trên cả 4 metric** (`src/reports/bonus_inspect_compare_v2.json`).

**Tổng: 1.190 trial × 4 metric, 0 lệch** → `exit 0 — Inspect AI and pydantic-evals agree on every trial`.

## Nhận xét
- Hai framework cho **cùng quyết định trên từng trial**, nên số liệu gate (Core/v2) không phụ thuộc harness; có thể chuyển sang Inspect (log `.eval`, viewer `inspect view`) mà không đổi kết quả.
- Khác biệt khi port: pydantic-evals trả `EvaluationReason(value=bool)` và aggregate do `lab9.eval` tự làm; Inspect trả `Score(value=float)` + metric `mean()`, nên safety được quy về 1.0 = vi phạm và đếm lại bằng tổng. Inspect bắt buộc có model và solver ngay cả khi chỉ chấm trace có sẵn: dùng `mockllm/model` + solver pass-through.
- Giới hạn: phép so khớp chứng minh hai cài đặt **nhất quán**, không chứng minh định nghĩa metric đúng; ví dụ cả hai cùng bỏ sót số tiền viết bằng chữ (cùng một regex). `test_amount_parsers_agree` khoá hai parser phải trả cùng kết quả.
