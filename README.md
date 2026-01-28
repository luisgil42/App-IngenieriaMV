# MV Ingeniería - Plataforma

## Desarrollo local
1) Crear venv e instalar:
   pip install -r requirements.txt

2) Variables (ejemplo):
   export DEBUG=1
   export SECRET_KEY="dev-secret"
   export ALLOWED_HOSTS="127.0.0.1,localhost"
   export DATABASE_URL="sqlite:///db.sqlite3"

3) Migraciones y run:
   python manage.py migrate
   python manage.py createsuperuser  (NO usamos admin, pero sirve para crear usuario inicial)
   python manage.py runserver

## Render (producción)
Configurar env vars:
- SECRET_KEY
- DEBUG=0
- ALLOWED_HOSTS=tu-app.onrender.com
- CSRF_TRUSTED_ORIGINS=https://tu-app.onrender.com
- DATABASE_URL (Postgres de Render)

Wasabi (opcional):
- WASABI_BUCKET_NAME
- WASABI_ACCESS_KEY_ID
- WASABI_SECRET_ACCESS_KEY
- WASABI_ENDPOINT_URL
- WASABI_REGION (ej: us-east-1)

2FA:
- Para roles críticos, activar 2FA en /usuarios/2fa/setup