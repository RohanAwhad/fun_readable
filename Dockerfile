FROM python:3.9-alpine

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source code
COPY api.py .
COPY readability.py .

# Run the app
CMD ["python", "api.py"]
