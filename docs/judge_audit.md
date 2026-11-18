# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (judge replay, FAIL = lớp dương).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (tp 24, fp 4, fn 6, tn 66) | **dùng** |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** κ và R (tp 9, fp 0, fn 21, tn 70) | **loại** |

Tỉ lệ fail (Rogan-Gladen): tone quan sát 0.28 → hiệu chỉnh 0.30; helpful quan sát 0.09 → hiệu chỉnh 0.30. Helpful judge báo tỉ lệ lỗi thấp hơn thực tế **hơn 3 lần**.

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em", "nha" quá suồng sã với khách khiếu nại. Rubric thêm: *xưng hô phải là "LogiX" + "anh/chị"; "em/bạn/nha/nhé" ⇒ FAIL.* |
| 2 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge bị đánh lừa bởi "Dạ, vui lòng". Rubric thêm: *câu mệnh lệnh cấm khách liên hệ ("không cần nhắn thêm") ⇒ FAIL dù có từ lịch sự.* |
| 3 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric sửa: *ngắn, đủ thông tin, có kính ngữ là PASS; xin lỗi không bắt buộc khi đã giải quyết xong.* |
| 4 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Từ "refund" được CS LogiX cho phép. Rubric thêm danh sách từ mượn được phép (refund, ship, voucher). |
| 5 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Ghi chú CSV: người đọc nhầm ticket → **sửa nhãn người** thành FAIL, không sửa rubric. Cho thấy nhãn người cũng cần kiểm tra chéo. |
| 6 | H-070 "…hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric thêm: *emoji cười trong ngữ cảnh khiếu nại ⇒ FAIL.* |
| 7 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống — thực chất là lỗi nội dung (FM-08-like), không phải giọng điệu → chuyển sang grader code đọc ledger, rubric tone ghi rõ *không chấm số tiền/cam kết*. |
| 8 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Helpful judge **không thấy ledger** nên không thể biết số sai. Đây là FM-08 → chấm bằng code `reply_amount_matches_ledger`, không dùng judge. |
| 9 | HL-016 / HL-053 reply dài, xin lỗi 2 lần, số tiền sai ledger | PASS | FAIL | Người | Thiên vị độ dài/lời xin lỗi: reply càng dài judge càng cho PASS. Không sửa được bằng rubric vì judge thiếu dữ liệu ledger. |
| 10 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nêu số tiền/kết quả cụ thể nhưng judge vẫn cho "helpful". Rubric helpful phải yêu cầu *nêu kết quả + số tiền + thời gian* — nhưng phần số tiền vẫn phải kiểm bằng code. |

## Kết luận
- **tone_ok: dùng được** (κ 0.757 ≥ 0.6, P 0.857 ≥ 0.8, R 0.80 ≥ 0.7). Lỗi còn lại của judge thiên về bỏ sót xưng hô suồng sã (fn = 6) và phạt nhầm reply ngắn/từ mượn (fp = 4) → đã đề xuất sửa rubric ở case 1–4, 6.
- **helpful: loại, không được làm gate.** Ma trận nhầm lẫn: tp 9, **fn 21**, fp 0, tn 70 → recall 0.30, κ 0.375. Judge bỏ sót 21/30 reply có vấn đề; 17/21 trong số đó là reply **nêu số tiền khác ledger** (ghi chú CSV "ledger ghi …"). Judge chỉ đọc chữ, không có ledger, nên về cấu trúc nó *không thể* bắt lỗi này; precision 1.0 chỉ vì nó gần như luôn nói PASS. Dùng nó làm gate sẽ cho qua đúng lỗi nguy hiểm nhất (nói sai tiền với khách). Thay thế: grader code `ReplyAmountMatchesLedger` (metric `reply_amount_matches_ledger`, blocking).
- Nguyên tắc rút ra: **tiền và approval luôn chấm bằng code**; judge chỉ dùng cho tiêu chí chủ quan (giọng điệu) sau khi qua FLOORS.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng/tiêu chí); cần nhãn người mới để có held-out thật, và cần 2 người gán nhãn độc lập (case 5 cho thấy nhãn người cũng sai).
