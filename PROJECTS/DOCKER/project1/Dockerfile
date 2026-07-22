FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY etl/ ./etl/
COPY data/ ./data/

RUN useradd --create-home appuser
USER appuser

CMD ["python","-m" ,"etl.main"]


