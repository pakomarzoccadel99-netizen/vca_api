from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import SessionLocal, engine
import models
import random
import json

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="VCA Group eSports API")

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

# --- SCHEMI ---
class UserRegister(BaseModel):
    email: str
    gamertag: str
    password: str

class UserLogin(BaseModel):
    login_id: str # Può inserire Email o Gamertag
    password: str

class RoleUpdate(BaseModel):
    user_id: int
    new_role: str

class ClubCreate(BaseModel):
    name: str
    formation: str = "3-1-4-2"
    owner_id: int

class ClubRosterUpdate(BaseModel):
    club_id: int
    user_id: int

class TournamentCreate(BaseModel):
    name: str
    format_type: str 
    rules: str = "Regolamento ufficiale."

class TournamentRegister(BaseModel):
    tournament_id: int
    club_id: int

class PointsAdjust(BaseModel):
    tournament_id: int
    club_id: int
    points_delta: int

class StatItem(BaseModel):
    player_id: int
    goals: int = 0
    assists: int = 0

class MatchSubmit(BaseModel):
    tournament_id: int
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    player_stats: list[StatItem] = [] # Statistiche dettagliate dei giocatori per il campionato

class DraftPermission(BaseModel):
    user_id: int
    can_access: bool

class PlayerSignup(BaseModel):
    gamertag: str
    role: str
    user_id: int

class DraftPick(BaseModel):
    player_id: int
    club_id: int

# --- WEBSOCKETS PER DRAFT LIVE ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/draft")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- AUTENTICAZIONE ---
@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email già registrata")
    if db.query(models.User).filter(models.User.username == data.gamertag).first():
        raise HTTPException(status_code=400, detail="Gamertag / EA ID già esistente")
    
    new_user = models.User(email=data.email, username=data.gamertag, password=data.password, role="user")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Crea automaticamente anche il profilo player collegato per le statistiche
    new_player = models.Player(gamertag=data.gamertag, role="CC", user_id=new_user.id, club_id=None)
    db.add(new_player)
    db.commit()

    return {"message": "Registrazione completata", "user_id": new_user.id, "role": new_user.role}

@app.post("/api/auth/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    # Permette il login sia tramite email che tramite gamertag
    user = db.query(models.User).filter(
        ((models.User.email == data.login_id) | (models.User.username == data.login_id)) & 
        (models.User.password == data.password)
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    
    club = db.query(models.Club).filter(models.Club.owner_id == user.id).first()
    return {
        "user_id": user.id,
        "gamertag": user.username,
        "email": user.email, # Restituita ma visualizzabile solo dagli admin nel frontend
        "role": user.role,
        "can_access_draft": user.can_access_draft,
        "club_id": club.id if club else None,
        "club_name": club.name if club else None
    }

# --- GESTIONE UTENTI E RUOLI (SOLO ADMIN) ---
@app.get("/api/admin/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    out = []
    for u in users:
        club = db.query(models.Club).filter(models.Club.owner_id == u.id).first()
        out.append({
            "id": u.id,
            "gamertag": u.username,
            "email": u.email, # Visibile solo agli admin
            "role": u.role,
            "club_name": club.name if club else "Nessun Club"
        })
    return out

@app.post("/api/admin/set-role")
def set_user_role(data: RoleUpdate, db: Session = Depends(get_db)):
    valid_roles = ["admin", "event_admin", "captain", "vice_captain", "draft_captain", "user"]
    if data.new_role not in valid_roles:
        raise HTTPException(status_code=400, detail="Ruolo non valido")

    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    user.role = data.new_role
    db.commit()
    return {"message": f"Ruolo di {user.username} aggiornato a {data.new_role}"}

# --- AREA PERSONALE UTENTE ---
@app.get("/api/user/profile/{user_id}")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    player = db.query(models.Player).filter(models.Player.user_id == user.id).first()
    club = db.query(models.Club).filter(models.Club.owner_id == user.id).first()
    
    club_name = "Nessun Club"
    if club:
        club_name = club.name
    elif player and player.club_id:
        c = db.query(models.Club).filter(models.Club.id == player.club_id).first()
        if c: club_name = c.name

    return {
        "gamertag": user.username,
        "email": user.email,
        "role": user.role,
        "club_name": club_name,
        "stats": {
            "goals": player.goals if player else 0,
            "assists": player.assists if player else 0,
            "matches_played": player.matches_played if player else 0
        }
    }

# --- GESTIONE CLUB E BACHECA PUBBLICA ---
@app.post("/api/club/create")
def create_club(data: ClubCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.owner_id).first()
    if not user or (user.role != "captain" and user.role != "admin"):
        raise HTTPException(status_code=403, detail="Solo i capitani o gli admin possono creare un club.")

    existing_club = db.query(models.Club).filter(models.Club.owner_id == data.owner_id).first()
    if existing_club:
        raise HTTPException(status_code=400, detail="Hai già creato un club!")

    new_club = models.Club(name=data.name, formation=data.formation, owner_id=data.owner_id)
    db.add(new_club)
    db.commit()
    db.refresh(new_club)
    return {"message": "Club creato con successo!", "club_id": new_club.id}

@app.get("/api/club/details/{club_id}")
def get_club_details(club_id: int, db: Session = Depends(get_db)):
    club = db.query(models.Club).filter(models.Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="Club non trovato")
    
    players = db.query(models.Player).filter(models.Player.club_id == club.id).all()
    return {
        "id": club.id,
        "name": club.name,
        "formation": club.formation,
        "players": [{
            "id": p.id,
            "gamertag": p.gamertag,
            "role": p.role,
            "user_id": p.user_id,
            "goals": p.goals,
            "assists": p.assists,
            "matches_played": p.matches_played
        } for p in players]
    }

@app.post("/api/club/add-player")
def add_player_to_club(data: ClubRosterUpdate, db: Session = Depends(get_db)):
    target_user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utente non trovato nel sistema.")

    player = db.query(models.Player).filter(models.Player.user_id == target_user.id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Profilo giocatore non trovato.")
    
    if player.club_id is not None:
        raise HTTPException(status_code=400, detail="Questo utente fa già parte di un club.")

    player.club_id = data.club_id
    db.commit()
    return {"message": f"Utente {target_user.username} aggiunto alla rosa con successo!"}

@app.post("/api/club/remove-player")
def remove_player_from_club(data: ClubRosterUpdate, db: Session = Depends(get_db)):
    player = db.query(models.Player).filter(models.Player.club_id == data.club_id, models.Player.user_id == data.user_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Giocatore non trovato nella tua rosa.")
    
    player.club_id = None
    db.commit()
    return {"message": "Giocatore rimosso dalla rosa."}

@app.get("/api/users/list")
def list_all_registered_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [{"id": u.id, "gamertag": u.username, "role": u.role} for u in users]

# --- REFERTI CAMPIONATO & AGGIORNAMENTO STATISTICHE ---
@app.post("/api/matches/submit-league")
def submit_league_match(data: MatchSubmit, db: Session = Depends(get_db)):
    match = models.Match(
        tournament_id=data.tournament_id,
        stage="campionato",
        home_team_id=data.home_team_id,
        away_team_id=data.away_team_id,
        home_score=data.home_score,
        away_score=data.away_score,
        is_verified=False 
    )
    db.add(match)
    db.commit()
    db.refresh(match)

    # Salvataggio temporaneo delle statistiche nel referto o report match
    for st in data.player_stats:
        rep = models.MatchReport(
            match_id=match.id,
            player_id=st.player_id,
            goals=st.goals,
            assists=st.assists
        )
        db.add(rep)
    db.commit()

    return {"message": "Referto campionato inviato. In attesa di approvazione dall'Admin."}

@app.put("/api/matches/{match_id}/verify")
def verify_match(match_id: int, db: Session = Depends(get_db)):
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    
    if match.is_verified:
        raise HTTPException(status_code=400, detail="Partita già approvata in precedenza.")

    tournament = db.query(models.Tournament).filter(models.Tournament.id == match.tournament_id).first()
    
    # VERIFICA CRITICA: Solo nei campionati (formato 'league') si aggiornano le statistiche personali!
    is_league = tournament and tournament.format_type.lower() == "league"

    match.is_verified = True

    if is_league:
        reports = db.query(models.MatchReport).filter(models.MatchReport.match_id == match.id).all()
        for rep in reports:
            player = db.query(models.Player).filter(models.Player.id == rep.player_id).first()
            if player:
                player.goals += rep.goals
                player.assists += rep.assists
                player.matches_played += 1

    db.commit()
    return {"message": "Partita approvata! Statistiche di campionato aggiornate in automatico."}

# --- ISCRIZIONE GIOCATORI E LOGICA DRAFT ---
@app.post("/api/draft/signup-player")
def signup_player(data: PlayerSignup, db: Session = Depends(get_db)):
    valid_roles = ["ATT", "CC", "DIF", "POR", "ES", "ED"]
    role_upper = data.role.upper()
    if role_upper not in valid_roles:
        raise HTTPException(status_code=400, detail="Ruolo non valido")

    player = db.query(models.Player).filter(models.Player.user_id == data.user_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Profilo giocatore non trovato")
    
    player.role = role_upper
    player.club_id = None
    db.commit()
    return {"message": "Ti sei candidato con successo al pool Draft!"}

@app.get("/api/draft/random-players/{role}")
def get_random_players(role: str, db: Session = Depends(get_db)):
    available_players = db.query(models.Player).filter(
        models.Player.role == role.upper(),
        models.Player.club_id == None
    ).all()
    if not available_players:
        raise HTTPException(status_code=404, detail="Nessun giocatore disponibile")
    sample_size = min(5, len(available_players))
    return {"role": role.upper(), "options": [{"id": p.id, "gamertag": p.gamertag, "role": p.role} for p in available_players]}

@app.post("/api/draft/assign")
async def assign_player(pick: DraftPick, db: Session = Depends(get_db)):
    player = db.query(models.Player).filter(models.Player.id == pick.player_id).first()
    if not player or player.club_id is not None:
        raise HTTPException(status_code=400, detail="Giocatore non valido o già assegnato")
    
    player.club_id = pick.club_id
    db.commit()

    await manager.broadcast(json.dumps({
        "action": "drafted",
        "gamertag": player.gamertag,
        "role": player.role
    }))
    return {"message": "Assegnazione completata"}

@app.get("/api/draft/summary")
def get_draft_summary(db: Session = Depends(get_db)):
    clubs = db.query(models.Club).all()
    summary = []
    for club in clubs:
        players = db.query(models.Player).filter(models.Player.club_id == club.id).all()
        roles_count = {"ATT": 0, "CC": 0, "DIF": 0, "POR": 0, "ES": 0, "ED": 0}
        player_list = []
        for p in players:
            if p.role in roles_count:
                roles_count[p.role] += 1
            player_list.append({"gamertag": p.gamertag, "role": p.role, "goals": p.goals, "assists": p.assists, "matches_played": p.matches_played})
            
        is_complete = all(count > 0 for count in roles_count.values())
        summary.append({
            "club_name": club.name,
            "formation": club.formation,
            "is_complete": is_complete,
            "roles_breakdown": roles_count,
            "players": player_list
        })
    return summary

# --- COMPETIZIONI ED ISCRIZIONI ---
@app.get("/api/tournaments")
def get_tournaments(db: Session = Depends(get_db)):
    tournaments = db.query(models.Tournament).all()
    out = []
    for t in tournaments:
        reg_count = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t.id).count()
        out.append({
            "id": t.id,
            "name": t.name,
            "format_type": t.format_type,
            "rules": t.rules,
            "status": t.status,
            "teams_count": reg_count
        })
    return out

@app.post("/api/tournaments")
def create_tournament(t: TournamentCreate, db: Session = Depends(get_db)):
    new_t = models.Tournament(name=t.name, format_type=t.format_type.lower(), rules=t.rules, status="open")
    db.add(new_t)
    db.commit()
    db.refresh(new_t)
    return {"message": "Competizione creata!", "id": new_t.id}

@app.post("/api/tournaments/register")
def register_team_to_tournament(reg: TournamentRegister, db: Session = Depends(get_db)):
    existing = db.query(models.TournamentRegistration).filter(
        models.TournamentRegistration.tournament_id == reg.tournament_id,
        models.TournamentRegistration.club_id == reg.club_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Squadra già iscritta")
    
    entry = models.TournamentRegistration(tournament_id=reg.tournament_id, club_id=reg.club_id)
    db.add(entry)
    db.commit()
    return {"message": "Iscrizione completata con successo!"}

@app.post("/api/admin/adjust-points")
def adjust_points(data: PointsAdjust, db: Session = Depends(get_db)):
    entry = db.query(models.TournamentRegistration).filter(
        models.TournamentRegistration.tournament_id == data.tournament_id,
        models.TournamentRegistration.club_id == data.club_id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Iscrizione non trovata")
    entry.points_adjustment += data.points_delta
    db.commit()
    return {"message": f"Punti aggiornati. Variazione totale: {entry.points_adjustment}"}

@app.post("/api/admin/draft-permissions")
def set_draft_permission(data: DraftPermission, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    user.can_access_draft = data.can_access
    db.commit()
    return {"message": f"Permesso Draft aggiornato per {user.username}"}

@app.get("/api/tournaments/{t_id}/standings")
def get_tournament_standings(t_id: int, db: Session = Depends(get_db)):
    regs = db.query(models.TournamentRegistration).filter(models.TournamentRegistration.tournament_id == t_id).all()
    standings = {}
    for r in regs:
        club = db.query(models.Club).filter(models.Club.id == r.club_id).first()
        standings[r.club_id] = {
            "name": club.name if club else f"Team {r.club_id}",
            "points": r.points_adjustment,
            "goals_for": 0,
            "goals_against": 0,
            "goal_diff": 0,
            "played": 0
        }

    matches = db.query(models.Match).filter(models.Match.tournament_id == t_id, models.Match.is_verified == True).all()
    for m in matches:
        if m.home_team_id in standings and m.away_team_id in standings:
            standings[m.home_team_id]["played"] += 1
            standings[m.away_team_id]["played"] += 1
            standings[m.home_team_id]["goals_for"] += m.home_score
            standings[m.home_team_id]["goals_against"] += m.away_score
            standings[m.away_team_id]["goals_for"] += m.away_score
            standings[m.away_team_id]["goals_against"] += m.home_score

            if m.home_score > m.away_score:
                standings[m.home_team_id]["points"] += 3
            elif m.home_score < m.away_score:
                standings[m.away_team_id]["points"] += 3
            else:
                standings[m.home_team_id]["points"] += 1
                standings[m.away_team_id]["points"] += 1

    res = list(standings.values())
    for team in res:
        team["goal_diff"] = team["goals_for"] - team["goals_against"]
    res.sort(key=lambda x: (x["points"], x["goal_diff"]), reverse=True)
    return res
from fastapi.responses import FileResponse
import os

@app.get("/")
def read_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "VCA Group eSports API Online. index.html non trovato nella cartella."}