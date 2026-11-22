FROM python:3.12-slim

WORKDIR /app

COPY cloud_saas/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY cloud_saas /app/cloud_saas
COPY core/div_engines_view.py /app/core/div_engines_view.py
COPY research/div_master/especialistas/modulo.py /app/research/div_master/especialistas/modulo.py
RUN touch /app/core/__init__.py

ENV PYTHONUNBUFFERED=1
ENV MW_ENV=production
ENV PORT=8090
EXPOSE 8090

CMD ["sh", "-c", "uvicorn cloud_saas.app:app --host 0.0.0.0 --port ${PORT:-8090}"]
