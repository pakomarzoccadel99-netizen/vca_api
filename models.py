from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True) # Gamertag / EA ID
    password = Column(String)
    role = Column(String, default="user") # "admin", "event_admin", "captain", "vice_captain", "draft_captain", "user"
    can_access_draft = Column(Boolean, default=False)

    club = relationship("Club", back_populates="owner", uselist=False)
    player_profile = relationship("Player", back_populates="user", uselist=False)

class Club(Base):
    __tablename__ = "clubs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    formation = Column(String, default="3-1-4-2")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    owner = relationship("User", back_populates="club")
    players = relationship("Player", back_populates="club")
    tournaments = relationship("TournamentRegistration", back_populates="club")

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True, index=True)
    gamertag = Column(String, unique=True, index=True)
    role = Column(String) # "ATT", "CC", "DIF", "POR", "ES", "ED"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    
    # Statistiche di campionato
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    matches_played = Column(Integer, default=0)

    club = relationship("Club", back_populates="players")
    user = relationship("User", back_populates="player_profile")

class Tournament(Base):
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    format_type = Column(String) # "league", "group", "swiss", "draft"
    rules = Column(Text, default="Regolamento standard VCA.")
    status = Column(String, default="open") 

    matches = relationship("Match", back_populates="tournament")
    registrations = relationship("TournamentRegistration", back_populates="tournament")

class TournamentRegistration(Base):
    __tablename__ = "tournament_registrations"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"))
    club_id = Column(Integer, ForeignKey("clubs.id"))
    points_adjustment = Column(Integer, default=0) 

    tournament = relationship("Tournament", back_populates="registrations")
    club = relationship("Club", back_populates="tournaments")

class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"))
    stage = Column(String, default="regular") 
    home_team_id = Column(Integer, ForeignKey("clubs.id"))
    away_team_id = Column(Integer, ForeignKey("clubs.id"))
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False) 

    tournament = relationship("Tournament", back_populates="matches")
    home_team = relationship("Club", foreign_keys=[home_team_id])
    away_team = relationship("Club", foreign_keys=[away_team_id])
    reports = relationship("MatchReport", back_populates="match")

class MatchReport(Base):
    __tablename__ = "match_reports"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    player_id = Column(Integer, ForeignKey("players.id"))
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)

    match = relationship("Match", back_populates="reports")
    player = relationship("Player")