import os
import random
from datetime import datetime, timedelta
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- SCHEMI DATI ---
class UserAuth(BaseModel): gamertag: str = None; email: str = None; login_id: str = None; password: str
class RoleUpdate(BaseModel): user_id: int; new_role: str
class AdminRemovePlayer(BaseModel): user_id: int
class ClubCreate(BaseModel): name: str; formation: str; owner_id: int
class PlayerAction(BaseModel): club_id: int; user_id: Optional[int] = None; player_id: Optional[int] = None
class TournamentCreate(BaseModel): name: str; format_type: str; rules: str; max_teams: int; matchdays: int; swiss_rounds: int = 0; playoff_teams: int = 0
class CalendarGenerate(BaseModel): tournament_id: int; start_date: str; play_days: List[int]
class TournamentRegister(BaseModel): tournament_id: int; club_id: int

# --- API AUTH & PROFILO ---
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
    club = db.query(models.Club).filter(models.Club.id == user.club_id).first() if user.club_id else None
    return {"gamertag": user.gamertag, "email": user.email, "role": user.role, "club_name": club.name if club else "Nessuno", "stats": {"goals": user.goals, "assists": user.assists, "matches_played": user.matches_played}}

# --- API ADMIN E UTENTI ---
@app.post("/api/admin/set-role")
def set_role(data: RoleUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    user.role = data.new_role
    db.commit()
    return {"message": "Ruolo aggiornato"}

@app.post("/api/admin/force-remove-player")
def force_remove_player(data: AdminRemovePlayer, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if user:
        user.club_id = None
        if user.role == "captain": user.role = "user"
        db.commit()
    return {"message": f"{user.gamertag} svincolato!"}

@app.get("/api/admin/users")
@app.get("/api/users/list")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    res = []
    for u in users:
        club = db.query(models.Club).filter(models.Club.id == u.club_id).first() if u.club_id else None
        res.append({"id": u.id, "gamertag": u.gamertag, "email": u.email, "role": u.role, "club_name": club.name if club else None})
    return res

# --- API CLUB ---
@app.post("/api/club/create")
def create_club(data: ClubCreate, db: Session = Depends(get_db)):
    if db.query(models.Club).filter(models.Club.name == data.name).first(): raise HTTPException(status_code=400, detail="Nome club in uso.")
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

# --- API TORNEI & LISTA ATTESA ---
@app.get("/api/tournaments")
def get_tournaments(db: Session = Depends(get_db)):
    tournaments = db.query(models.Tournament).all()
    res = []
    for t in tournaments:
        teams_count = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t.id, models.TournamentRegistration.is_waitlisted == False).count()
        waitlist_count = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t.id, models.TournamentRegistration.is_waitlisted == True).count()
        res.append({"id": t.id, "name": t.name, "format_type": t.format_type, "status": t.status, "max_teams": t.max_teams, "teams_count": teams_count, "waitlist_count": waitlist_count})
    return res

@app.post("/api/tournaments")
def create_tournament(data: TournamentCreate, db: Session = Depends(get_db)):
    t = models.Tournament(
        name=data.name, format_type=data.format_type, rules=data.rules, max_teams=data.max_teams, matchdays=data.matchdays,
        swiss_rounds=data.swiss_rounds, playoff_teams=data.playoff_teams, status="open"
    )
    db.add(t)
    db.commit()
    return {"message": "Competizione creata"}

@app.post("/api/tournaments/register")
def register_tournament(data: TournamentRegister, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == data.tournament_id).first()
    if not t: raise HTTPException(status_code=404, detail="Torneo non trovato")
    if t.status == "closed": raise HTTPException(status_code=400, detail="Le iscrizioni per questo torneo sono chiuse.")
    
    existing = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == data.tournament_id, models.TournamentRegistration.club_id == data.club_id).first()
    if existing: raise HTTPException(status_code=400, detail="Il tuo club è già iscritto o in lista d'attesa.")
    
    current_count = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == data.tournament_id, models.TournamentRegistration.is_waitlisted == False).count()
    
    # Se il torneo è pieno, va in Lista d'Attesa
    is_waitlisted = current_count >= t.max_teams
    db.add(models.TournamentRegistration(tournament_id=data.tournament_id, club_id=data.club_id, is_waitlisted=is_waitlisted))
    db.commit()
    
    if is_waitlisted: return {"message": "Iscritti in LISTA D'ATTESA. Sarete contattati se si libera un posto."}
    return {"message": "Club iscritto ufficialmente!"}

@app.post("/api/admin/toggle-tournament/{t_id}")
def toggle_tournament(t_id: int, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == t_id).first()
    t.status = "closed" if t.status == "open" else "open"
    db.commit()
    return {"message": f"Iscrizioni {t.status}!"}

@app.post("/api/admin/delete-tournament/{t_id}")
def delete_tournament(t_id: int, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == t_id).first()
    if not t: raise HTTPException(status_code=404, detail="Torneo non trovato")
    db.query(models.Match).filter(models.Match.tournament_id == t_id).delete()
    db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t_id).delete()
    db.delete(t)
    db.commit()
    return {"message": "Competizione eliminata."}

@app.post("/api/admin/generate-calendar")
def generate_calendar(data: CalendarGenerate, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == data.tournament_id).first()
    if not t: raise HTTPException(status_code=404, detail="Torneo non trovato")
    
    regs = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t.id, models.TournamentRegistration.is_waitlisted == False).all()
    team_ids = [r.club_id for r in regs]
    
    if len(team_ids) < 2: raise HTTPException(status_code=400, detail="Servono almeno 2 squadre iscritte Ufficialmente.")
    if len(team_ids) % 2 != 0: team_ids.append(None) # Team fantasma per il "Riposo"

    num_teams = len(team_ids)
    total_rounds = num_teams - 1
    total_matchdays = total_rounds * t.matchdays

    current_date = datetime.strptime(data.start_date, "%Y-%m-%d")
    matchday_dates = {}
    day_counter = 1
    
    while day_counter <= total_matchdays:
        if current_date.weekday() in data.play_days:
            matchday_dates[day_counter] = current_date.strftime("%Y-%m-%d")
            day_counter += 1
        current_date += timedelta(days=1)

    db.query(models.Match).filter(models.Match.tournament_id == t.id).delete()

    matches = []
    teams = list(team_ids)
    
    for round_idx in range(total_rounds):
        matchday = round_idx + 1
        play_date = matchday_dates[matchday]
        for i in range(num_teams // 2):
            home = teams[i]
            away = teams[num_teams - 1 - i]
            if home is not None and away is not None:
                matches.append(models.Match(tournament_id=t.id, home_team_id=home, away_team_id=away, matchday=matchday, play_date=play_date))
        teams.insert(1, teams.pop())

    if t.matchdays == 2:
        for round_idx in range(total_rounds):
            matchday = total_rounds + round_idx + 1
            play_date = matchday_dates[matchday]
            for i in range(num_teams // 2):
                home = teams[i]
                away = teams[num_teams - 1 - i]
                if home is not None and away is not None:
                    matches.append(models.Match(tournament_id=t.id, home_team_id=away, away_team_id=home, matchday=matchday, play_date=play_date))
            teams.insert(1, teams.pop())

    db.add_all(matches)
    db.commit()
    return {"message": f"Calendario base generato per {len(regs)} squadre! (Totale {total_matchdays} giornate)"}

# --- GESTIONE FRONTEND ---
@app.get("/")
def read_root():
    if os.path.exists("index.html"): return FileResponse("index.html")
    return {"message": "Home page non trovata."}

app.mount("/", StaticFiles(directory=".", html=True), name="static")
