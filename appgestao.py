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
        tab_tasks, tab_dash = st.tabs(["📝 Minhas Tarefas", "📊 Dashboard de Performance"])
        
        with tab_tasks:
            # TELA DE DETALHES (Só aparece se houver uma tarefa selecionada)
            if "detail_view" in st.session_state:
                task_detail = s.query(Task).get(st.session_state.detail_view)
                
                if task_detail:
                    if st.button("⬅️ Voltar para a Lista"):
                        del st.session_state.detail_view
                        st.rerun()

                    st.divider()
                    st.header(f"🔍 Detalhes: {task_detail.title}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(f"**Área:** {task_detail.area}")
                        status_icon = "⚪" if task_detail.status == "Pendente" else "🟡" if task_detail.status == "Em Andamento" else "🟢"
                        st.write(f"**Status Atual:** {status_icon} {task_detail.status}")
                        
                        # Cronômetro nos detalhes
                        if task_detail.start_time:
                            st.warning("⏳ Cronômetro em execução...")
                        
                        if st.button("✅ Concluir Tarefa", use_container_width=True, type="primary"):
                            task_detail.status = "Concluído"
                            task_detail.start_time = None # Para o tempo se estiver rodando
                            s.commit()
                            st.rerun()
                    
                    with col2:
                        # Campo de Observação Rico (armazenando no campo priority conforme seu código)
                        new_obs = st.text_area("📝 Observações/Notas", value=task_detail.priority if task_detail.priority else "", height=150)
                        if st.button("Salvar Observações"):
                            task_detail.priority = new_obs
                            s.commit()
                            st.success("Observação salva!")

                    # --- SEÇÃO DE SUBTASKS ---
                    st.subheader("📌 Subtarefas")
                    with st.expander("➕ Adicionar Subtask"):
                        sub_t = st.text_input("Título da Subtarefa")
                        if st.button("Criar"):
                            s.add(Task(title=sub_t, parent_id=task_detail.id, project_id=p_id, user_id=uid, status="Pendente"))
                            s.commit()
                            st.rerun()
                    
                    subs = s.query(Task).filter(Task.parent_id == task_detail.id).all()
                    for sb in subs:
                        c1, c2 = st.columns([0.1, 0.9])
                        is_ok = c1.checkbox("", value=(sb.status == "Concluído"), key=f"det_sub_{sb.id}")
                        c2.write(sb.title)
                        if is_ok != (sb.status == "Concluído"):
                            sb.status = "Concluído" if is_ok else "Pendente"
                            s.commit()
                            st.rerun()
                else:
                    del st.session_state.detail_view
                    st.rerun()

            else:
                # TELA DE LISTAGEM (GRID)
                st.title(f"Projeto: {project.name}")
                tasks = s.query(Task).filter(Task.project_id == p_id, Task.user_id == uid, Task.parent_id == None).all()
                
                if tasks:
                    df_display = pd.DataFrame([{
                        "ID": t.id,
                        "Tarefa": t.title,
                        "Status": t.status,
                        "Área": t.area,
                        "Prazo": t.due_date.strftime('%d/%m/%Y') if t.due_date else "-"
                    } for t in tasks])

                    st.info("💡 Clique em uma linha para ver Detalhes, Observações e Subtasks.")
                    
                    # Grid Interativo
                    event = st.dataframe(
                        df_display, 
                        use_container_width=True, 
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row"
                    )

                    if len(event.selection.rows) > 0:
                        selected_row = event.selection.rows[0]
                        st.session_state.detail_view = int(df_display.iloc[selected_row]["ID"])
                        st.rerun()
                else:
                    st.write("Crie sua primeira tarefa abaixo.")

                with st.expander("➕ Nova Tarefa Principal"):
                    with st.form("new_task_main"):
                        t_title = st.text_input("Título")
                        t_area = st.selectbox("Área", ["Financeiro", "Operacional", "Vendas", "RH", "TI", "Diretoria"])
                        t_date = st.date_input("Prazo")
                        if st.form_submit_button("Salvar"):
                            new_t = Task(title=t_title, area=t_area, due_date=datetime.combine(t_date, datetime.min.time()), 
                                         project_id=p_id, user_id=uid, status="Pendente")
                            s.add(new_t)
                            s.commit()
                            st.rerun()

        with tab_dash:
            st.header("Análise por Área")
            if tasks:
                df = pd.DataFrame([{
                    'Área': t.area,
                    'Minutos': (t.total_seconds or 0) / 60,
                    'Status': t.status
                } for t in tasks])
                
                # Gráfico de Barras - Tempo por Área
                area_chart = df.groupby('Área')['Minutos'].sum().reset_index()
                st.subheader("Tempo Gasto por Departamento (min)")
                st.bar_chart(data=area_chart, x='Área', y='Minutos')
                
                # Tabela de Detalhamento
                st.subheader("Detalhamento de Custos/Tempo")
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Sem dados para gerar o dashboard ainda.")
                
                # Subtasks
                subs = s.query(Task).filter(Task.parent_id == t.id).all()
                for sb in subs:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;↳ <small>{sb.title} - {sb.status}</small>", unsafe_with_html=True)
else:
    st.info("Selecione um projeto na barra lateral.")

s.close()