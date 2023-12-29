from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import asyncio
import logging
import aioconsole
import os
import signal
import string
from dataclasses import dataclass, field
from ruamel.yaml import YAML


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

    def ask(self) -> dict:
        return {'text': self.text, 'options': [opt.answer for opt in self.options]}


@dataclass
class Quiz:
    name: str
    questions: list[Question] = field(default_factory=list)
    current_question: int = 0

    def __post_init__(self):
        self.questions = [Question(**q) for q in self.questions]

    def __next__(self) -> Question:
        try:
            question = self.questions[self.current_question]
        except IndexError:
            raise StopIteration

        self.current_question += 1
        return question

    def __len__(self) -> int:
        return len(self.questions)


@dataclass
class Player:
    id: str
    websocket: WebSocket
    score: int = 0


class Players:
    _players: list[Player] = []

    def add(self, player: Player):
        self._players.append(player)

    def remove(self, player: Player):
        self._players.remove(player)

    async def send_question(self, question: dict | str):
        for player in self._players:
            await player.websocket.send_json(question)


@asynccontextmanager
async def lifespan(app: FastAPI):
    quiz_file = os.environ.get('QUIZ')
    if not quiz_file:
        logger.critical("Environment variable QUIZ was not set.")
        os.kill(os.getpid(), signal.SIGKILL)

    yaml = YAML(typ='safe')
    with open(quiz_file, encoding='utf-8') as file:
        quiz_data = yaml.load(file)

    app.state.quiz = Quiz(**quiz_data)
    app.state.players = Players()
    asyncio.ensure_future(control_server())

    yield  # Second half of a life span - this is executed once server exits
    logger.warn("\nServer quit")


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger(__name__)


@app.websocket("/register/{player_id}")
async def register(ws: WebSocket, player_id: str):
    await ws.accept()
    await ws.send_json(app.state.quiz.name)
    await ws.send_json("Check your name on the screen!")

    player = Player(player_id, ws)
    app.state.players.add(player)
    print(player_id)

    try:
        while True:
            data = await ws.receive_text()
            print(f"\nClient {player_id} {ws}: {data}")
    except WebSocketDisconnect:
        logger.warn(f"{player_id} disconected")
        app.state.players.remove(player)


async def control_server():
    '''Wait for all players to login to the quiz'''
    print("Send 'y' to start the quiz")
    print("Registred players:")

    while True:
        proceed_char = await aioconsole.ainput()
        if proceed_char.lower() == 'y':
            break

    while True:
        proceed_char = await aioconsole.ainput("Proceed [y/N]: ")
        if proceed_char.lower() != 'y':
            continue

        try:
            question = next(app.state.quiz)
        except StopIteration:
            end_quiz()
            break

        print(
            f'[Question {app.state.quiz.current_question}/{len(app.state.quiz)}]')
        print_question(question)
        await app.state.players.send_question(question.ask())


def print_question(question: Question):
    '''Nicely print text of the question with possible answeres'''

    print(question.text)
    for letter, opt in zip(string.ascii_letters, question.options):
        print(f'\t{letter}) {opt.answer}')


def end_quiz():
    print("Quiz ended")
