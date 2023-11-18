from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import asyncio
import logging
import aioconsole
import os
import signal
from dataclasses import dataclass, field
from ruamel.yaml import YAML

from pprint import pprint


@dataclass
class Option:
    answer: str
    correct: bool


@dataclass
class Question:
    text: str
    time_limit: int
    options: list[Option] = field(default_factory=list)

    def __post_init__(self):
        self.options = [Option(**opt) for opt in self.options]


@dataclass
class Quiz:
    name: str
    questions: list[Question] = field(default_factory=list)

    def __post_init__(self):
        self.questions = [Question(**q) for q in self.questions]


@asynccontextmanager
async def lifespan(app: FastAPI):
    quiz_file = os.environ.get('QUIZ')
    if not quiz_file:
        logger.critical("Environment variable QUIZ was not set.")
        os.kill(os.getpid(), signal.SIGKILL)

    yaml = YAML(typ='safe')
    with open(quiz_file, encoding='utf-8') as file:
        data = yaml.load(file)

    quiz = Quiz(**data)
    pprint(quiz)

    asyncio.ensure_future(control_server())
    yield
    logger.warn("\nBye!")


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger(__name__)
clients = {}


@app.websocket("/ws/{client_id}")
async def ws_endpoint(ws: WebSocket, client_id: str):
    await ws.accept()
    await ws.send_text(f"Welcome {client_id}!")
    clients[client_id] = ws
    print(f'\n{client_id}')

    try:
        while True:
            data = await ws.receive_text()
            print(f"\nClient {client_id} {ws}: {data}")
    except WebSocketDisconnect:
        del clients[client_id]


async def send_to_clients(msg: str):
    for client_socket in clients.values():
        await client_socket.send_text(msg)


async def control_server():
    while True:
        proceed_char = await aioconsole.ainput("Proceed [y/N]: ")
        if proceed_char.lower() != 'y':
            continue
        print("Otazka poslana")
        await send_to_clients("Otazka")
