"""Chat with the QuoteSure agent."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.runner import AgentError, run_agent
from app.database import get_db

router = APIRouter(prefix="/agent", tags=["AI Agent"])


class ChatTurn(BaseModel):
    role: str = Field(examples=["user"])   # "user" or "assistant"
    text: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, examples=["Is Sharma Steel charging me fairly?"])
    history: list[ChatTurn] = []


class AgentStep(BaseModel):
    tool: str
    args: dict
    result: str


class ChatResponse(BaseModel):
    reply: str
    steps: list[AgentStep]


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """Ask anything about suppliers, prices, orders or open quotes.
    The agent decides which tools to use; `steps` shows what it did.
    (A plain `def` endpoint: FastAPI runs it on a separate thread, so slow
    Gemini calls don't freeze the server.)"""
    try:
        return run_agent(db, req.message, [t.model_dump() for t in req.history])
    except AgentError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
