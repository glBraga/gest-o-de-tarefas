import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref
from sqlalchemy.dialects.postgresql import UUID
from supabase import create_client

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="TaskProd Pro", layout="wide", page_icon="🚀")

# --- 2. CONFIGURAÇÃO SUPABASE ---
if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
    st.error("Configure as chaves SUPABASE_URL e SUPABASE_KEY nos Secrets.")
    st.stop()

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()

# --- 3. CONFIGURAÇÃO BANCO (SQLAlchemy) ---
Base = declarative_base()

@st.cache_resource
def get_engine():
    try:
        db_url = st.secrets["connections"]["postgresql"]["url"]
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True)
    except Exception as e:
        st.error(f"Erro na conexão com o banco: {e}")
        return None

ENGINE = get_engine()
SessionLocal = sessionmaker(bind=ENGINE)

# --- 4. MODELOS ---
class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True))
    tasks = relationship("Task", back_populates="project", cascade="all, delete")

class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    parent_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    title = Column(String, nullable=False)
    status = Column(String, default="Pendente")
    priority = Column(String, default="Média")
    area = Column(String)
    due_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    start_time = Column(DateTime, nullable=True)
    total_seconds = Column(Integer, default=0)
    user_id = Column(UUID(as_uuid=True))
    
    project = relationship("Project", back_populates="tasks")
    subtasks = relationship("Task", backref=backref('parent', remote_side=[id]))

if ENGINE:
    Base.metadata.create_all(ENGINE)

# --- 5. LÓGICA DE LOGIN ---
def login_screen():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🚀 TaskProd Login")
        tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])
        with tab1:
            email = st.text_input("Email", key="l_email")
            password = st.text_input("Senha", type="password", key="l_pass")
            if st.button("Login", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    if res.user:
                        st.session_state.user = res.user
                        st.rerun()
                except Exception as e:
                    st.error("Email ou senha incorretos.")
        with tab2:
            new_email = st.text_input("Novo Email", key="r_email")
            new_pass = st.text_input("Nova Senha", type="password", key="r_pass")
            if st.button("Cadastrar", use_container_width=True):
                try:
                    supabase.auth.sign_up({"email": new_email, "password": new_pass})
                    st.info("Verifique seu email para confirmar!")
                except Exception as e:
                    st.error(f"Erro: {e}")

if 'user' not in st.session_state:
    login_screen()
    st.stop()

# --- 6. INÍCIO DA SESSÃO ÚNICA ---
uid = st.session_state.user.id
s = SessionLocal()

# --- 7. SIDEBAR ---
with st.sidebar:
    user_email = getattr(st.session_state.user, 'email', 'Usuário')
    st.write(f"👤 {user_email}")
    if st.button("Sair"):
        supabase.auth.sign_out()
        del st.session_state.user
        st.rerun()
    st.divider()
    st.subheader("Meus Projetos")
    projects = s.query(Project).filter(Project.user_id == uid).all()
    for p in projects:
        col_p, col_d = st.columns([4, 1])
        if col_p.button(f"📁 {p.name}", key=f"p_{p.id}", use_container_width=True):
            st.session_state.active_project = p.id
        if col_d.button("🗑️", key=f"del_p_{p.id}"):
            s.delete(p)
            s.commit()
            st.rerun()
    with st.popover("➕ Novo Projeto", use_container_width=True):
        new_p_name = st.text_input("Nome")
        if st.button("Criar"):
            s.add(Project(name=new_p_name, user_id=uid))
            s.commit()
            st.rerun()

# --- 8. CONTEÚDO PRINCIPAL ---
if "active_project" in st.session_state:
    p_id = st.session_state.active_project
    project = s.query(Project).filter(Project.id == p_id, Project.user_id == uid).first()
    
    if project:
        st.title(f"Projeto: {project.name}")
        tasks = s.query(Task).filter(Task.project_id == p_id, Task.user_id == uid, Task.parent_id == None).all()
        
        c1, c2 = st.columns(2)
        c1.metric("Tarefas", len(tasks))
        c2.metric("Concluídas", len([t for t in tasks if t.status == "Concluído"]))
        
        with st.expander("➕ Nova Tarefa"):
            with st.form("new_task"):
                t_title = st.text_input("Título")
                t_area = st.selectbox("Área", ["Financeiro", "Operacional", "Vendas", "RH", "TI", "Diretoria"])
                t_priority = st.selectbox("Prioridade", ["Baixa", "Média", "Alta"], index=1)
                t_date = st.date_input("Prazo")
                if st.form_submit_button("Salvar"):
                    if t_title:
                        new_t = Task(title=t_title, area=t_area, priority=t_priority, due_date=datetime.combine(t_date, datetime.min.time()), project_id=p_id, user_id=uid)
                        s.add(new_t)
                        s.commit()
                        st.rerun()

        # --- LISTAGEM DE TAREFAS (AQUI ESTAVA O ERRO) ---
        for t in tasks:
            with st.container(border=True):
                col_t, col_st, col_time, col_a = st.columns([3, 1, 1, 1])
                
                with col_t:
                    st.write(f"**{t.title}**")
                    st.caption(f"📍 {t.area} | 📅 {t.due_date.strftime('%d/%m') if t.due_date else ''}")

                with col_st:
                    status_opts = ["Pendente", "Em Andamento", "Concluído"]
                    curr_idx = status_opts.index(t.status) if t.status in status_opts else 0
                    new_status = st.selectbox("Status", status_opts, index=curr_idx, key=f"st_{t.id}", label_visibility="collapsed")
                    if new_status != t.status:
                        t.status = new_status
                        s.commit()
                        st.rerun()

                with col_time:
                    if t.start_time is None:
                        if st.button("▶️", key=f"play_{t.id}"):
                            t.start_time = datetime.now()
                            s.commit()
                            st.rerun()
                    else:
                        if st.button("⏹️", key=f"stop_{t.id}", type="primary"):
                            diff = (datetime.now() - t.start_time).total_seconds()
                            t.total_seconds += int(diff)
                            t.start_time = None
                            s.commit()
                            st.rerun()
                    st.caption(f"⏱️ {(t.total_seconds or 0) // 60} min")

                with col_a:
                    if st.button("🗑️", key=f"t_del_{t.id}"):
                        s.delete(t)
                        s.commit()
                        st.rerun()
                
                # Subtasks
                subs = s.query(Task).filter(Task.parent_id == t.id).all()
                for sb in subs:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;↳ <small>{sb.title} - {sb.status}</small>", unsafe_with_html=True)
else:
    st.info("Selecione um projeto na barra lateral.")

s.close()