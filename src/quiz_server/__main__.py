import asyncio
import aioconsole
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pprint import pprint

app = FastAPI()
clients = {}

async def handle_server_input():
    while True:
        server_input = await aioconsole.ainput("Server:\n")
        for client_socket in clients.values():
            await client_socket.send_text(server_input)


@app.websocket("/ws/{client_id}")
async def ws_endpoint(ws: WebSocket, client_id: str):
    asyncio.ensure_future(handle_server_input())
    await ws.accept()
    await ws.send_text(f"Welcome {client_id}!")
    clients[client_id] = ws
    print(client_id)

    try:
        while True:
            data = await ws.receive_text()
            print(f"Client {client_id} {ws}: {data}")

    except WebSocketDisconnect:
        del clients[client_id]
