FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY fixtures ./fixtures

RUN mkdir -p /app/uploads

EXPOSE 3004

CMD ["python", "-m", "app"]
