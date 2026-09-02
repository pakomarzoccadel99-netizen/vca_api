from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import os

from database import SessionLocal, engine, Base
import models

# Creazione tabelle database
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

# --- ROTTE PER SERVIRE I FILE HTML (Evita i problemi di Not Found) ---
@app.get("/")
def read_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "VCA API Online. index.html non trovato."}

@app.get("/auth.html")
def read_auth():
    return FileResponse("auth.html")

@app.get("/admin_vca.html")
def read_admin():
    return FileResponse("admin_vca.html")

@app.get("/draft_vca.html")
def read_draft():
    return FileResponse("draft_vca.html")

@app.get("/dashboard_vca.html")
def read_dashboard():
    return FileResponse("dashboard_vca.html")

@app.get("/referto_vca.html")
def read_referto():
    return FileResponse("referto_vca.html")


# --- SCHEMI PYDANTIC & API BACKEND ---
class UserRegister(BaseModel):
    gamertag: str
    email: str
    password: str

class UserLogin(BaseModel):
    login_id: str
    password: str

@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter((models.User.gamertag == data.gamertag) | (models.User.email == data.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Gamertag o Email già registrati.")
    
    new_user = models.User(
        gamertag=data.gamertag,
        email=data.email,
        password=data.password,
        role="user"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Registrazione completata con successo!"}

@app.post("/api/auth/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        (models.User.gamertag == data.login_id) | (models.User.email == data.login_id)
    ).first()
    
    if not user or user.password != data.password:
        raise HTTPException(status_code=400, detail="Credenziali non valide.")
    
    return {
        "user_id": user.id,
        "gamertag": user.gamertag,
        "email": user.email,
        "role": user.role,
        "club_id": user.club_id
    }

@app.get("/api/user/profile/{user_id}")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    club_name = "Nessuno"
    if user.club_id:
        club = db.query(models.Club).filter(models.Club.id == user.club_id).first()
        if club:
            club_name = club.name

    return {
        "gamertag": user.gamertag,
        "email": user.email,
        "role": user.role,
        "club_name": club_name,
        "stats": {
            "goals": user.goals,
            "assists": user.assists,
            "matches_played": user.matches_played
        }
    }

@app.get("/api/tournaments")
def get_tournaments(db: Session = Depends(get_db)):
    tournaments = db.query(models.Tournament).all()
    result = []
    for t in tournaments:
        teams_count = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t.id).count()
        result.append({
            "id": t.id,
            "name": t.name,
            "format_type": t.format_type,
            "rules": t.rules,
            "teams_count": teams_count
        })
    return result

@app.get("/api/users/list")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [{"id": u.id, "gamertag": u.gamertag, "role": u.role} for u in users]