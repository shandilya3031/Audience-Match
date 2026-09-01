# Run from the repo root as a module: python -m scripts.verify_langsmith_trace
# (running it as a bare script file won't put the repo root on sys.path)
from app.llm.llm_clients import haiku


def main() -> None:
    response = haiku.invoke("Say 'observability check' and nothing else.")
    print(response.content)


if __name__ == "__main__":
    main()
