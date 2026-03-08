import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="TaskProd Pro v6", layout="wide", page_icon="🚀")
Base = declarative_base()
ENGINE = create_engine('sqlite:///taskprod_v6.db')
SessionLocal = sessionmaker(bind=ENGINE)

# --- MODELOS ---
class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    tasks = relationship("Task", back_populates="project", cascade="all, delete")

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    area = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    status = Column(String, default="Pendente")
    project_id = Column(Integer, ForeignKey('projects.id'))
    parent_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    is_running = Column(Boolean, default=False)
    last_start_time = Column(DateTime, nullable=True)
    total_seconds = Column(Float, default=0.0)
    project = relationship("Project", back_populates="tasks")

Base.metadata.create_all(ENGINE)

# Migração de banco para garantir colunas novas
def upgrade_db():
    with ENGINE.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()]
        for col in [('area', 'TEXT'), ('notes', 'TEXT'), ('created_at', 'DATETIME')]:
            if col[0] not in columns:
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col[0]} {col[1]}"))
        conn.commit()
upgrade_db()

def get_session(): return SessionLocal()

def toggle_timer(task_id):
    session = get_session()
    task = session.query(Task).get(task_id)
    if task.is_running:
        diff = (datetime.now() - task.last_start_time).total_seconds()
        task.total_seconds += diff
        task.is_running = False
    else:
        task.last_start_time = datetime.now()
        task.is_running = True
        task.status = "Fazendo"
    session.commit(); session.close()

def complete_task(task_id):
    session = get_session()
    task = session.query(Task).get(task_id)
    if task.is_running:
        diff = (datetime.now() - task.last_start_time).total_seconds()
        task.total_seconds += diff
        task.is_running = False
    task.status = "Concluído"
    session.commit(); session.close()

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))

# --- CARREGAMENTO INICIAL ---
session = get_session()
all_projects = session.query(Project).all()
proj_map = {p.name: p.id for p in all_projects}
all_tasks_df = pd.read_sql(session.query(Task).statement, ENGINE)
session.close()

# --- SIDEBAR (MENU DE PROJETOS) ---
with st.sidebar:
    st.title("🎯 TaskProd v6")
    
    # Seção para Criar Projetos
    with st.expander("🆕 Novo Projeto", expanded=False):
        new_p = st.text_input("Nome do Projeto")
        if st.button("Criar"):
            if new_p:
                s = get_session(); s.add(Project(name=new_p)); s.commit(); s.close()
                st.rerun()

    st.divider()
    st.subheader("📁 Meus Projetos")
    
    # Filtro de Projetos (Lista na Sidebar)
    # Usamos session_state para persistir qual projeto está selecionado
    if 'selected_proj_id' not in st.session_state:
        st.session_state.selected_proj_id = "Todos"

    if st.button("📂 Mostrar Todos", use_container_width=True, 
                 type="primary" if st.session_state.selected_proj_id == "Todos" else "secondary"):
        st.session_state.selected_proj_id = "Todos"
        st.rerun()

    for p in all_projects:
        is_selected = st.session_state.selected_proj_id == p.id
        if st.button(f"📄 {p.name}", key=f"side_proj_{p.id}", use_container_width=True,
                     type="primary" if is_selected else "secondary"):
            st.session_state.selected_proj_id = p.id
            st.rerun()

    st.divider()
    show_finished = st.checkbox("Mostrar concluídas", value=True)

# --- CORPO PRINCIPAL ---
tab_dash, tab_board = st.tabs(["📊 Dashboard Geral", "📋 Lista de Tarefas"])

# TAB DASHBOARD
with tab_dash:
    if not all_tasks_df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Tarefas", len(all_tasks_df))
        c2.metric("Concluídas", len(all_tasks_df[all_tasks_df.status == "Concluído"]))
        total_h = all_tasks_df['total_seconds'].sum() / 3600
        c3.metric("Tempo Investido", f"{total_h:.1f}h")
        
        fig = px.pie(all_tasks_df, names='status', title="Status das Tarefas", hole=.4,
                     color='status', color_discrete_map={'Pendente':'#94a3b8', 'Fazendo':'#3b82f6', 'Concluído':'#10b981'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhuma tarefa cadastrada ainda.")

# TAB TAREFAS
with tab_board:
    # Form de Criação
    with st.expander("➕ Adicionar Nova Tarefa Principal", expanded=False):
        with st.form("f_new"):
            t_name = st.text_input("Título da Tarefa")
            col_a, col_b = st.columns(2)
            t_area = col_a.selectbox("Área Solicitante", ["TI", "RH", "Financeiro", "Comercial", "Operacional", "Diretoria"])
            # Define o projeto padrão no selectbox baseado na sidebar
            default_proj_idx = 0
            if st.session_state.selected_proj_id != "Todos":
                proj_names = list(proj_map.keys())
                proj_ids = list(proj_map.values())
                if st.session_state.selected_proj_id in proj_ids:
                    default_proj_idx = proj_ids.index(st.session_state.selected_proj_id)

            t_proj = col_b.selectbox("Projeto", list(proj_map.keys()), index=default_proj_idx)
            t_notes = st.text_area("Observações / Detalhes")
            if st.form_submit_button("Criar Tarefa"):
                if t_name:
                    s = get_session()
                    s.add(Task(title=t_name, area=t_area, project_id=proj_map[t_proj], notes=t_notes))
                    s.commit(); s.close()
                    st.rerun()

    # Lógica de Filtragem de Projetos para Exibição
    display_projects = all_projects
    if st.session_state.selected_proj_id != "Todos":
        display_projects = [p for p in all_projects if p.id == st.session_state.selected_proj_id]

    # Renderização dos Projetos
    for p in display_projects:
        st.markdown(f"## 📁 {p.name}")
        s = get_session()
        tasks = s.query(Task).filter(Task.project_id == p.id, Task.parent_id == None).all()
        
        if not tasks:
            st.caption("Nenhuma tarefa neste projeto.")
            
        for t in tasks:
            if not show_finished and t.status == "Concluído": continue
            
            with st.container(border=True):
                c_timer, c_info, c_actions = st.columns([1.5, 5, 2])
                
                with c_timer:
                    curr = t.total_seconds
                    if t.is_running: curr += (datetime.now() - t.last_start_time).total_seconds()
                    st.code(format_time(curr))
                    if st.button("▶️/⏸️", key=f"p_{t.id}"): toggle_timer(t.id); st.rerun()

                with c_info:
                    status_icon = "🟢" if t.status == "Concluído" else "🟡" if t.status == "Fazendo" else "⚪"
                    st.markdown(f"### {status_icon} {t.title}")
                    data_str = t.created_at.strftime('%d/%m %H:%M') if t.created_at else "---"
                    st.markdown(f"**Criação:** {data_str} | **Área:** {t.area}")
                    if t.notes: st.info(f"📝 {t.notes}")
                    
                    # Subtasks com Botão OK
                    subs = s.query(Task).filter(Task.parent_id == t.id).all()
                    for sb in subs:
                        sc1, sc2, sc3 = st.columns([0.3, 4, 1])
                        sc1.write("↳")
                        txt = f"~~{sb.title}~~" if sb.status == "Concluído" else sb.title
                        sc2.write(txt)
                        if sb.status != "Concluído":
                            if sc3.button("OK", key=f"ok_{sb.id}"): complete_task(sb.id); st.rerun()

                with c_actions:
                    if t.status != "Concluído":
                        if st.button("Concluir ✅", key=f"done_{t.id}", use_container_width=True):
                            complete_task(t.id); st.rerun()
                    if st.button("➕ Subtask", key=f"add_s_{t.id}", use_container_width=True):
                        st.session_state[f"sub_f_{t.id}"] = True
                    if st.button("🗑️ Deletar", key=f"del_{t.id}", use_container_width=True):
                        s.delete(t); s.commit(); st.rerun()

                # Form Subtask
                if st.session_state.get(f"sub_f_{t.id}"):
                    with st.form(f"f_s_{t.id}"):
                        sub_n = st.text_input("Nome da Subtarefa")
                        if st.form_submit_button("Adicionar"):
                            s_s = get_session()
                            s_s.add(Task(title=sub_n, project_id=p.id, parent_id=t.id))
                            s_s.commit(); s_s.close()
                            st.session_state[f"sub_f_{t.id}"] = False
                            st.rerun()
        s.close()
        st.divider()