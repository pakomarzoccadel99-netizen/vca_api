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
class PlayerStat(BaseModel): player_id: int; goals: int; assists: int
class MatchSubmit(BaseModel): match_id: int; home_score: int; away_score: int; player_stats: List[PlayerStat] = []
class DraftSignup(BaseModel): role: str; user_id: int

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

# --- API TORNEI & CALENDARIO ---
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
    t = models.Tournament(name=data.name, format_type=data.format_type, rules=data.rules, max_teams=data.max_teams, matchdays=data.matchdays, swiss_rounds=data.swiss_rounds, playoff_teams=data.playoff_teams, status="open")
    db.add(t)
    db.commit()
    return {"message": "Competizione creata"}

@app.post("/api/tournaments/register")
def register_tournament(data: TournamentRegister, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == data.tournament_id).first()
    if t.status == "closed": raise HTTPException(status_code=400, detail="Iscrizioni chiuse.")
    existing = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == data.tournament_id, models.TournamentRegistration.club_id == data.club_id).first()
    if existing: raise HTTPException(status_code=400, detail="Sei già iscritto o in coda.")
    current_count = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == data.tournament_id, models.TournamentRegistration.is_waitlisted == False).count()
    is_waitlisted = current_count >= t.max_teams
    db.add(models.TournamentRegistration(tournament_id=data.tournament_id, club_id=data.club_id, is_waitlisted=is_waitlisted))
    db.commit()
    if is_waitlisted: return {"message": "Iscritti in LISTA D'ATTESA."}
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
    db.query(models.Match).filter(models.Match.tournament_id == t_id).delete()
    db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t_id).delete()
    db.delete(t)
    db.commit()
    return {"message": "Competizione eliminata."}

def calculate_standings(t_id: int, db: Session):
    regs = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t_id, models.TournamentRegistration.is_waitlisted == False).all()
    stats = {}
    for r in regs:
        club = db.query(models.Club).filter(models.Club.id == r.club_id).first()
        if club: stats[r.club_id] = {"club_id": club.id, "name": club.name, "points": 0, "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "gd": 0}
    matches = db.query(models.Match).filter(models.Match.tournament_id == t_id, models.Match.is_played == True, models.Match.phase == "regular").all()
    for m in matches:
        if m.home_team_id in stats and m.away_team_id in stats:
            stats[m.home_team_id]["played"] += 1; stats[m.away_team_id]["played"] += 1
            stats[m.home_team_id]["gf"] += m.home_score; stats[m.home_team_id]["ga"] += m.away_score
            stats[m.away_team_id]["gf"] += m.away_score; stats[m.away_team_id]["ga"] += m.home_score
            if m.home_score > m.away_score: stats[m.home_team_id]["points"] += 3; stats[m.home_team_id]["won"] += 1; stats[m.away_team_id]["lost"] += 1
            elif m.home_score < m.away_score: stats[m.away_team_id]["points"] += 3; stats[m.away_team_id]["won"] += 1; stats[m.home_team_id]["lost"] += 1
            else:
                stats[m.home_team_id]["points"] += 1; stats[m.away_team_id]["points"] += 1
                stats[m.home_team_id]["drawn"] += 1; stats[m.away_team_id]["drawn"] += 1
    for cid, s in stats.items(): s["gd"] = s["gf"] - s["ga"]
    return sorted(stats.values(), key=lambda x: (x["points"], x["gd"], x["gf"]), reverse=True)

@app.get("/api/tournaments/{t_id}/standings")
def api_get_standings(t_id: int, db: Session = Depends(get_db)): return calculate_standings(t_id, db)

@app.post("/api/admin/generate-next-phase")
def generate_next_phase(data: CalendarGenerate, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.id == data.tournament_id).first()
    matches = db.query(models.Match).filter(models.Match.tournament_id == t.id).all()
    phase_order = ["sedicesimi", "ottavi", "quarti", "semifinali", "finale"]
    current_phase = "regular"
    for m in matches:
        if m.phase in phase_order:
            if phase_order.index(m.phase) >= (phase_order.index(current_phase) if current_phase in phase_order else -1): current_phase = m.phase
    advancing_teams = []
    next_phase_name = ""

    if current_phase == "regular":
        if t.playoff_teams not in [2, 4, 8, 16, 32]: raise HTTPException(status_code=400, detail="Numero qualificate non valido.")
        standings = calculate_standings(t.id, db)
        if len(standings) < t.playoff_teams: raise HTTPException(status_code=400, detail="Squadre insufficienti.")
        for s in standings[:t.playoff_teams]: advancing_teams.append(s["club_id"])
        if t.playoff_teams == 32: next_phase_name = "sedicesimi"
        elif t.playoff_teams == 16: next_phase_name = "ottavi"
        elif t.playoff_teams == 8: next_phase_name = "quarti"
        elif t.playoff_teams == 4: next_phase_name = "semifinali"
        elif t.playoff_teams == 2: next_phase_name = "finale"
        pairings = [(advancing_teams[i], advancing_teams[len(advancing_teams) - 1 - i]) for i in range(len(advancing_teams) // 2)]
    else:
        current_phase_matches = [m for m in matches if m.phase == current_phase]
        for m in current_phase_matches:
            if not m.is_played: raise HTTPException(status_code=400, detail="Completa prima i referti del turno corrente.")
            if m.home_score == m.away_score: raise HTTPException(status_code=400, detail="I pareggi non sono ammessi nei playoff.")
            advancing_teams.append(m.home_team_id if m.home_score > m.away_score else m.away_team_id)
        n = len(advancing_teams)
        if n == 16: next_phase_name = "ottavi"
        elif n == 8: next_phase_name = "quarti"
        elif n == 4: next_phase_name = "semifinali"
        elif n == 2: next_phase_name = "finale"
        elif n == 1: raise HTTPException(status_code=400, detail="Il torneo è concluso!")
        pairings = [(advancing_teams[i], advancing_teams[i+1]) for i in range(0, n, 2)]

    current_date = datetime.strptime(data.start_date, "%Y-%m-%d")
    while current_date.weekday() not in data.play_days: current_date += timedelta(days=1)
    play_date_str = current_date.strftime("%Y-%m-%d")

    db.query(models.Match).filter(models.Match.tournament_id == t.id, models.Match.phase == next_phase_name).delete()
    new_matches = [models.Match(tournament_id=t.id, home_team_id=h, away_team_id=a, matchday=100, play_date=play_date_str, phase=next_phase_name) for h, a in pairings]
    db.add_all(new_matches)
    db.commit()
    return {"message": f"Turno {next_phase_name.upper()} generato!"}

# --- REFERTI ---
@app.get("/api/matches/pending/{club_id}")
def get_pending_matches(club_id: int, db: Session = Depends(get_db)):
    matches = db.query(models.Match).filter((models.Match.home_team_id == club_id) | (models.Match.away_team_id == club_id), models.Match.is_played == False).all()
    res = []
    for m in matches:
        t = db.query(models.Tournament).filter(models.Tournament.id == m.tournament_id).first()
        home = db.query(models.Club).filter(models.Club.id == m.home_team_id).first()
        away = db.query(models.Club).filter(models.Club.id == m.away_team_id).first()
        res.append({"match_id": m.id, "tournament_name": t.name if t else "Torneo", "phase": m.phase, "home_team": home.name if home else "TBD", "away_team": away.name if away else "TBD"})
    return res

@app.post("/api/matches/submit")
def submit_match(data: MatchSubmit, db: Session = Depends(get_db)):
    m = db.query(models.Match).filter(models.Match.id == data.match_id).first()
    if m.is_played: raise HTTPException(status_code=400, detail="Referto già inviato.")
    m.home_score = data.home_score; m.away_score = data.away_score; m.is_played = True
    for stat in data.player_stats:
        p = db.query(models.User).filter(models.User.id == stat.player_id).first()
        if p: p.goals += stat.goals; p.assists += stat.assists; p.matches_played += 1
    db.commit()
    return {"message": "Referto confermato!"}

@app.post("/api/admin/simulate-matches/{t_id}")
def simulate_matches(t_id: int, db: Session = Depends(get_db)):
    matches = db.query(models.Match).filter(models.Match.tournament_id == t_id, models.Match.is_played == False).all()
    for m in matches:
        m.home_score = random.randint(0, 4); m.away_score = random.randint(0, 4)
        if m.phase != "regular" and m.home_score == m.away_score: m.home_score += 1
        m.is_played = True
    db.commit()
    return {"message": "Simulazione completata!"}

# --- DRAFT ---
@app.post("/api/draft/signup")
def draft_signup(data: DraftSignup, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    user.draft_role = data.role
    db.commit()
    return {"message": f"Candidatura come {data.role} registrata con successo!"}

@app.get("/api/draft/players")
def get_draft_players(db: Session = Depends(get_db)):
    players = db.query(models.User).filter(models.User.draft_role != None, models.User.club_id == None).all()
    return [{"id": p.id, "gamertag": p.gamertag, "role": p.draft_role} for p in players]

@app.post("/api/draft/assign")
def draft_assign(data: PlayerAction, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.player_id).first()
    user.club_id = data.club_id; user.draft_role = None
    db.commit()
    return {"message": f"Giocatore {user.gamertag} ingaggiato!"}

# --- NUOVO: API TOP STATISTICHE (CAPOCANNONIERE E ASSISTMAN) ---
@app.get("/api/stats/top-players")
def get_top_players(db: Session = Depends(get_db)):
    # Prende solo chi ha giocato almeno una partita o ha fatto gol/assist
    users = db.query(models.User).filter((models.User.goals > 0) | (models.User.assists > 0) | (models.User.matches_played > 0)).all()
    
    # Ordina: chi ha più gol, a parità di gol vince chi ha giocato MENO partite
    top_scorers = sorted(users, key=lambda x: (x.goals, -x.matches_played), reverse=True)[:10]
    top_assists = sorted(users, key=lambda x: (x.assists, -x.matches_played), reverse=True)[:10]
    
    def format_player(p):
        club = db.query(models.Club).filter(models.Club.id == p.club_id).first() if p.club_id else None
        return {
            "gamertag": p.gamertag,
            "club_name": club.name if club else "Free Agent",
            "goals": p.goals,
            "assists": p.assists,
            "matches_played": p.matches_played
        }
    
    return {
        "top_scorers": [format_player(p) for p in top_scorers if p.goals > 0],
        "top_assists": [format_player(p) for p in top_assists if p.assists > 0]
    }

# --- FRONTEND ---
@app.get("/")
def read_root():
    if os.path.exists("index.html"): return FileResponse("index.html")
    return {"message": "Home page non trovata."}
app.mount("/", StaticFiles(directory=".", html=True), name="static")
