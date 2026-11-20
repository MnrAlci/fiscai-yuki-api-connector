# Optional: run the MCP server in a container. Not required; the plugin normally runs directly with Python.
# The key is passed at run time, never baked into the image:
#   docker run -i --rm -e YUKI_ACCESS_KEY fiscai-yuki-api-connector
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
RUN useradd --create-home app
USER app
ENTRYPOINT ["python", "server/run_connector.py", "serve"]
