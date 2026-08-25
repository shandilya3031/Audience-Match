from langchain_aws import ChatBedrock

from app.config import settings

sonnet = ChatBedrock(
    model_id=settings.bedrock_sonnet_model_id,
    region_name=settings.aws_region,
    model_kwargs={"temperature": 0},
)

haiku = ChatBedrock(
    model_id=settings.bedrock_haiku_model_id,
    region_name=settings.aws_region,
    model_kwargs={"temperature": 0},
)

llama_fallback = ChatBedrock(
    model_id=settings.bedrock_fallback_model_id,
    region_name=settings.aws_region,
)

robust_sonnet = sonnet.with_fallbacks([haiku, llama_fallback])
