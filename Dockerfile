FROM python:3.11

WORKDIR /app

# Install dependencies
COPY ./readable_service/requirements.txt .
RUN pip install -r requirements.txt

# Copy source code
COPY ./readable_service/api.py .
COPY ./readable_service/readability.py .

# Run the app
CMD ["python", "api.py"]
