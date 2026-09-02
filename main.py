import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
import models

# Crea le tabelle del database all'avvio
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserRegister(BaseModel):
    gamertag: str
    email: str
    password: str

class UserLogin(BaseModel):
    login_id: str
    password: str

@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        (models.User.gamertag == data.gamertag) | (models.User.email == data.email)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Gamertag o Email già in uso.")
        
    new_user = models.User(
        gamertag=data.gamertag, 
        email=data.email, 
        password=data.password, 
        role="user"
    )
    db.add(new_user)
    db.commit()
    return {"message": "Registrazione completata!"}

@app.post("/api/auth/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        (models.User.gamertag == data.login_id) | (models.User.email == data.login_id)
    ).first()
    
    if not user or user.password != data.password:
        raise HTTPException(status_code=400, detail="Credenziali errate.")
        
    return {
        "user_id": user.id, 
        "gamertag": user.gamertag, 
        "email": user.email, 
        "role": user.role, 
        "club_id": user.club_id
    }

@app.get("/api/tournaments")
def get_tournaments(db: Session = Depends(get_db)):
    return db.query(models.Tournament).all()
class RoleUpdate(BaseModel):
    user_id: int
    new_role: str

@app.post("/api/admin/set-role")
def set_role(data: RoleUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    user.role = data.new_role
    db.commit()
    return {"message": f"Ruolo di {user.gamertag} aggiornato a {data.new_role}"}

@app.get("/api/admin/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [{"id": u.id, "gamertag": u.gamertag, "email": u.email, "role": u.role, "club_name": u.club_id} for u in users]
@app.get("/")
def read_root():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "Home page non trovata."}

app.mount("/", StaticFiles(directory=".", html=True), name="static")
