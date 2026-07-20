# Chỉ đóng gói TRANG TẢI VỀ, không đóng gói autoclicker.py.
#
# autoclicker.py là app desktop cần màn hình và chuột thật -> không thể chạy
# trong container. Cố cài tk-dev/Xvfb cũng vô ích vì nó không mở cổng HTTP nào,
# và nếu có click thì cũng click lên màn hình ảo của server chứ không phải máy
# người dùng.
#
# Ảnh này không cài thư viện ngoài nào cả — app.py dùng thuần stdlib.

FROM python:3.12-slim

WORKDIR /app

COPY web/ ./web/
COPY app.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
