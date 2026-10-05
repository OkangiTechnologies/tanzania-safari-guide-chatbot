from pathlib import Path
import os

from dotenv import load_dotenv

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from core.llm import get_client, generate_response
from core.prompt import SYSTEM_PROMPT
from services.db_service import (
    create_conversation,
    delete_conversation,
    get_conversation_messages,
    init_db,
    list_conversations,
    rename_conversation,
    save_message,
)


FRONTEND_DIR = Path(__file__).parent / "frontend"
ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)
if not os.getenv("GROQ_API_KEY") and ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if candidate.startswith("gsk_"):
            os.environ["GROQ_API_KEY"] = candidate
            break
TOURISM_TERMS = (
    "tanzania", "safari", "tourism", "tourist", "travel", "trip", "itinerary",
    "hotel", "lodge", "camp", "park", "wildlife", "animal", "lion", "elephant",
    "serengeti", "ngorongoro", "tarangire", "zanzibar", "arusha", "beach",
    "culture", "food", "flight", "airport", "visa", "guide", "weather",
    "utalii", "mtalii", "safari", "kusafiri", "safiri", "likizo", "ziara",
    "hifadhi", "wanyama", "simba", "tembo", "hoteli", "malazi", "ufukwe",
    "utamaduni", "chakula", "ndege", "visa", "hali ya hewa",
)
GREETING_TERMS = {
    "hi", "hello", "hey", "salam", "salaam", "assalamualaikum",
    "habari", "mambo", "hujambo", "jambo", "good morning", "good afternoon",
    "good evening",
}


def is_tourism_question(message):
    normalized = message.lower()
    return any(term in normalized for term in TOURISM_TERMS)


def is_greeting(message):
    normalized = message.lower().strip(" !?.;,\t\n")
    return normalized in GREETING_TERMS


async def chat(request):
    try:
        payload = await request.json()
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        user_message = payload.get("message", "").strip()
        history = payload.get("history", [])
        conversation_id = payload.get("conversation_id")

        if not user_message:
            return JSONResponse({"error": "Message is required."}, status_code=400)
        if is_greeting(user_message):
            return JSONResponse({
                "reply": "Salaam! Karibu Safari Guide. Naweza kukusaidia kuhusu utalii na safari za Tanzania.",
                "conversation_id": conversation_id,
            })
        if not api_key:
            return JSONResponse({"error": "GROQ_API_KEY is not configured on the server."}, status_code=500)
        if not is_tourism_question(user_message):
            return JSONResponse({
                "reply": "I can only help with Tanzania tourism and travel questions.",
                "conversation_id": conversation_id,
            })

        if not conversation_id:
            conversation_id = create_conversation()
            rename_conversation(conversation_id, user_message)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]
        reply = generate_response(get_client(api_key), messages)
        save_message(conversation_id, "user", user_message)
        save_message(conversation_id, "assistant", reply)

        return JSONResponse({"reply": reply, "conversation_id": conversation_id})
    except Exception as error:
        return JSONResponse({"error": str(error)}, status_code=500)


async def health(request):
    return JSONResponse({"status": "ok"})


async def conversations(request):
    return JSONResponse({"conversations": list_conversations()})


async def conversation_messages(request):
    conversation_id = int(request.path_params["conversation_id"])
    return JSONResponse({"messages": get_conversation_messages(conversation_id)})


async def delete_conversation_route(request):
    conversation_id = int(request.path_params["conversation_id"])
    delete_conversation(conversation_id)
    return JSONResponse({"deleted": True})


init_db()
app = Starlette(
    debug=True,
    routes=[
        Route("/api/chat", chat, methods=["POST"]),
        Route("/api/health", health, methods=["GET"]),
        Route("/api/conversations", conversations, methods=["GET"]),
        Route("/api/conversations/{conversation_id:int}", conversation_messages, methods=["GET"]),
        Route("/api/conversations/{conversation_id:int}", delete_conversation_route, methods=["DELETE"]),
        Mount("/", app=StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend"),
    ],
)