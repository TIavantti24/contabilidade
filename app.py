import os
import json
import secrets
import pandas as pd
from functools import wraps
from datetime import timedelta, datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")
ALLOWED_EXT   = {"xlsx", "xls"}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    SQLALCHEMY_DATABASE_URI=os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "stratws.db")
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
)
db = SQLAlchemy(app)

# ── Models ────────────────────────────────────────────────────────────────────
class User(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80),  unique=True, nullable=False)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    def set_password(self, raw):   self.password = generate_password_hash(raw)
    def check_password(self, raw): return check_password_hash(self.password, raw)

class Indicador(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    plano_gestao     = db.Column(db.Integer)
    sigla_unidade    = db.Column(db.String(100))
    area_resultado   = db.Column(db.String(100))
    tipo             = db.Column(db.String(20))
    status           = db.Column(db.String(20))
    nome             = db.Column(db.String(300))
    unidade_medida   = db.Column(db.String(50))
    melhor           = db.Column(db.String(50))
    frequencia       = db.Column(db.String(50))
    responsavel      = db.Column(db.String(200))
    forma_acumulo    = db.Column(db.String(50))
    ponderacao       = db.Column(db.Float, nullable=True)
    tolerancia_verde = db.Column(db.Float, nullable=True)
    tolerancia_amar  = db.Column(db.Float, nullable=True)
    valores_json     = db.Column(db.Text, default="{}")

class CustoFixo(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    atividade = db.Column(db.String(100))
    descricao = db.Column(db.String(200))
    data      = db.Column(db.String(10))   # "MM/YYYY"
    ano       = db.Column(db.Integer)
    mes       = db.Column(db.Integer)
    realizado = db.Column(db.Float, nullable=True)
    orcado    = db.Column(db.Float, nullable=True)

class ImportLog(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    tipo        = db.Column(db.String(20), default="indicadores")  # indicadores | custo
    filename    = db.Column(db.String(200))
    imported_at = db.Column(db.DateTime, server_default=db.func.now())
    total       = db.Column(db.Integer, default=0)
    imported_by = db.Column(db.String(80))

# ── Auth decorators ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Por favor, faça login para acessar.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = User.query.get(session["user_id"])
        if not user or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated

# ── Helpers ───────────────────────────────────────────────────────────────────
MONTHS = ["JAN","FEV","MAR","ABR","MAI","JUN","JUL","AGO","SET","OUT","NOV","DEZ"]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def _safe_float(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None

def import_excel(path):
    df = pd.read_excel(path, sheet_name="Indicadores")
    df.columns = [c.strip() for c in df.columns]
    required = {"NOME DO INDICADOR", "SIGLA UNIDADE", "ÁREA DE RESULTADO"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes na planilha: {missing}")
    Indicador.query.delete()
    db.session.flush()
    count = 0
    for _, row in df.iterrows():
        valores = {}
        for m in MONTHS:
            rea = row.get(f"REA_{m}")
            met = row.get(f"MET_{m}")
            if pd.notna(rea):
                try:    valores[f"rea_{m.lower()}"] = float(str(rea).replace(".", "").replace(",", "."))
                except: valores[f"rea_{m.lower()}"] = None
            if pd.notna(met):
                try:    valores[f"met_{m.lower()}"] = float(str(met).replace(".", "").replace(",", "."))
                except: valores[f"met_{m.lower()}"] = None
        ind = Indicador(
            plano_gestao     = int(row.get("PLANO DE GESTÃO", 0) or 0),
            sigla_unidade    = str(row.get("SIGLA UNIDADE", "") or ""),
            area_resultado   = str(row.get("ÁREA DE RESULTADO", "") or ""),
            tipo             = str(row.get("SIGLA TIPO ACOMPANHAMENTO", "") or ""),
            status           = str(row.get("Status", "Inativo") or "Inativo"),
            nome             = str(row.get("NOME DO INDICADOR", "") or ""),
            unidade_medida   = str(row.get("UNIDADE DE MEDIDA", "") or ""),
            melhor           = str(row.get("MELHOR", "") or ""),
            frequencia       = str(row.get("FREQUÊNCIA", "Mensal") or "Mensal"),
            responsavel      = str(row.get("RESPONSÁVEL", "") or ""),
            forma_acumulo    = str(row.get("FORMA ACÚMULO", "") or ""),
            ponderacao       = _safe_float(row.get("PONDERAÇÃO")),
            tolerancia_verde = _safe_float(row.get("TOLERÂNCIA VERDE")),
            tolerancia_amar  = _safe_float(row.get("TOLERÂNCIA AMARELO")),
            valores_json     = json.dumps(valores),
        )
        db.session.add(ind)
        count += 1
    db.session.commit()
    return count

def import_custo_fixo(path):
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    required = {"Atividade", "Data", "REALIZADO", "ORÇADO"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {missing}")
    CustoFixo.query.delete()
    db.session.flush()
    count = 0
    for _, row in df.iterrows():
        raw_date = str(row.get("Data", "") or "")
        ano, mes = None, None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw_date.split(" ")[0], fmt)
                ano, mes = dt.year, dt.month
                break
            except Exception:
                pass
        cf = CustoFixo(
            atividade = str(row.get("Atividade", "") or ""),
            descricao = str(row.get("Descrição", "") or ""),
            data      = f"{mes:02d}/{ano}" if ano else raw_date,
            ano       = ano,
            mes       = mes,
            realizado = _safe_float(row.get("REALIZADO")),
            orcado    = _safe_float(row.get("ORÇADO")),
        )
        db.session.add(cf)
        count += 1
    db.session.commit()
    return count

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.permanent = True
            session["user_id"]  = user.id
            session["username"] = user.username
            session["is_admin"] = user.is_admin
            flash(f"Bem-vindo, {user.username}!", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Usuário ou senha inválidos.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    total    = Indicador.query.count()
    ativos   = Indicador.query.filter_by(status="Ativo").count()
    inativos = total - ativos
    unidades = db.session.query(Indicador.sigla_unidade, db.func.count(Indicador.id)).group_by(Indicador.sigla_unidade).all()
    areas    = db.session.query(Indicador.area_resultado, db.func.count(Indicador.id)).group_by(Indicador.area_resultado).all()
    anos     = db.session.query(Indicador.plano_gestao,   db.func.count(Indicador.id)).group_by(Indicador.plano_gestao).all()
    last_import = ImportLog.query.order_by(ImportLog.imported_at.desc()).first()
    return render_template("dashboard.html",
        total=total, ativos=ativos, inativos=inativos,
        unidades=unidades, areas=areas, anos=anos,
        last_import=last_import,
        username=session.get("username"), is_admin=session.get("is_admin"))

@app.route("/indicadores")
@login_required
def indicadores():
    page     = request.args.get("page", 1, type=int)
    q        = request.args.get("q", "").strip()
    unidade  = request.args.get("unidade", "")
    area     = request.args.get("area", "")
    status_f = request.args.get("status", "")
    ano_f    = request.args.get("ano", "", type=str)
    query = Indicador.query
    if q:        query = query.filter(Indicador.nome.ilike(f"%{q}%"))
    if unidade:  query = query.filter_by(sigla_unidade=unidade)
    if area:     query = query.filter_by(area_resultado=area)
    if status_f: query = query.filter_by(status=status_f)
    if ano_f:
        try: query = query.filter_by(plano_gestao=int(ano_f))
        except ValueError: pass
    pag          = query.paginate(page=page, per_page=20, error_out=False)
    all_unidades = [r[0] for r in db.session.query(Indicador.sigla_unidade).distinct().all()]
    all_areas    = [r[0] for r in db.session.query(Indicador.area_resultado).distinct().all()]
    all_anos     = sorted({r[0] for r in db.session.query(Indicador.plano_gestao).distinct().all()})
    return render_template("indicadores.html",
        pag=pag, q=q, unidade=unidade, area=area,
        status_f=status_f, ano_f=ano_f,
        all_unidades=all_unidades, all_areas=all_areas, all_anos=all_anos,
        username=session.get("username"), is_admin=session.get("is_admin"))

@app.route("/indicadores/<int:ind_id>")
@login_required
def indicador_detalhe(ind_id):
    ind = Indicador.query.get_or_404(ind_id)
    valores = json.loads(ind.valores_json or "{}")
    chart_data = {
        "labels":    MONTHS,
        "realizado": [valores.get(f"rea_{m.lower()}") for m in MONTHS],
        "meta":      [valores.get(f"met_{m.lower()}") for m in MONTHS],
    }
    return render_template("detalhe.html", ind=ind, chart_data=chart_data,
        username=session.get("username"), is_admin=session.get("is_admin"))

# ── Custo Fixo ────────────────────────────────────────────────────────────────
@app.route("/custo-fixo")
@login_required
def custo_fixo():
    atividades = [r[0] for r in db.session.query(CustoFixo.atividade).distinct().order_by(CustoFixo.atividade).all()]
    anos       = sorted({r[0] for r in db.session.query(CustoFixo.ano).distinct().all() if r[0]})
    ativ_f     = request.args.get("atividade", "")
    ano_f      = request.args.get("ano", "", type=str)

    query = CustoFixo.query.order_by(CustoFixo.ano, CustoFixo.mes)
    if ativ_f: query = query.filter_by(atividade=ativ_f)
    if ano_f:
        try: query = query.filter_by(ano=int(ano_f))
        except ValueError: pass

    registros = query.all()

    chart = {}
    for r in registros:
        key = r.atividade
        if key not in chart:
            chart[key] = {"labels": [], "realizado": [], "orcado": []}
        chart[key]["labels"].append(r.data)
        chart[key]["realizado"].append(r.realizado)
        chart[key]["orcado"].append(r.orcado)

    total_realizado = sum(r.realizado or 0 for r in registros)
    total_orcado    = sum(r.orcado    or 0 for r in registros)
    variacao        = total_realizado - total_orcado

    return render_template("custo_fixo.html",
        registros=registros,
        atividades=atividades, anos=anos,
        ativ_f=ativ_f, ano_f=ano_f,
        chart_json=json.dumps(chart),
        total_realizado=total_realizado,
        total_orcado=total_orcado,
        variacao=variacao,
        total_registros=len(registros),
        username=session.get("username"),
        is_admin=session.get("is_admin"))

# ── Admin: Users ──────────────────────────────────────────────────────────────
@app.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.all()
    return render_template("admin_users.html", users=users,
        username=session.get("username"), is_admin=True)

@app.route("/admin/users/create", methods=["POST"])
@admin_required
def admin_create_user():
    u = request.form.get("username","").strip()
    e = request.form.get("email","").strip()
    p = request.form.get("password","")
    admin = request.form.get("is_admin") == "on"
    if User.query.filter((User.username==u)|(User.email==e)).first():
        flash("Usuário ou e-mail já existe.", "danger")
    else:
        user = User(username=u, email=e, is_admin=admin)
        user.set_password(p)
        db.session.add(user)
        db.session.commit()
        flash(f"Usuário '{u}' criado.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@admin_required
def admin_delete_user(uid):
    if uid == session["user_id"]:
        flash("Não pode deletar a si mesmo.", "warning")
    else:
        User.query.filter_by(id=uid).delete()
        db.session.commit()
        flash("Usuário removido.", "info")
    return redirect(url_for("admin_users"))

# ── Admin: Import ─────────────────────────────────────────────────────────────
@app.route("/admin/importar", methods=["GET", "POST"])
@admin_required
def admin_importar():
    logs_ind = ImportLog.query.filter_by(tipo="indicadores").order_by(ImportLog.imported_at.desc()).limit(10).all()

    if request.method == "POST":
        file = request.files.get("planilha")
        if not file or file.filename == "":
            flash("Nenhum arquivo selecionado.", "warning")
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash("Formato inválido. Envie .xlsx ou .xls.", "danger")
            return redirect(request.url)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename  = secure_filename(file.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)
        try:
            total = import_excel(save_path)
            db.session.add(ImportLog(tipo="indicadores", filename=filename, total=total, imported_by=session.get("username","?")))
            db.session.commit()
            flash(f"✅ {total} indicadores importados com sucesso!", "success")
        except ValueError as e:
            flash(f"Erro na planilha: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Erro inesperado: {e}", "danger")
        return redirect(url_for("admin_importar"))

    return render_template("admin_importar.html",
        logs_ind=logs_ind,
        total_ind=Indicador.query.count(),
        total_custo=CustoFixo.query.count(),
        username=session.get("username"), is_admin=True)

@app.route("/admin/importar-custo", methods=["POST"])
@admin_required
def admin_importar_custo():
    file = request.files.get("planilha_custo")
    if not file or file.filename == "":
        flash("Nenhum arquivo selecionado.", "warning")
        return redirect(url_for("admin_importar"))
    if not allowed_file(file.filename):
        flash("Formato inválido. Envie .xlsx ou .xls.", "danger")
        return redirect(url_for("admin_importar"))
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename  = secure_filename(file.filename)
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)
    try:
        total = import_custo_fixo(save_path)
        db.session.add(ImportLog(tipo="custo", filename=filename, total=total, imported_by=session.get("username","?")))
        db.session.commit()
        flash(f"✅ {total} registros de Custo Fixo importados!", "success")
    except ValueError as e:
        flash(f"Erro na planilha: {e}", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro inesperado: {e}", "danger")
    return redirect(url_for("admin_importar"))

# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/stats")
@login_required
def api_stats():
    areas = db.session.query(Indicador.area_resultado, db.func.count(Indicador.id)).group_by(Indicador.area_resultado).all()
    return jsonify({a: c for a, c in areas})

# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, msg="Acesso negado."), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Página não encontrada."), 404

@app.errorhandler(413)
def too_large(e):
    flash("Arquivo muito grande. Limite: 20 MB.", "danger")
    return redirect(url_for("admin_importar"))

# ── Init DB ───────────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    db.create_all()
    if User.query.count() == 0:
        admin = User(username="admin", email="admin@cimapra.com.br", is_admin=True)
        admin.set_password(os.environ.get("ADMIN_PASSWORD", "Admin@2024!"))
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin criado: admin / Admin@2024!")
    if Indicador.query.count() == 0:
        excel = os.environ.get("EXCEL_PATH", "/mnt/user-data/uploads/_cimapra__-_Listagens.xlsx")
        if os.path.exists(excel):
            total = import_excel(excel)
            db.session.add(ImportLog(tipo="indicadores", filename=os.path.basename(excel), total=total, imported_by="sistema"))
            db.session.commit()
            print(f"✅ {total} indicadores importados.")
        else:
            print("⚠️  Excel de indicadores não encontrado. Use /admin/importar.")
    if CustoFixo.query.count() == 0:
        custo = os.environ.get("CUSTO_EXCEL_PATH", "/mnt/user-data/uploads/Custo_Fixo.xlsx")
        if os.path.exists(custo):
            total = import_custo_fixo(custo)
            db.session.add(ImportLog(tipo="custo", filename=os.path.basename(custo), total=total, imported_by="sistema"))
            db.session.commit()
            print(f"✅ {total} registros de Custo Fixo importados.")
        else:
            print("⚠️  Custo_Fixo.xlsx não encontrado. Use /admin/importar.")

if __name__ == "__main__":
    with app.app_context():
        init_db()
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug)
