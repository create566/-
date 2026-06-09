"""数据存储层 — SQLAlchemy + MySQL（生产）+ JSON（开发回退）"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from loguru import logger

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Boolean, JSON, Float, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

# ==================== SQLAlchemy 模型 ====================

Base = declarative_base()


class System(Base):
    __tablename__ = "systems"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    system_type = Column(String(32), default="web_service")
    status = Column(String(16), default="active")
    endpoint = Column(String(512), default="")
    auth = Column(JSON, nullable=True)
    detectors = Column(JSON, default=list)
    check_interval_seconds = Column(Integer, default=60)
    alert_enabled = Column(Boolean, default=True)
    health_score = Column(Integer, default=100)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String(64), primary_key=True)
    system_id = Column(String(64), nullable=False, index=True)
    system_name = Column(String(128), nullable=True)
    severity = Column(String(16), nullable=False)
    status = Column(String(16), default="open")
    title = Column(String(256), nullable=False)
    message = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    report = Column(Text, nullable=True)
    anomalies = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class CheckHistory(Base):
    __tablename__ = "check_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(String(64), nullable=False, index=True)
    detector_name = Column(String(64), nullable=False)
    metric_name = Column(String(64), nullable=False)
    metric_value = Column(Float, nullable=True)
    severity = Column(String(16), default="normal")
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True)
    chat_source = Column(String(16), nullable=False, default="web")
    source_id = Column(String(128), nullable=False, index=True)
    title = Column(String(256), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class MemoryFact(Base):
    __tablename__ = "memory_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    key = Column(String(256), nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(64), default="general")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==================== 引擎和会话管理 ====================

_engine = None
_SessionLocal = None


def init_db(host: str, port: int, user: str, password: str, name: str):
    """初始化数据库引擎"""
    global _engine, _SessionLocal
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
    _engine = create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)
    logger.info(f"数据库已连接: {host}:{port}/{name}")


def get_session() -> Session:
    """获取数据库会话"""
    return _SessionLocal()


@asynccontextmanager
async def get_db():
    """异步上下文管理器获取数据库会话"""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ==================== JSON 回退模式 ====================

DATA_DIR = Path("./data")
SYSTEMS_FILE = DATA_DIR / "systems.json"
INCIDENTS_FILE = DATA_DIR / "incidents.json"
HISTORY_FILE = DATA_DIR / "check_history.json"
CHAT_SESSIONS_FILE = DATA_DIR / "chat_sessions.json"
CHAT_MESSAGES_FILE = DATA_DIR / "chat_messages.json"
MEMORY_FACTS_FILE = DATA_DIR / "memory_facts.json"

_json_mode = False


def is_json_mode() -> bool:
    return _json_mode


def _ensure():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in [SYSTEMS_FILE, INCIDENTS_FILE, HISTORY_FILE, CHAT_SESSIONS_FILE, CHAT_MESSAGES_FILE, MEMORY_FACTS_FILE]:
        if not f.exists():
            f.write_text("[]", encoding="utf-8")


def _read_json(file: Path) -> list:
    _ensure()
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _write_json(file: Path, data: list):
    _ensure()
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ==================== 系统管理 ====================

def list_systems(status: Optional[str] = None) -> List[Dict]:
    if _engine is None:
        # JSON 回退模式
        global _json_mode
        _json_mode = True
        systems = _read_json(SYSTEMS_FILE)
        if status:
            systems = [s for s in systems if s.get("status") == status]
        return systems

    with get_session() as session:
        query = session.query(System)
        if status:
            query = query.filter(System.status == status)
        return [_system_to_dict(s) for s in query.all()]


def get_system(system_id: str) -> Optional[Dict]:
    if _engine is None:
        for s in _read_json(SYSTEMS_FILE):
            if s["id"] == system_id:
                return s
        return None

    with get_session() as session:
        s = session.query(System).filter(System.id == system_id).first()
        return _system_to_dict(s) if s else None


def create_system(data: Dict) -> Dict:
    if _engine is None:
        systems = _read_json(SYSTEMS_FILE)
        now = datetime.now(timezone.utc).isoformat()
        system = {
            "id": data.get("id", ""),
            "name": data["name"],
            "system_type": data.get("system_type", "web_service"),
            "status": "active",
            "endpoint": data.get("endpoint", ""),
            "auth": data.get("auth"),
            "detectors": data.get("detectors", []),
            "check_interval_seconds": data.get("check_interval_seconds", 60),
            "alert_enabled": data.get("alert_enabled", True),
            "health_score": 100,
            "last_checked_at": None,
            "created_at": now,
            "updated_at": now,
        }
        systems.append(system)
        _write_json(SYSTEMS_FILE, systems)
        logger.info(f"系统已注册( JSON): {data['name']} ({system['id']})")
        return system

    now = datetime.now(timezone.utc)
    system = System(
        id=data.get("id", ""),
        name=data["name"],
        system_type=data.get("system_type", "web_service"),
        status="active",
        endpoint=data.get("endpoint", ""),
        auth=data.get("auth"),
        detectors=data.get("detectors", []),
        check_interval_seconds=data.get("check_interval_seconds", 60),
        alert_enabled=data.get("alert_enabled", True),
        health_score=100,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )
    with get_session() as session:
        session.add(system)
        session.commit()
        result = _system_to_dict(system)
    logger.info(f"系统已注册(MySQL): {data['name']} ({system.id})")
    return result


def update_system(system_id: str, data: Dict) -> Optional[Dict]:
    if _engine is None:
        systems = _read_json(SYSTEMS_FILE)
        for i, s in enumerate(systems):
            if s["id"] == system_id:
                s.update({k: v for k, v in data.items() if v is not None})
                s["updated_at"] = datetime.now(timezone.utc).isoformat()
                systems[i] = s
                _write_json(SYSTEMS_FILE, systems)
                return s
        return None

    with get_session() as session:
        s = session.query(System).filter(System.id == system_id).first()
        if not s:
            return None
        for key, value in data.items():
            if value is not None and hasattr(s, key):
                setattr(s, key, value)
        s.updated_at = datetime.now(timezone.utc)
        session.commit()
        return _system_to_dict(s)


def update_system_status(system_id: str, status: str) -> Optional[Dict]:
    return update_system(system_id, {"status": status})


def update_health_score(system_id: str, score: int):
    update_system(system_id, {"health_score": score, "last_checked_at": datetime.now(timezone.utc).isoformat()})


def delete_system(system_id: str) -> bool:
    if _engine is None:
        systems = _read_json(SYSTEMS_FILE)
        filtered = [s for s in systems if s["id"] != system_id]
        if len(filtered) < len(systems):
            _write_json(SYSTEMS_FILE, filtered)
            return True
        return False

    with get_session() as session:
        s = session.query(System).filter(System.id == system_id).first()
        if s:
            session.delete(s)
            return True
        return False


# ==================== 故障记录 ====================

def create_incident(data: Dict) -> Dict:
    if _engine is None:
        incidents = _read_json(INCIDENTS_FILE)
        incidents.insert(0, data)
        if len(incidents) > 500:
            incidents = incidents[:500]
        _write_json(INCIDENTS_FILE, incidents)
        return data

    now = datetime.now(timezone.utc)
    incident = Incident(
        id=data.get("id", ""),
        system_id=data.get("system_id", ""),
        system_name=data.get("system_name", ""),
        severity=data.get("severity", "warning"),
        status=data.get("status", "open"),
        title=data.get("title", ""),
        message=data.get("message"),
        root_cause=data.get("root_cause"),
        report=data.get("report"),
        anomalies=data.get("anomalies", []),
        created_at=now,
    )
    with get_session() as session:
        session.add(incident)
        session.commit()
        result = _incident_to_dict(incident)
    return result


def list_incidents(system_id: Optional[str] = None, severity: Optional[str] = None,
                   status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    if _engine is None:
        incidents = _read_json(INCIDENTS_FILE)
        if system_id:
            incidents = [i for i in incidents if i["system_id"] == system_id]
        if severity:
            incidents = [i for i in incidents if i["severity"] == severity]
        if status:
            incidents = [i for i in incidents if i.get("status") == status]
        return incidents[:limit]

    with get_session() as session:
        query = session.query(Incident)
        if system_id:
            query = query.filter(Incident.system_id == system_id)
        if severity:
            query = query.filter(Incident.severity == severity)
        if status:
            query = query.filter(Incident.status == status)
        query = query.order_by(Incident.created_at.desc()).limit(limit)
        return [_incident_to_dict(i) for i in query.all()]


def get_incident(incident_id: str) -> Optional[Dict]:
    if _engine is None:
        for i in _read_json(INCIDENTS_FILE):
            if i["id"] == incident_id:
                return i
        return None

    with get_session() as session:
        inc = session.query(Incident).filter(Incident.id == incident_id).first()
        return _incident_to_dict(inc) if inc else None


def update_incident_status(incident_id: str, status: str) -> Optional[Dict]:
    if _engine is None:
        incidents = _read_json(INCIDENTS_FILE)
        for i, inc in enumerate(incidents):
            if inc["id"] == incident_id:
                inc["status"] = status
                if status == "resolved":
                    inc["resolved_at"] = datetime.now(timezone.utc).isoformat()
                elif status == "acknowledged":
                    inc["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
                incidents[i] = inc
                _write_json(INCIDENTS_FILE, incidents)
                return inc
        return None

    with get_session() as session:
        inc = session.query(Incident).filter(Incident.id == incident_id).first()
        if not inc:
            return None
        inc.status = status
        if status == "resolved":
            inc.resolved_at = datetime.now(timezone.utc)
        elif status == "acknowledged":
            inc.acknowledged_at = datetime.now(timezone.utc)
        session.commit()
        return _incident_to_dict(inc)


def update_incident_field(incident_id: str, updates: dict) -> Optional[Dict]:
    if _engine is None:
        incidents = _read_json(INCIDENTS_FILE)
        for i, inc in enumerate(incidents):
            if inc.get("id") == incident_id:
                inc.update(updates)
                incidents[i] = inc
                _write_json(INCIDENTS_FILE, incidents)
                return inc
        return None

    with get_session() as session:
        inc = session.query(Incident).filter(Incident.id == incident_id).first()
        if not inc:
            return None
        for key, value in updates.items():
            if hasattr(inc, key):
                setattr(inc, key, value)
        session.commit()
        return _incident_to_dict(inc)


def delete_incident(incident_id: str) -> bool:
    if _engine is None:
        incidents = _read_json(INCIDENTS_FILE)
        before = len(incidents)
        incidents = [i for i in incidents if i.get("id") != incident_id]
        _write_json(INCIDENTS_FILE, incidents)
        return len(incidents) < before

    with get_session() as session:
        inc = session.query(Incident).filter(Incident.id == incident_id).first()
        if not inc:
            return False
        session.delete(inc)
        session.commit()
        return True


# ==================== 检测历史 ====================

def save_check_history(results: List[Dict]):
    if _engine is None:
        history = _read_json(HISTORY_FILE)
        for r in results:
            history.append({
                "system_id": r.get("system_id", ""),
                "detector_name": r.get("detector_name", ""),
                "metric_name": r.get("metric_name", ""),
                "metric_value": r.get("current_value", 0),
                "severity": r.get("severity", "normal"),
                "checked_at": r.get("timestamp", datetime.now(timezone.utc).isoformat()),
            })
        if len(history) > 10000:
            history = history[-10000:]
        _write_json(HISTORY_FILE, history)
        return

    with get_session() as session:
        for r in results:
            history = CheckHistory(
                system_id=r.get("system_id", ""),
                detector_name=r.get("detector_name", ""),
                metric_name=r.get("metric_name", ""),
                metric_value=r.get("current_value", 0),
                severity=r.get("severity", "normal"),
                checked_at=datetime.now(timezone.utc),
            )
            session.add(history)
        session.commit()


def get_check_history(system_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
    if _engine is None:
        history = _read_json(HISTORY_FILE)
        if system_id:
            history = [h for h in history if h["system_id"] == system_id]
        return history[-limit:]

    with get_session() as session:
        query = session.query(CheckHistory)
        if system_id:
            query = query.filter(CheckHistory.system_id == system_id)
        query = query.order_by(CheckHistory.checked_at.desc()).limit(limit)
        return [_history_to_dict(h) for h in query.all()]


# ==================== 聊天会话 ====================

def create_session(data: Dict) -> Dict:
    if _engine is None:
        sessions = _read_json(CHAT_SESSIONS_FILE)
        now = datetime.now(timezone.utc).isoformat()
        session = {
            "id": data.get("id", ""),
            "chat_source": data.get("chat_source", "web"),
            "source_id": data.get("source_id", ""),
            "title": data.get("title", ""),
            "created_at": now,
            "updated_at": now,
        }
        sessions.append(session)
        _write_json(CHAT_SESSIONS_FILE, sessions)
        return session

    now = datetime.now(timezone.utc)
    s = ChatSession(
        id=data.get("id", ""),
        chat_source=data.get("chat_source", "web"),
        source_id=data.get("source_id", ""),
        title=data.get("title", ""),
        created_at=now,
        updated_at=now,
    )
    with get_session() as session:
        session.add(s)
        session.commit()
        return _chat_session_to_dict(s)


def get_chat_session(session_id: str) -> Optional[Dict]:
    if _engine is None:
        for s in _read_json(CHAT_SESSIONS_FILE):
            if s["id"] == session_id:
                return s
        return None

    with get_session() as session:
        s = session.query(ChatSession).filter(ChatSession.id == session_id).first()
        return _chat_session_to_dict(s) if s else None


def get_session_by_source(chat_source: str, source_id: str) -> Optional[Dict]:
    if _engine is None:
        for s in _read_json(CHAT_SESSIONS_FILE):
            if s["chat_source"] == chat_source and s["source_id"] == source_id:
                return s
        return None

    with get_session() as session:
        s = session.query(ChatSession).filter(
            ChatSession.chat_source == chat_source,
            ChatSession.source_id == source_id,
        ).first()
        return _chat_session_to_dict(s) if s else None


def update_session_title(session_id: str, title: str) -> Optional[Dict]:
    if _engine is None:
        sessions = _read_json(CHAT_SESSIONS_FILE)
        for i, s in enumerate(sessions):
            if s["id"] == session_id:
                s["title"] = title
                s["updated_at"] = datetime.now(timezone.utc).isoformat()
                sessions[i] = s
                _write_json(CHAT_SESSIONS_FILE, sessions)
                return s
        return None

    with get_session() as session:
        s = session.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not s:
            return None
        s.title = title
        s.updated_at = datetime.now(timezone.utc)
        session.commit()
        return _chat_session_to_dict(s)


def update_session_timestamp(session_id: str):
    if _engine is None:
        sessions = _read_json(CHAT_SESSIONS_FILE)
        for i, s in enumerate(sessions):
            if s["id"] == session_id:
                s["updated_at"] = datetime.now(timezone.utc).isoformat()
                sessions[i] = s
                _write_json(CHAT_SESSIONS_FILE, sessions)
                return
        return

    with get_session() as session:
        s = session.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            s.updated_at = datetime.now(timezone.utc)
            session.commit()


def list_sessions(limit: int = 50) -> List[Dict]:
    if _engine is None:
        sessions = _read_json(CHAT_SESSIONS_FILE)
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return sessions[:limit]

    with get_session() as session:
        query = session.query(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
        return [_chat_session_to_dict(s) for s in query.all()]


def delete_session(session_id: str) -> bool:
    if _engine is None:
        sessions = _read_json(CHAT_SESSIONS_FILE)
        filtered = [s for s in sessions if s["id"] != session_id]
        if len(filtered) < len(sessions):
            _write_json(CHAT_SESSIONS_FILE, filtered)
            _delete_session_messages_json(session_id)
            _delete_session_facts_json(session_id)
            return True
        return False

    with get_session() as session:
        s = session.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            session.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
            session.query(MemoryFact).filter(MemoryFact.session_id == session_id).delete()
            session.delete(s)
            session.commit()
            return True
        return False


def _delete_session_messages_json(session_id: str):
    messages = _read_json(CHAT_MESSAGES_FILE)
    messages = [m for m in messages if m["session_id"] != session_id]
    _write_json(CHAT_MESSAGES_FILE, messages)


def _delete_session_facts_json(session_id: str):
    facts = _read_json(MEMORY_FACTS_FILE)
    facts = [f for f in facts if f["session_id"] != session_id]
    _write_json(MEMORY_FACTS_FILE, facts)


# ==================== 聊天消息 ====================

def save_message(data: Dict) -> Dict:
    if _engine is None:
        messages = _read_json(CHAT_MESSAGES_FILE)
        msg = {
            "id": len(messages) + 1,
            "session_id": data["session_id"],
            "role": data["role"],
            "content": data["content"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        messages.append(msg)
        _write_json(CHAT_MESSAGES_FILE, messages)
        return msg

    now = datetime.now(timezone.utc)
    msg = ChatMessage(
        session_id=data["session_id"],
        role=data["role"],
        content=data["content"],
        created_at=now,
    )
    with get_session() as session:
        session.add(msg)
        session.commit()
        return _chat_message_to_dict(msg)


def get_messages(session_id: str, limit: int = 50) -> List[Dict]:
    if _engine is None:
        messages = _read_json(CHAT_MESSAGES_FILE)
        messages = [m for m in messages if m["session_id"] == session_id]
        messages.sort(key=lambda x: x.get("created_at", ""))
        return messages[-limit:]

    with get_session() as session:
        query = session.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.asc())
        if limit:
            query = query.limit(limit)
        return [_chat_message_to_dict(m) for m in query.all()]


def get_recent_messages(session_id: str, limit: int = 20) -> List[Dict]:
    if _engine is None:
        messages = _read_json(CHAT_MESSAGES_FILE)
        messages = [m for m in messages if m["session_id"] == session_id]
        messages.sort(key=lambda x: x.get("created_at", ""))
        return messages[-limit:]

    with get_session() as session:
        subq = session.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.desc()).limit(limit).subquery()
        query = session.query(ChatMessage).filter(
            ChatMessage.id.in_(session.query(subq.c.id))
        ).order_by(ChatMessage.created_at.asc())
        return [_chat_message_to_dict(m) for m in query.all()]


def get_message_count(session_id: str) -> int:
    if _engine is None:
        messages = _read_json(CHAT_MESSAGES_FILE)
        return sum(1 for m in messages if m["session_id"] == session_id)

    with get_session() as session:
        return session.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).count()


# ==================== 记忆事实 ====================

def save_fact(data: Dict) -> Dict:
    if _engine is None:
        facts = _read_json(MEMORY_FACTS_FILE)
        for i, f in enumerate(facts):
            if f["session_id"] == data["session_id"] and f["key"] == data["key"]:
                f["value"] = data["value"]
                f["category"] = data.get("category", "general")
                f["created_at"] = datetime.now(timezone.utc).isoformat()
                facts[i] = f
                _write_json(MEMORY_FACTS_FILE, facts)
                return f
        fact = {
            "id": len(facts) + 1,
            "session_id": data["session_id"],
            "key": data["key"],
            "value": data["value"],
            "category": data.get("category", "general"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        facts.append(fact)
        _write_json(MEMORY_FACTS_FILE, facts)
        return fact

    with get_session() as session:
        existing = session.query(MemoryFact).filter(
            MemoryFact.session_id == data["session_id"],
            MemoryFact.key == data["key"],
        ).first()
        if existing:
            existing.value = data["value"]
            existing.category = data.get("category", "general")
            existing.created_at = datetime.now(timezone.utc)
            session.commit()
            return _memory_fact_to_dict(existing)

        fact = MemoryFact(
            session_id=data["session_id"],
            key=data["key"],
            value=data["value"],
            category=data.get("category", "general"),
            created_at=datetime.now(timezone.utc),
        )
        session.add(fact)
        session.commit()
        return _memory_fact_to_dict(fact)


def get_facts(session_id: str) -> List[Dict]:
    if _engine is None:
        facts = _read_json(MEMORY_FACTS_FILE)
        return [f for f in facts if f["session_id"] == session_id]

    with get_session() as session:
        query = session.query(MemoryFact).filter(
            MemoryFact.session_id == session_id
        ).order_by(MemoryFact.created_at.desc())
        return [_memory_fact_to_dict(f) for f in query.all()]


# ==================== 辅助函数 ====================

def _system_to_dict(s: System) -> Dict:
    return {
        "id": s.id,
        "name": s.name,
        "system_type": s.system_type,
        "status": s.status,
        "endpoint": s.endpoint,
        "auth": s.auth,
        "detectors": s.detectors,
        "check_interval_seconds": s.check_interval_seconds,
        "alert_enabled": s.alert_enabled,
        "health_score": s.health_score,
        "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _incident_to_dict(i: Incident) -> Dict:
    return {
        "id": i.id,
        "system_id": i.system_id,
        "system_name": i.system_name or "",
        "severity": i.severity,
        "status": i.status,
        "title": i.title,
        "message": i.message,
        "root_cause": i.root_cause,
        "report": i.report,
        "report_markdown": i.report,
        "anomalies": i.anomalies or [],
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "acknowledged_at": i.acknowledged_at.isoformat() if i.acknowledged_at else None,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
    }


def _history_to_dict(h: CheckHistory) -> Dict:
    return {
        "system_id": h.system_id,
        "detector_name": h.detector_name,
        "metric_name": h.metric_name,
        "metric_value": float(h.metric_value) if h.metric_value is not None else 0,
        "severity": h.severity,
        "checked_at": h.checked_at.isoformat() if h.checked_at else None,
    }


def _chat_session_to_dict(s: ChatSession) -> Dict:
    return {
        "id": s.id,
        "chat_source": s.chat_source,
        "source_id": s.source_id,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _chat_message_to_dict(m: ChatMessage) -> Dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _memory_fact_to_dict(f: MemoryFact) -> Dict:
    return {
        "id": f.id,
        "session_id": f.session_id,
        "key": f.key,
        "value": f.value,
        "category": f.category,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def save_report_md(incident_id: str, report_content: str) -> str:
    """保存故障报告为 Markdown 文件到指定目录"""
    from app.config import config
    import os
    report_dir = config.report_dir
    os.makedirs(report_dir, exist_ok=True)
    filepath = os.path.join(report_dir, f"incident_{incident_id[:8]}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_content)
    logger.info(f"报告已保存: {filepath}")
    return filepath


def cleanup_old_data(days: int = 7):
    """清理 N 天前的数据（JSON模式：check_history.json + 聊天记录 + reports目录）"""
    import os
    from datetime import datetime, timezone, timedelta

    if _engine is None and not _json_mode:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cleaned = 0

    def _clean_json_file(file: Path, time_field: str):
        nonlocal cleaned
        if file.exists():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                before = len(data)
                data = [
                    h for h in data
                    if datetime.fromisoformat(h[time_field]).replace(tzinfo=timezone.utc) > cutoff
                ]
                after = len(data)
                if before > after:
                    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    cleaned += before - after
                    logger.info(f"清理 {file.name}: 删除 {before - after} 条，保留 {after} 条")
            except Exception as e:
                logger.warning(f"清理 {file.name} 失败: {e}")

    # 清理 check_history.json
    if _json_mode:
        _clean_json_file(DATA_DIR / "check_history.json", "checked_at")
        _clean_json_file(CHAT_MESSAGES_FILE, "created_at")
        _clean_json_file(MEMORY_FACTS_FILE, "created_at")
        _clean_json_file(CHAT_SESSIONS_FILE, "updated_at")

    # MySQL 模式：清理 chat_messages
    if _engine is not None:
        try:
            with get_session() as session:
                deleted = session.query(ChatMessage).filter(
                    ChatMessage.created_at < cutoff
                ).delete()
                session.commit()
                if deleted:
                    cleaned += deleted
                    logger.info(f"清理 chat_messages: 删除 {deleted} 条过期记录")
        except Exception as e:
            logger.warning(f"清理 chat_messages 失败: {e}")

        try:
            with get_session() as session:
                deleted = session.query(MemoryFact).filter(
                    MemoryFact.created_at < cutoff
                ).delete()
                session.commit()
                if deleted:
                    cleaned += deleted
                    logger.info(f"清理 memory_facts: 删除 {deleted} 条过期记录")
        except Exception as e:
            logger.warning(f"清理 memory_facts 失败: {e}")

        try:
            with get_session() as session:
                deleted = session.query(ChatSession).filter(
                    ChatSession.updated_at < cutoff
                ).delete()
                session.commit()
                if deleted:
                    cleaned += deleted
                    logger.info(f"清理 chat_sessions: 删除 {deleted} 条过期会话")
        except Exception as e:
            logger.warning(f"清理 chat_sessions 失败: {e}")

    # 清理 reports 目录下超过7天的 .md 文件
    try:
        from app.config import config
        report_dir = Path(config.report_dir)
        if report_dir.exists():
            for f in report_dir.glob("incident_*.md"):
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        f.unlink()
                        cleaned += 1
                except Exception:
                    pass
            if cleaned > 0:
                logger.info(f"清理报告文件: 删除 {cleaned} 个过期文件")
    except Exception as e:
        logger.warning(f"清理报告目录失败: {e}")

    return cleaned


# ==================== 初始化 ====================

def init_database(config):
    """初始化数据库连接"""
    try:
        init_db(config.db_host, config.db_port, config.db_user, config.db_password, config.db_name)
        logger.info("数据库模式: MySQL")
    except Exception as e:
        logger.warning(f"数据库连接失败，回退到 JSON 模式: {e}")
        global _engine, _SessionLocal, _json_mode
        _engine = None
        _SessionLocal = None
        _json_mode = True
        logger.info("数据库模式: JSON (开发模式)")