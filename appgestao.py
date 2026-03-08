import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID # Necessário para o user_id do Supabase
import os
from supabase import create_client

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="TaskProd Pro Cloud", layout="wide", page_icon="🚀")

# --- 2. CONFIGURAÇÃO SUPABASE AUTH ---
if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
    st.error("Configure as chaves SUPABASE_URL e SUPABASE_KEY no Streamlit Cloud.")
    st.stop()

supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- 3. CONFIGURAÇÃO DO BANCO (SQLAlchemy) ---
Base = declarative_base()

def get_engine():
    try:
        db_url = st.secrets["connections"]["postgresql"]["url"]
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        if "pgbouncer=true" in db_url:
            db_url = db_url.replace("pgbouncer=true", "").replace("?&", "?").strip("?&")
        return create_engine(db_url, pool_pre_ping=True)
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

ENGINE = get_engine()
SessionLocal = sessionmaker(bind=ENGINE)

def get_session():
    return SessionLocal()

# --- 4. MODELOS (Atualizados com user_id para RLS) ---
class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True)) # Filtro RLS
    tasks = relationship("Task", back_populates="project", cascade="all, delete", foreign_keys="Task.project_id")

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    parent_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    title = Column(String, nullable=False)
    description = Column(String)
    status = Column(String, default="Pendente")
    priority = Column(String, default="Média")
    due_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    notes = Column(String)
    user_id = Column(UUID(as_uuid=True)) # Filtro RLS
    
    project = relationship("Project", back_populates="tasks")
    subtasks = relationship("Task", backref=st.orm.backref('parent', remote_side=[id]))

Base.metadata.create_all(ENGINE)

# --- 5. LÓGICA DE AUTENTICAÇÃO ---
def login_screen():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🚀 TaskProd Login")
        tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])
        with tab1:
            email = st.text_input("Email")
            password = st.text_input("Senha", type="password")
            if st.button("Login", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.rerun()
                except: st.error("Email ou senha incorretos.")
        with tab2:
            new_email = st.text_input("Novo Email")
            new_pass = st.text_input("Nova Senha", type="password")
            if st.button("Cadastrar", use_container_width=True):
                try:
                    supabase.auth.sign_up({"email": new_email, "password": new_pass})
                    st.info("Verifique seu email para confirmar o cadastro!")
                except Exception as e: st.error(f"Erro: {e}")

if 'user' not in st.session_state:
    login_screen()
    st.stop()

# Dados do usuário logado
uid = st.session_state.user.id

# --- 6. FUNÇÕES DE SUPORTE (Filtradas por UID) ---
def complete_task(task_id):
    s = get_session()
    t = s.query(Task).filter(Task.id == task_id, Task.user_id == uid).first()
    if t:
        t.status = "Concluído"
        t.completed_at = datetime.utcnow()
        s.commit()
    s.close()

# --- 7. DASHBOARD E INTERFACE ---
with st.sidebar:
    st.title("⚙️ Painel")
    st.write(f"Usuário: {st.session_state.user.email}")
    if st.button("Sair"):
        supabase.auth.sign_out()
        del st.session_state.user
        st.rerun()
    st.divider()
    
    s = get_session()
    # QUERY FILTRADA POR USER_ID
    projects = s.query(Project).filter(Project.user_id == uid).all()
    
    st.subheader("Projetos")
    for p in projects:
        col_p, col_d = st.columns([4, 1])
        if col_p.button(f"📁 {p.name}", key=f"p_{p.id}", use_container_width=True):
            st.session_state.active_project = p.id
        if col_d.button("🗑️", key=f"del_p_{p.id}"):
            s.delete(p); s.commit(); st.rerun()
            
    with st.popover("➕ Novo Projeto", use_container_width=True):
        new_p = st.text_input("Nome")
        if st.button("Criar"):
            s.add(Project(name=new_p, user_id=uid))
            s.commit(); st.rerun()

# --- 8. CONTEÚDO PRINCIPAL ---
if "active_project" in st.session_state:
    p_id = st.session_state.active_project
    project = s.query(Project).filter(Project.id == p_id, Project.user_id == uid).first()
    
    if project:
        st.title(f"Projeto: {project.name}")
        
        # --- MÉTRICAS ---
        tasks = s.query(Task).filter(Task.project_id == p_id, Task.user_id == uid, Task.parent_id == None).all()
        total = len(tasks)
        done = len([t for t in tasks if t.status == "Concluído"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", total)
        c2.metric("Concluídas", done)
        c3.metric("Progresso", f"{(done/total*100 if total>0 else 0):.0f}%")
        
        # --- NOVA TAREFA ---
        with st.expander("➕ Adicionar Nova Tarefa Principal"):
            with st.form("f_task"):
                t_title = st.text_input("O que precisa ser feito?")
                t_priority = st.selectbox("Prioridade", ["Baixa", "Média", "Alta"])
                t_date = st.date_input("Prazo", datetime.now() + timedelta(days=1))
                if st.form_submit_button("Salvar Tarefa"):
                    s.add(Task(title=t_title, priority=t_priority, due_date=t_date, project_id=p_id, user_id=uid))
                    s.commit(); st.rerun()
        
        # --- LISTAGEM DE TAREFAS ---
        for t in tasks:
            with st.container(border=True):
                c_check, c_content, c_actions = st.columns([0.5, 4, 1.5])
                
                if t.status == "Concluído":
                    c_content.write(f"~~{t.title}~~ (Prioridade: {t.priority})")
                else:
                    c_content.write(f"**{t.title}** (Prioridade: {t.priority})")
                    c_content.caption(f"📅 Prazo: {t.due_date.strftime('%d/%m/%Y')}")

                with c_actions:
                    col_b1, col_b2 = st.columns(2)
                    if t.status != "Concluído":
                        if col_b1.button("✅", key=f"ok_{t.id}"):
                            complete_task(t.id); st.rerun()
                    if col_b2.button("🗑️", key=f"del_{t.id}"):
                        s.delete(t); s.commit(); st.rerun()
                
                # --- SUBTASKS ---
                subs = s.query(Task).filter(Task.parent_id == t.id, Task.user_id == uid).all()
                for sb in subs:
                    st.write(f"   ↳ {'~~' if sb.status == 'Concluído' else ''}{sb.title}{'~~' if sb.status == 'Concluído' else ''}")
                
                if st.button("➕ Subtask", key=f"add_sub_{t.id}"):
                    st.session_state[f"show_sub_{t.id}"] = True
                
                if st.session_state.get(f"show_sub_{t.id}"):
                    with st.form(f"form_sub_{t.id}"):
                        sub_title = st.text_input("Nome da Subtask")
                        if st.form_submit_button("Adicionar"):
                            s.add(Task(title=sub_title, parent_id=t.id, project_id=p_id, user_id=uid))
                            s.commit(); st.rerun()
else:
    st.info("Selecione um projeto na barra lateral para começar.")

s.close()