import math
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = "8766102244:AAE70LSpBADzM7xsFnStP_7Z7oUYklOAMaQ"
ID_MOTORISTA = None

DESTINO_LAT = -6.4583
DESTINO_LON = -37.0978

alunos_inscritos = set()

dados_bus = {
    "lat": None,
    "lon": None,
    "velocidade_kmh": 0,
    "tempo_restante_min": None,
    "notificado_5min": False
}

def calcular_distancia_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Gerenciador de ciclo de vida moderno (substitui on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    print("🤖 Bot do Telegram pronto para uso!")
    yield
    await telegram_app.updater.stop()
    await telegram_app.stop()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LocationData(BaseModel):
    lat: float
    lon: float
    velocidade: float

@app.post("/atualizar_localizacao")
async def atualizar_localizacao(data: LocationData):
    dados_bus["lat"] = data.lat
    dados_bus["lon"] = data.lon
    dados_bus["velocidade_kmh"] = data.velocidade
    
    distancia_km = calcular_distancia_km(data.lat, data.lon, DESTINO_LAT, DESTINO_LON)
    
    if data.velocidade > 5:
        tempo_minutos = (distancia_km / data.velocidade) * 60
        dados_bus["tempo_restante_min"] = round(tempo_minutos, 1)
        
        if tempo_minutos <= 5 and not dados_bus["notificado_5min"]:
            dados_bus["notificado_5min"] = True
            for chat_id in alunos_inscritos:
                try:
                    await telegram_app.bot.send_message(
                        chat_id=chat_id,
                        text="🚨 *ATENÇÃO*: O ônibus está a aproximadamente *5 minutos* da UFRN Caicó!",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Erro ao enviar para {chat_id}: {e}")
    else:
        dados_bus["tempo_restante_min"] = None

    return {"status": "sucesso"}

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    alunos_inscritos.add(chat_id)
    await update.message.reply_text(
        "👋 Olá! Você se cadastrou para receber alertas do ônibus.\n\n"
        "Comandos disponíveis:\n"
        "/status - Ver velocidade e tempo estimado\n"
        "/quebrou - Motorista envia alerta de imprevisto"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if dados_bus["lat"] is None:
        await update.message.reply_text("🔴 O ônibus ainda não iniciou a viagem.")
        return
        
    vel = dados_bus["velocidade_kmh"]
    tempo = dados_bus["tempo_restante_min"]
    
    msg = f"🚌 *Status do Ônibus*\n"
    msg += f"⚡ Velocidade atual: *{vel} km/h*\n"
    
    if tempo is not None:
        msg += f"⏳ Tempo estimado para UFRN: *{tempo} min*"
    else:
        msg += "⏳ Calculando tempo (ônibus parado ou em baixa velocidade)..."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_quebrou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if ID_MOTORISTA and user_id != ID_MOTORISTA:
        await update.message.reply_text("❌ Apenas o motorista tem autorização para emitir este alerta.")
        return

    msg_emergencia = (
        "⚠️ *AVISO DE EMERGÊNCIA*\n\n"
        "O motorista informou que o ônibus *quebrou* ou teve um imprevisto na rota.\n"
        "Por favor, busquem alternativas de transporte."
    )
    
    if not alunos_inscritos:
        await update.message.reply_text("⚠️ Nenhum aluno se cadastrou no bot ainda.")
        return

    for chat_id in alunos_inscritos:
        try:
            await telegram_app.bot.send_message(chat_id=chat_id, text=msg_emergencia, parse_mode="Markdown")
        except Exception as e:
            print(f"Erro ao notificar {chat_id}: {e}")

    await update.message.reply_text("✅ Alerta de emergência enviado a todos os alunos.")

telegram_app.add_handler(CommandHandler("start", cmd_start))
telegram_app.add_handler(CommandHandler("status", cmd_status))
telegram_app.add_handler(CommandHandler("quebrou", cmd_quebrou))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)