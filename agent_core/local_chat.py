"""Interactive local chat with the task agent, without deploying to AgentCore.

Uses real Bedrock (Kimi K2.5) and a real DynamoDB tasks table. Set BEDROCK_AGENTCORE_MEMORY_ID
to also use the deployed AgentCore Memory; otherwise history is kept in memory only.

Usage (from task_agent/agent_core):
    export AWS_PROFILE=<perfil> AWS_REGION=us-east-1
    export TASKS_TABLE_NAME=<tabla> USER_TIMEZONE=America/Mexico_City
    python local_chat.py --actor-id ana
"""
import argparse
import asyncio
import uuid

import main


def run() -> None:
    parser = argparse.ArgumentParser(description="Chat local con el agente de tareas")
    parser.add_argument("--actor-id", required=True, help="Identificador del estudiante (letras, números, - o _)")
    args = parser.parse_args()

    session_id = uuid.uuid4().hex
    print(f"Actor: {args.actor_id} | Sesión: {session_id}")
    print("Escribe 'salir' para terminar o 'nueva' para iniciar otra sesión.\n")

    while True:
        try:
            prompt = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt.lower() == "salir":
            break
        if prompt.lower() == "nueva":
            session_id = uuid.uuid4().hex
            print(f"Nueva sesión: {session_id}\n")
            continue

        payload = {"prompt": prompt, "actor_id": args.actor_id, "session_id": session_id}
        print(f"Agente: {asyncio.run(main.invoke(payload))}\n")


if __name__ == "__main__":
    run()
