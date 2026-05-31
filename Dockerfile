FROM python:3.12-slim

# System dependencies needed by chromadb and crewai
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first — Docker caches this layer
# so rebuilds are fast if only code changes
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools==69.5.1
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full project
COPY . .

# Create directories that must exist at runtime
RUN mkdir -p /app/memory/chroma_db /app/data

# Expose Streamlit port
EXPOSE 8501

# Health check — confirms Streamlit is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Streamlit
CMD ["streamlit", "run", "ui/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]