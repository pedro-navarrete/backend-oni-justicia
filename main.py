# main.py
import uvicorn
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse
from database.verificador_mongo import init_mongo
from routers import auth, user_router, verificar_router, mision_router, vehiculo_router, \
    solicitud_edicion_router, solicitud_factura_edicion, mision_estadisticas_router, editar_mision_completa, \
    estado_vehiculo_router

# Configuración básica de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

app = FastAPI()


# Crear appFa
app = FastAPI(
    title="Backend OniTransporte",
    description="API para la gestión de transporte y misiones",
    version="1.0.0",
    # docs_url=None,
    # redoc_url=None,
    # openapi_url=None,
)

# -------------------- EVENTOS --------------------
@app.on_event("startup")
async def startup_event():
    """Inicializa la conexión a MongoDB al iniciar la app"""
    try:
        init_mongo()
        logging.info("Conexión a MongoDB establecida correctamente")
    except Exception as e:
        logging.error(f"No se pudo inicializar MongoDB: {e}")

# -------------------- MIDDLEWARE / EXCEPCIONES --------------------
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    """Middleware para capturar excepciones no manejadas"""
    try:
        return await call_next(request)
    except Exception as exc:
        logging.error(f"Error interno: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        )

# -------------------- ROUTERS --------------------
app.include_router(auth.router)
app.include_router(user_router.router)
app.include_router(verificar_router.router)
app.include_router(mision_router.router)
app.include_router(vehiculo_router.router)
app.include_router(solicitud_edicion_router.router)
app.include_router(solicitud_factura_edicion.router)
app.include_router(mision_estadisticas_router.router)
app.include_router(editar_mision_completa.router)
app.include_router(estado_vehiculo_router.router)

#--------------------Raiz del API----------------

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
    <head>
        <title>Oni Transporte</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #fdfdfd;
                color: #111;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .container {
                text-align: center;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                background-color: #ffffff;
                max-width: 500px;
            }
            h2 {
                margin-bottom: 20px;
                font-size: 28px;
            }
            p {
                margin-bottom: 15px;
                font-size: 16px;
            }
            a {
                text-decoration: none;
                color: #ffffff;
                background-color: #111;
                padding: 8px 16px;
                border-radius: 6px;
                transition: background-color 0.3s;
            }
            a:hover {
                background-color: #333;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Bienvenido al backend de Oni transporte(tracking)</h2>
            <p>Documentación disponible en:</p>
            <p><a href='/docs'>Swagger UI</a></p>
            <p>Alternativa Redoc:</p>
            <p><a href='/redoc'>Redoc</a></p>
        </div>
    </body>
    </html>
    """

# -------------------- EJECUTAR APP --------------------
#if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
