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
from datetime import datetime


@dataclass
class Option:
    answer: str
    correct: bool


@dataclass
class Question:
    text: str
    time_limit: int | None = None
    options: list[Option] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.options = [Option(**opt) for opt in self.options]

    def print(self) -> None:
        '''Nicely print text of the question with possible answeres'''

        question_label = f'Question number {app.state.quiz.current_question}/{len(app.state.quiz)}'
        logging.info(question_label)
        print(f'\n{question_label}')

        logging.info(f'Question text: {self.text}')
        print(self.text)

        for letter, opt in zip(string.ascii_letters, self.options):
            logging.info(opt)
            print(f'\t{letter}) {opt.answer}')

    def ask(self) -> dict:
        return {
            'type': 'question',
            'text': self.text,
            'options': [opt.answer for opt in self.options]
        }


@dataclass
class Quiz:
    name: str
    questions: list[Question] = field(default_factory=list)
    current_question: int = 0
    receiving_answers = False

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

    def print_results(self):
        print("Results...")


@dataclass
class Player:
    _id: str
    _websocket: WebSocket
    score: int = 0

    async def send(self, data: dict):
        await self._websocket.send_json(data)

    async def close_connection(self, msg: str):
        await self._websocket.close(reason=msg)


class Players:
    _players: list[Player] = []

    def find(self, player_id: str):
        ...

    def add(self, player: Player):
        self._players.append(player)

    def remove(self, player: Player):
        self._players.remove(player)

    async def send(self, data: dict):
        for player in self._players:
            await player.send(data)

    async def close_connection(self, msg: str):
        '''Print results of the quiz and disconnect the clients'''

        for player in self._players:
            await player.close_connection(msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    quiz_file = os.environ.get('QUIZ')
    if not quiz_file:
        shutdown_server("Environment variable QUIZ was not set!")

    yaml = YAML(typ='safe')
    with open(quiz_file, encoding='utf-8') as file:
        quiz_data = yaml.load(file)

    app.state.quiz = Quiz(**quiz_data)
    app.state.players = Players()
    logging.info(f'Quiz server started running quiz: {app.state.quiz.name}')
    asyncio.ensure_future(control_server())

    yield  # Second half of a life span - this is executed once server exits
    shutdown_server("Quiz server quit")


app = FastAPI(lifespan=lifespan)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    filename=f'{datetime.now():quiz-log_%Y-%m-%d_%H:%M:%S.txt}'
)


@app.websocket("/register/{player_id}")
async def register(ws: WebSocket, player_id: str):
    await ws.accept()
    await ws.send_json({'text': app.state.quiz.name})
    await ws.send_json({'text': 'Check your name on the screen!'})

    player = Player(player_id, ws)
    app.state.players.add(player)

    msg = f'{player_id} has connected'
    print(msg)
    logging.info(msg)

    try:
        while True:
            data = await ws.receive_json()
            logging.info(f"Client {player_id} sent: {data}")
    except WebSocketDisconnect:
        logging.info(f"{player_id} has disconected")
        app.state.players.remove(player)


async def control_server() -> None:
    '''
    Interaction with server app in terminal happens here. Joining players and
    sending question is possible in the same time
    '''
    print("Registred players:")

    while True:
        proceed_char = await aioconsole.ainput("Continue [y/N]:\n")
        if proceed_char.lower() != 'y':
            continue

        try:
            question = next(app.state.quiz)
        except StopIteration:
            app.state.quiz.print_results()

            msg = "Quiz ended"
            await app.state.players.close_connection(msg)

            shutdown_server(msg)

        question.print()
        await app.state.players.send(question.ask())


def shutdown_server(msg: str) -> None:
    '''This way of exit might not be correct but fits the usage of this software'''

    logging.info(msg)
    print(f'\n{msg}')
    os.kill(os.getppid(), signal.SIGTERM)  # Quit parent process - Uvicorn server
    os.kill(os.getpid(), signal.SIGKILL)   # Kill Quiz server
