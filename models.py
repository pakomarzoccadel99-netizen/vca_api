from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    gamertag = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, default="user")
    club_id = Column(Integer, nullable=True)
    draft_role = Column(String, nullable=True)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    matches_played = Column(Integer, default=0)

class Club(Base):
    __tablename__ = "clubs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    formation = Column(String)
    owner_id = Column(Integer)

class Tournament(Base):
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    format_type = Column(String)
    rules = Column(String)
    max_teams = Column(Integer, default=16) # Nuovo: Limite squadre
    matchdays = Column(Integer, default=1)  # Nuovo: 1 = Andata, 2 = Andata e Ritorno

class TournamentRegistration(Base):
    __tablename__ = "tournament_registrations"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer)
    club_id = Column(Integer)

# Nuova tabella per il calendario automatico
class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer)
    home_team_id = Column(Integer)
    away_team_id = Column(Integer)
    matchday = Column(Integer) # Giornata (1, 2, 3...)
    play_date = Column(String) # Data calcolata in automatico (es. 2026-09-08)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    is_played = Column(Boolean, default=False)
