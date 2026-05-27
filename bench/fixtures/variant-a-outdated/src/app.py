from fastapi import Depends, FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

engine = create_engine("sqlite:///db.sqlite3")
SessionLocal = sessionmaker(bind=engine)

app = FastAPI()


@app.on_event("startup")
async def startup():
    app.state.db_engine = engine


@app.on_event("shutdown")
async def shutdown():
    engine.dispose()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users
