# Phân tích memory system — Bước 8

## Trạng thái kết quả

Đã chạy lại test và benchmark trên mã hiện tại ngày 03/10/2026. Pytest: **24 passed trong 0,72 giây**, không có test fail. Kết quả được lưu trong `test-results.txt` và `benchmark-results.txt`. Kiểm chứng này chạy offline; chưa gọi API để kiểm chứng chế độ live.

## Standard Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 3470 | 14787 | 0.0% | 0.0% | 0 | 0 |
| Advanced | 3812 | 33454 | 92.9% | 95.0% | 359 | 0 |

## Long-Context Stress Benchmark

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 2790 | 22587 | 0.0% | 0.0% | 0 | 0 |
| Advanced | 2852 | 18797 | 100.0% | 100.0% | 353 | 1 |

## Nhận xét từ kết quả thực tế

Trong Standard Benchmark, Advanced đạt recall **92,9%**, quality heuristic **95,0%**; Baseline đạt 0% cho cả hai chỉ số. Prompt tokens tăng từ 14.787 lên 33.454 (**126,2%**), trong khi không có compaction. Agent tokens tăng từ 3.470 lên 3.812 (khoảng **9,9%**). Memory growth là **359 bytes**. Advanced nhớ qua phiên tốt hơn nhưng mang thêm chi phí hồ sơ và hướng dẫn ở các thread ngắn.

Trong Long-Context Stress Benchmark, Advanced đạt recall **100,0%** và quality heuristic **100,0%** cho các câu hỏi của bộ dữ liệu. Advanced compact **1 lần**, giảm prompt tokens từ 22.587 xuống 18.797: giảm **3.790 token**, khoảng **16,8%**. Agent tokens tăng từ 2.790 lên 2.852 (khoảng **2,2%**), memory growth là **353 bytes**. Lợi ích compact nằm ở giảm lịch sử phải xử lý lại, không phải giảm token của lượt mới.

Recall standard chưa đạt 100%; cần giữ giới hạn này trong kết luận. Quality là tỷ lệ chuỗi kỳ vọng xuất hiện, nên 100% ở stress không chứng minh chất lượng ngữ nghĩa hoàn hảo hoặc khả năng tổng quát ngoài dataset.

## Kiểm chứng lỗi đã sửa

Lỗi cũ trích `nghề hiện tại` trong câu hỏi thành fact đã được sửa bằng cách giới hạn mẫu khai báo nghề và bỏ qua yêu cầu nhắc lại/tóm tắt. Test hồi quy kiểm tra recall không thay đổi hồ sơ và vẫn nhận khai báo nghề thật đã pass. Khi chạy bộ test mới, pytest phát hiện tên tham số `request` dành riêng; tham số đã được đổi thành `recall_message` và toàn bộ bộ test đã chạy lại thành công.

24 test pass bao gồm thao tác User.md, compact trigger, recall qua instance mới, giảm prompt load, cách ly người dùng, cập nhật fact, chuẩn hoá provider và các trường hợp hồi quy extraction. Các test không gọi API live và không bảo đảm mọi cách diễn đạt ngoài dữ liệu đều được xử lý đúng.

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

Hai bảng và log pytest đã được cập nhật sau khi sửa lỗi. Nếu thay đổi mã hoặc cấu hình, chạy lại các lệnh trên để đồng bộ số liệu báo cáo.

## Rà soát bài nộp (bước 1–8, không gồm bước 9)

| Bước | Trạng thái qua đọc mã | Việc còn cần làm |
|---|---|---|
| 1. Cấu trúc và môi trường | Có tài liệu và dữ liệu | Đã có benchmark và log pytest |
| 2. Cấu hình | Có LabConfig, load_config, 6 provider | Chưa kiểm chứng runtime; cấu hình provider không đồng nghĩa model live đã hoạt động |
| 3. Memory layer | Có estimator, User.md, extraction, summary, compact | Đã sửa; test hồi quy extraction đã pass |
| 4. Baseline | Có offline, bộ đếm, nhánh live | Đã triển khai provider; chưa kiểm chứng bằng API thật |
| 5. Advanced | Có ba lớp memory và công cụ profile cho live | Đã bổ sung câu hỏi thú nuôi/tóm tắt; chưa kiểm chứng live; compact live dùng manager chung |
| 6. Benchmark | Có hai bộ và đủ 6 chỉ số | Đã chạy và lưu hai bảng mới; chất lượng là heuristic |
| 7. Test | Có test cho 4 hành vi cốt lõi và một số trường hợp bổ sung | 24 test pass, không còn fail trong bộ test hiện tại |
| 8. Phân tích | Đã có lập luận và giới hạn trong tài liệu này | Đã cập nhật benchmark và log test; kết luận có ghi rõ giới hạn |

`src/model_provider.py` đã triển khai `normalize_provider()` và `build_chat_model()` cho sáu provider. Import SDK chỉ xảy ra khi khởi tạo live model, nên offline không cần API key. Chưa gọi API thật để kiểm chứng; model và endpoint phải tương thích với tài khoản của người chạy. Test chuẩn hoá provider và test hồi quy recall đều pass. Không triển khai các bonus bước 9.

Trước khi nộp, đưa `Analysis.md`, mã nguồn và kết quả benchmark vào bộ bài nộp; không đưa `.env`, `.venv/` hoặc hồ sơ cá nhân trong `state/`. Các TODO được giữ theo yêu cầu, không dùng việc còn comment TODO làm bằng chứng rằng hàm chưa hoàn thiện; kiểm tra phần thân hàm và kết quả chạy.
