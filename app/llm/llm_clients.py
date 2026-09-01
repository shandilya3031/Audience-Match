from langchain_groq import ChatGroq

from app.config import settings

sonnet = ChatGroq(
    model=settings.groq_sonnet_model_id,
    api_key=settings.groq_api_key,
    temperature=0,
)

haiku = ChatGroq(
    model=settings.groq_haiku_model_id,
    api_key=settings.groq_api_key,
    temperature=0,
)

fallback_model = ChatGroq(
    model=settings.groq_fallback_model_id,
    api_key=settings.groq_api_key,
    temperature=0,
)

robust_sonnet = sonnet.with_fallbacks([haiku, fallback_model])
