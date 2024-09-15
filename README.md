# quiz-server

This is the server side of the client-server quiz application. It tries to
provide the quiz game experience similar to **Kahoot** but in much lighter and
open manner as a CLI program.

The CLI client can be found at
[quiz-client](https://github.com/ZelenyMartin/quiz-client).

The server is operated by a lecturer and it is a **FastAPI** application run
under **Uvicorn** server providing the endpoint for the clients to establish
the connection through the **WebSockets**.

The **Asyncio** us used to control the server. It provides asynchronous network
communication with clients in JSON (sending questions, receiving answers),
showing the information and proceeding with the quiz questions.

Most of the program entities are implemented as **Data Classes** (`Players`,
`Player`, `Quiz`, `Questions`, `Question`, `Option`). It loads the quiz
questions from a **YAML** file.
