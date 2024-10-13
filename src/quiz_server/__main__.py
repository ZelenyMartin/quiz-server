import asyncio
import logging
import os
import signal
import string
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import aioconsole
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

# from datetime import datetime


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

    def __str__(self) -> str:
        """Nicely print text of the question with possible answeres"""

        question_label = f"Question number {app.state.quiz.current_question + 1}/{len(app.state.quiz)}"
        logging.info(question_label)
        logging.info(f"Question text: {self.text}")

        output = f"\n{question_label}\n{self.text}\n"

        for letter, opt in zip(string.ascii_letters, self.options):
            logging.info(opt)
            output += f"\t{letter}) {opt.answer}\n"

        return output

    def ask(self) -> dict:
        return {
            "type": "question",
            "text": self.text,
            "options": [opt.answer for opt in self.options],
        }


@dataclass
class Quiz:
    name: str
    questions: list[Question] = field(default_factory=list)
    current_question: int = -1

    def __post_init__(self):
        self.questions = [Question(**q) for q in self.questions]

    def __next__(self) -> Question:
        self.current_question += 1
        try:
            question = self.questions[self.current_question]
        except IndexError:
            raise StopIteration

        return question

    def __len__(self) -> int:
        return len(self.questions)

    @property
    def question(self):
        return self.questions[self.current_question]


@dataclass
class Player:
    _websocket: WebSocket
    name: str
    accepting_answer: bool = False

    async def send(self, data: dict):
        try:
            await self._websocket.send_json(data)
        except RuntimeError:
            logging.info(f'Player unreachable, cannot send data: {self.name}')

    async def close_connection(self, msg: str):
        try:
            await self._websocket.close(reason=msg)
        except RuntimeError:
            logging.info(f'Player unreachable, cannot close the connection: {self.name}')


class Players:
    _players: list[Player] = []

    def find(self, player_id: str): ...

    def add(self, player: Player):
        self._players.append(player)

    def remove(self, player: Player):
        self._players.remove(player)

    def unblock_players(self):
        for player in self._players:
            player.accepting_answer = True

    async def send(self, data: dict):
        for player in self._players:
            await player.send(data)

    async def close_connection(self, msg: str):
        """Print results of the quiz and disconnect the clients"""

        for player in self._players:
            await player.close_connection(msg)


class Results:
    _results: dict[tuple[str, int], str] = {}

    def check_answer(
        self, player: Player, question: Question, question_number: int, answer: str
    ):
        self._results[(player.name, question_number)] = answer

    def __str__(self):
        output = "\nResults:\n"
        output += "Name\tQuestion\tResult\n"

        for (name, qustion), result in self._results.items():
            output += f"{name}\t{qustion}\t{result}\n"

        return output


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        quiz_file = os.environ["QUIZ"]
    except KeyError:
        shutdown_server("Environment variable QUIZ was not set!")

    yaml = YAML(typ="safe")
    try:
        with open(quiz_file, encoding="utf-8") as file:
            quiz_data = yaml.load(file)

        app.state.quiz = Quiz(**quiz_data)
    except (OSError, YAMLError, TypeError) as e:
        shutdown_server(f"Can't load a quiz file: {quiz_file}", exception=e)

    app.state.players = Players()
    app.state.results = Results()
    logging.info(f"Quiz server started running quiz: {app.state.quiz.name}")
    asyncio.ensure_future(control_server())

    yield  # Second half of a life span - this is executed once server exits
    shutdown_server("Quiz server quit")


app = FastAPI(lifespan=lifespan)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d|%(message)s",
    datefmt="%H:%M:%S",
    # filename=f'{datetime.now():quiz-log_%Y-%m-%d_%H:%M:%S.txt}'
    filename="quiz-log_.txt",
)


@app.websocket("/connect/{player_name}")
async def connect(ws: WebSocket, player_name: str):
    await ws.accept()
    await ws.send_json({"text": app.state.quiz.name})
    await ws.send_json({"text": "Check your name on the screen!"})

    player = Player(ws, player_name)
    app.state.players.add(player)

    msg = f"Player connects: {player_name}"
    print(msg)
    logging.info(msg)

    try:
        while True:
            data = await ws.receive_json()
            logging.info(f"Client {player_name} sent: {data}")

            if player.accepting_answer:
                await player.send({"type": "repeat", "text": data["answer"]})
                player.accepting_answer = False
                app.state.results.check_answer(
                    player,
                    app.state.quiz.question,
                    app.state.quiz.current_question,
                    data["answer"],
                )

    except WebSocketDisconnect:
        logging.info(f"Player disconnects: {player_name}")
        # app.state.players.remove(player)


async def control_server() -> None:
    """
    Interaction with server app in terminal happens here. Joining players and
    sending question is possible in the same time
    """
    print("Registred players:")

    while True:
        proceed_char = await aioconsole.ainput("Continue [y/N]:\n")
        if proceed_char.lower() != "y":
            continue

        try:
            question = next(app.state.quiz)
        except StopIteration:
            print(app.state.results)

            msg = "Quiz ended"
            await app.state.players.close_connection(msg)

            shutdown_server(msg)

        print(question, end="")
        app.state.players.unblock_players()
        await app.state.players.send(question.ask())


def shutdown_server(msg: str, exception: Exception = None) -> None:
    """This way of exit might not be correct but fits the usage of this software"""

    if exception:
        logging.info(f"{exception}")
    logging.info(f"{msg}\n")

    print(f"\n{msg}")

    # Quit parent process - Uvicorn server
    os.kill(os.getppid(), signal.SIGTERM)
    os.kill(os.getpid(), signal.SIGKILL)  # Kill Quiz server
