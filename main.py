import os
import random
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- SCHEMI DATI ---
class UserAuth(BaseModel):
    gamertag: str = None
    email: str = None
    login_id: str = None
    password: str

class RoleUpdate(BaseModel):
    user_id: int
    new_role: str

class ClubCreate(BaseModel):
    name: str
    formation: str
    owner_id: int

class PlayerAction(BaseModel):
    club_id: int
    user_id: Optional[int] = None
    player_id: Optional[int] = None

class DraftSignup(BaseModel):
    gamertag: str
    role: str
    user_id: int

class TournamentCreate(BaseModel):
    name: str
    format_type: str
    rules: str

class TournamentRegister(BaseModel):
    tournament_id: int
    club_id: int

class PlayerStat(BaseModel):
    player_id: int
    goals: int
    assists: int

class MatchSubmit(BaseModel):
    tournament_id: int
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    player_stats: List[PlayerStat] = []

# --- API AUTH E PROFILO ---
@app.post("/api/auth/register")
def register(data: UserAuth, db: Session = Depends(get_db)):
    if db.query(models.User).filter((models.User.gamertag == data.gamertag) | (models.User.email == data.email)).first():
        raise HTTPException(status_code=400, detail="Utente già registrato.")
    new_user = models.User(gamertag=data.gamertag, email=data.email, password=data.password, role="user")
    db.add(new_user)
    db.commit()
    return {"message": "Registrazione ok!"}

@app.post("/api/auth/login")
def login(data: UserAuth, db: Session = Depends(get_db)):
    user = db.query(models.User).filter((models.User.gamertag == data.login_id) | (models.User.email == data.login_id)).first()
    if not user or user.password != data.password: raise HTTPException(status_code=400, detail="Credenziali errate.")
    return {"user_id": user.id, "gamertag": user.gamertag, "email": user.email, "role": user.role, "club_id": user.club_id}

@app.get("/api/user/profile/{user_id}")
def profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(status_code=404)
    club = db.query(models.Club).filter(models.Club.id == user.club_id).first() if user.club_id else None
    return {
        "gamertag": user.gamertag, "email": user.email, "role": user.role, 
        "club_name": club.name if club else "Nessuno",
        "stats": {"goals": user.goals, "assists": user.assists, "matches_played": user.matches_played}
    }

# --- API ADMIN E UTENTI ---
@app.post("/api/admin/set-role")
def set_role(data: RoleUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user: raise HTTPException(status_code=404)
    user.role = data.new_role
    db.commit()
    return {"message": f"Ruolo aggiornato a {data.new_role}"}

@app.get("/api/admin/users")
@app.get("/api/users/list")
def list_users(db: Session = Depends(get_db)):
    return [{"id": u.id, "gamertag": u.gamertag, "email": u.email, "role": u.role, "club_name": u.club_id} for u in db.query(models.User).all()]

# --- API CLUB ---
@app.post("/api/club/create")
def create_club(data: ClubCreate, db: Session = Depends(get_db)):
    if db.query(models.Club).filter(models.Club.name == data.name).first():
        raise HTTPException(status_code=400, detail="Nome club in uso.")
    new_club = models.Club(name=data.name, formation=data.formation, owner_id=data.owner_id)
    db.add(new_club)
    db.commit()
    db.refresh(new_club)
    owner = db.query(models.User).filter(models.User.id == data.owner_id).first()
    if owner:
        owner.club_id = new_club.id
        owner.role = "captain"
        db.commit()
    return {"message": "Club creato!", "club_id": new_club.id}

@app.get("/api/club/details/{club_id}")
def get_club(club_id: int, db: Session = Depends(get_db)):
    club = db.query(models.Club).filter(models.Club.id == club_id).first()
    players = db.query(models.User).filter(models.User.club_id == club.id).all()
    return {"name": club.name, "formation": club.formation, "players": [{"user_id": p.id, "gamertag": p.gamertag, "role": p.role, "goals": p.goals, "assists": p.assists, "matches_played": p.matches_played} for p in players]}

@app.post("/api/club/add-player")
def add_player(data: PlayerAction, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    user.club_id = data.club_id
    db.commit()
    return {"message": "Aggiunto"}

@app.post("/api/club/remove-player")
def remove_player(data: PlayerAction, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    user.club_id = None
    db.commit()
    return {"message": "Rimosso"}

# --- API DRAFT ---
@app.post("/api/draft/signup-player")
def draft_signup(data: DraftSignup, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    user.draft_role = data.role
    db.commit()
    return {"message": "Candidato al draft!"}

@app.get("/api/draft/random-players/{role}")
def draft_random(role: str, db: Session = Depends(get_db)):
    players = db.query(models.User).filter(models.User.draft_role == role, models.User.club_id == None).all()
    options = [{"id": p.id, "gamertag": p.gamertag, "role": p.draft_role} for p in players]
    random.shuffle(options)
    return {"role": role, "options": options[:3]}

@app.post("/api/draft/assign")
def draft_assign(data: PlayerAction, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.player_id).first()
    user.club_id = data.club_id
    user.draft_role = None 
    db.commit()
    return {"message": "Assegnato"}

@app.get("/api/draft/summary")
def draft_summary(db: Session = Depends(get_db)):
    res = []
    for c in db.query(models.Club).all():
        players = db.query(models.User).filter(models.User.club_id == c.id).all()
        res.append({
            "club_name": c.name, "formation": c.formation, "is_complete": len(players) >= 11,
            "roles_breakdown": {"ATT": 0, "CC": 0, "ES": 0, "ED": 0, "DIF": 0, "POR": 0},
            "players": [{"gamertag": p.gamertag, "role": p.role, "goals": p.goals, "assists": p.assists} for p in players]
        })
    return res

# --- API TORNEI E REFERTI ---
@app.get("/api/tournaments")
def get_tournaments(db: Session = Depends(get_db)):
    return db.query(models.Tournament).all()

@app.post("/api/tournaments")
def create_tournament(data: TournamentCreate, db: Session = Depends(get_db)):
    t = models.Tournament(name=data.name, format_type=data.format_type, rules=data.rules)
    db.add(t)
    db.commit()
    return {"message": "Creato"}

@app.post("/api/tournaments/register")
def register_tournament(data: TournamentRegister, db: Session = Depends(get_db)):
    db.add(models.TournamentRegistration(tournament_id=data.tournament_id, club_id=data.club_id))
    db.commit()
    return {"message": "Iscritto"}

@app.post("/api/matches/submit-league")
def submit_match(data: MatchSubmit, db: Session = Depends(get_db)):
    for stat in data.player_stats:
        p = db.query(models.User).filter(models.User.id == stat.player_id).first()
        if p:
            p.goals += stat.goals
            p.assists += stat.assists
            p.matches_played += 1
    db.commit()
    return {"message": "Inviato!"}

# --- GESTIONE FRONTEND HTML ---
@app.get("/")
def read_root():
    if os.path.exists("index.html"): return FileResponse("index.html")
    return {"message": "Home page non trovata."}

app.mount("/", StaticFiles(directory=".", html=True), name="static")
