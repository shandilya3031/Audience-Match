from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["dev", "staging", "prod"] = "dev"

    # Bedrock / AWS
    aws_region: str
    bedrock_sonnet_model_id: str
    bedrock_haiku_model_id: str
    bedrock_fallback_model_id: str

    # Pinecone
    pinecone_api_key: str
    pinecone_environment: str
    pinecone_index_name: str

    # PostgreSQL
    postgres_dsn: str
    postgres_readonly_dsn: str

    # DynamoDB
    dynamodb_chat_history_table: str = "ChatHistory"
    dynamodb_schema_metadata_table: str = "SchemaMetadata"
    dynamodb_prompt_registry_table: str = "PromptRegistry"

    # S3
    s3_raw_documents_bucket: str
    s3_raw_customer_data_bucket: str

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str
    langchain_project: str = "audience-match-dev"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
