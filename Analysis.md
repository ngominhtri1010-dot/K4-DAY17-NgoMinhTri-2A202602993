# Phân tích memory system — Bước 8

## Trạng thái kết quả

Số liệu dưới đây lấy từ `benchmark-results.txt` và `test-results.txt` do người làm bài chạy lại. Trợ lý chỉ đọc kết quả, không chạy lại test hoặc benchmark. Pytest thu thập 18 test: **17 passed, 1 failed** trong 0,69 giây. Bài chưa đạt trạng thái toàn bộ test pass.

## Standard Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 3460 | 14787 | 0.0% | 0.0% | 0 | 0 |
| Advanced | 3812 | 33587 | 89.3% | 91.8% | 366 | 0 |

## Long-Context Stress Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 2775 | 22587 | 0.0% | 0.0% | 0 | 0 |
| Advanced | 2820 | 18754 | 50.0% | 58.3% | 340 | 1 |

## Nhận xét từ kết quả thực tế

Trong Standard Benchmark, Advanced đạt recall **89,3%** và quality heuristic **91,8%**, so với Baseline đều 0%. Prompt tokens tăng từ 14.787 lên 33.587, tương đương **127,1%**; không có compaction. Agent tokens tăng từ 3.460 lên 3.812 (khoảng 10,2%). Đây là chi phí mang thêm hồ sơ và hướng dẫn khi lịch sử từng thread còn ngắn. Memory growth của Advanced là **366 bytes**.

Trong Long-Context Stress Benchmark, Advanced compact **1 lần** và giảm prompt tokens từ 22.587 xuống 18.754: tiết kiệm **3.833 token**, khoảng **17,0%**. Agent tokens vẫn tăng nhẹ từ 2.775 lên 2.820 (khoảng 1,6%). Recall đạt **50,0%**, quality heuristic **58,3%**, memory growth **340 bytes**. Compact đã giảm tải prompt trong lần đo này, nhưng recall chưa đầy đủ; không thể kết luận chất lượng ngữ nghĩa cao chỉ từ việc giảm token.

So với lần đo trước, recall standard tăng từ 50,0% lên 89,3% và mức giảm prompt stress tăng từ khoảng 10,7% lên 17,0%. Đây là quan sát giữa hai phiên bản, không chứng minh riêng từng thay đổi là nguyên nhân của toàn bộ mức cải thiện.

## Kết quả test và lỗi còn lại

Test thất bại là `test_profile_recall_matches_dataset_fields`. Đáp án có `Nghề nghiệp: hiện tại` thay vì `MLOps engineer`. Qua đối chiếu mã, regex nghề nghiệp có nhánh `nghề` quá rộng, khớp cụm `nghề hiện tại` trong yêu cầu recall; `_prepare_turn()` lưu giá trị này trước khi trả lời, làm ghi đè nghề đã biết. Cần sửa extraction để yêu cầu recall không được xem là khai báo nghề nghiệp, rồi chạy lại test và benchmark. Đây là sửa lỗi chức năng cơ bản, không phải bonus bước 9.

17 test còn lại pass, bao gồm bốn hành vi cốt lõi: thao tác User.md, compact trigger, cross-session recall và giảm prompt load. Tuy nhiên, chúng không thay thế test đang fail hoặc kiểm chứng toàn bộ câu recall trong dataset. Benchmark tổng hợp chưa liệt kê từng câu sai, nên chưa xác định đầy đủ nguyên nhân recall stress chỉ đạt 50%.

## Vì sao Advanced có khả năng recall tốt hơn Baseline

Baseline chỉ giữ message trong `sessions` theo `thread_id`. Nó có thể đọc lại thông tin trong cùng thread, nhưng thread mới không có lịch sử cũ. Advanced trích fact từ message và lưu vào `state/profiles/<user>/User.md`; khi đổi thread hoặc tạo một instance agent mới dùng cùng thư mục state, agent vẫn đọc được hồ sơ. `upsert_fact()` thay giá trị cũ khi cùng field được cập nhật, chẳng hạn nơi ở chuyển từ Huế sang Đà Nẵng.

Trong benchmark, mỗi câu hỏi recall dùng thread mới. Các câu hỏi được đánh giá ngay sau từng cuộc hội thoại để correction trong cuộc hội thoại sau không làm sai kỳ vọng của cuộc hội thoại trước. Recall của Advanced còn phụ thuộc vào khả năng trích fact và nhận diện câu hỏi, nên chưa thể khẳng định đạt 100%.

## Vì sao Advanced có thể tốn hơn ở hội thoại ngắn

Advanced mang thêm hướng dẫn hệ thống, hồ sơ người dùng và summary vào ngữ cảnh. Khi lịch sử còn ngắn, phần bổ sung này có thể lớn hơn phần lịch sử tiết kiệm được. Baseline chưa cần nén và chỉ giữ message nên prompt có thể nhỏ hơn. Lưu memory cũng có thêm chi phí đọc/ghi tệp.

`Agent tokens only` hiện được tính bằng tổng token ước lượng của input người dùng và output trợ lý ở mỗi lượt, bao gồm lượt recall. Chỉ số này không phản ánh toàn bộ lịch sử được gửi lại. Câu trả lời offline của hai agent có độ dài khác nhau nên bản thân câu trả lời cũng ảnh hưởng số token; không nên quy mọi chênh lệch cho compact.

## Vì sao compact giúp ở hội thoại dài

Baseline xử lý lại toàn bộ lịch sử mỗi lượt. Với độ dài message gần tương đương, tổng prompt tokens có xu hướng tăng theo bậc hai của số lượt. Advanced chuyển phần cũ thành summary có giới hạn số mục và độ dài, rồi giữ một số message gần nhất nguyên văn. Khi lịch sử dài, lượng ngữ cảnh xử lý lại có thể giảm đáng kể.

Compact chủ yếu tác động tới `Prompt tokens processed`, không trực tiếp làm giảm token của message mới hay câu trả lời. Ngưỡng compact là điều kiện kích hoạt, không phải giới hạn cứng: nếu các message phải giữ lại rất dài, ngữ cảnh sau compact vẫn có thể vượt ngưỡng. Summary heuristic cũng có thể làm mất chi tiết, nên số compactions lớn không tự chứng minh chất lượng tốt.

## Memory growth và rủi ro

`Memory growth (bytes)` là chênh lệch kích thước các file `User.md` của những user trong dataset trước và sau benchmark. Baseline không có file hồ sơ nên chỉ số này bằng 0. Advanced có thể tăng kích thước khi thêm field mới hoặc thay giá trị bằng nội dung dài hơn; khi thay bằng giá trị ngắn hơn, kích thước cũng có thể giảm. Compact lịch sử không thu nhỏ `User.md` vì đây là hai lớp memory riêng.

Regex có thể bỏ sót hoặc lưu sai fact, đặc biệt với câu phủ định, câu nhiều mệnh đề và cách diễn đạt mới. Lưu sai fact bền vững có thể làm sai nhiều phiên sau. Summary chỉ giữ một số ý nên không bảo đảm recall toàn bộ tin tức hay chi tiết kỹ thuật. Hồ sơ hiện được lưu dạng văn bản rõ; cần tránh đưa dữ liệu cá nhân thật vào bản nộp.

## Cách đo và bổ sung số liệu

Chạy từ root repo bằng môi trường Python đã cài pytest:

```bash
PYTHONPATH=src python -m pytest src/test_agents.py -v > test-results.txt 2>&1
python src/benchmark.py > benchmark-results.txt
```

Benchmark chạy offline, không gọi model hay judge API. Mỗi bộ dữ liệu có agent mới và thư mục state tạm riêng; thư mục tạm được xoá sau khi đo. `Response quality` chỉ là tỷ lệ chuỗi kỳ vọng xuất hiện trong đáp án, không phải đánh giá ngữ nghĩa của model judge. Recall cho mỗi câu hỏi là 0 nếu không khớp, 0.5 nếu khớp một phần, và 1 nếu khớp toàn bộ.

Đã có hai bảng benchmark và log pytest. Sau khi sửa lỗi extraction, chạy lại các lệnh trên và thay số liệu trong báo cáo bằng kết quả mới. Không coi số liệu hiện tại là kết quả của bản sửa trong tương lai.

## Rà soát bài nộp (bước 1–8, không gồm bước 9)

| Bước | Trạng thái qua đọc mã | Việc còn cần làm |
|---|---|---|
| 1. Cấu trúc và môi trường | Có tài liệu và dữ liệu | Đã có benchmark và log pytest |
| 2. Cấu hình | Có LabConfig, load_config, 6 provider | Chưa kiểm chứng runtime; cấu hình provider không đồng nghĩa model live đã hoạt động |
| 3. Memory layer | Có estimator, User.md, extraction, summary, compact | Còn lỗi trích nghề từ yêu cầu recall; cần sửa và kiểm chứng |
| 4. Baseline | Có offline, bộ đếm, nhánh live | Đã triển khai provider; chưa kiểm chứng bằng API thật |
| 5. Advanced | Có ba lớp memory và công cụ profile cho live | Đã bổ sung câu hỏi thú nuôi/tóm tắt; chưa kiểm chứng live; compact live dùng manager chung |
| 6. Benchmark | Có hai bộ và đủ 6 chỉ số | Đã có hai bảng mới; chạy lại sau khi sửa lỗi; chất lượng là heuristic |
| 7. Test | Có test cho 4 hành vi cốt lõi và một số trường hợp bổ sung | 17 pass, 1 fail; cần sửa test hồi quy đang fail |
| 8. Phân tích | Đã có lập luận và giới hạn trong tài liệu này | Đã cập nhật benchmark và log test; kết luận có ghi rõ giới hạn |

`src/model_provider.py` đã triển khai `normalize_provider()` và `build_chat_model()` cho sáu provider. Import SDK chỉ xảy ra khi khởi tạo live model, nên offline không cần API key. Chưa gọi API thật để kiểm chứng; model và endpoint phải tương thích với tài khoản của người chạy. Test chuẩn hoá provider đã pass; test hồi quy recall còn 1 lỗi như mô tả ở trên. Không triển khai các bonus bước 9.

Trước khi nộp, đưa `Analysis.md`, mã nguồn và kết quả benchmark vào bộ bài nộp; không đưa `.env`, `.venv/` hoặc hồ sơ cá nhân trong `state/`. Các TODO được giữ theo yêu cầu, không dùng việc còn comment TODO làm bằng chứng rằng hàm chưa hoàn thiện; kiểm tra phần thân hàm và kết quả chạy.
