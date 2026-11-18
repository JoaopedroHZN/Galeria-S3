import io
import os
from datetime import datetime
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from flask import (
    Flask,
    flash,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from setup_localstack import (
    BUCKET_ORIGEM,
    BUCKET_PROCESSADAS,
    ENDPOINT_URL,
    LAMBDA_NAME,
    REGION,
    TABELA_USUARIOS,
    inicializar_infraestrutura,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "chave-secreta-localstack-cn-2026")

# Cliente S3 (Atividades #1 e #3) apontando para o LocalStack
s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name=REGION,
)

# Recurso DynamoDB (Atividade #2) apontando para o LocalStack
dynamodb = boto3.resource(
    "dynamodb",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name=REGION,
)

AUTH_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Autenticação DynamoDB - LocalStack</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f0f4f8; color: #1e293b; }
        .header-banner { background: linear-gradient(135deg, #0f172a, #1e3a8a); color: #fff; padding: 24px; border-radius: 10px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
        .header-banner h1 { margin: 0 0 6px 0; font-size: 24px; }
        .header-banner p { margin: 0; opacity: 0.85; font-size: 14px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
        .card { background: #fff; padding: 24px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 24px; }
        h2 { margin-top: 0; font-size: 19px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
        label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #475569; }
        input[type="text"], input[type="password"] { width: 100%; padding: 10px 12px; margin-bottom: 16px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; }
        button { width: 100%; background: #0066cc; color: #fff; border: none; padding: 11px 16px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
        button:hover { background: #0052a3; }
        button.btn-green { background: #059669; }
        button.btn-green:hover { background: #047857; }
        .alert { padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; font-size: 14px; font-weight: 500; }
        .alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
        .alert-success { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
        .badge { display: inline-block; background: #dbeafe; color: #1e40af; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e2e8f0; }
        th { background: #f8fafc; color: #475569; }
    </style>
</head>
<body>
    <div class="header-banner">
        <h1>Computação em Nuvem — Plataforma AWS LocalStack</h1>
        <p>Atividade #2: Criação de Contas e Autenticação de Usuários com <strong>Amazon DynamoDB</strong> (Tabela: <code>{{ tabela }}</code>)</p>
        <p style="margin-top:6px; font-size:12px;">Alunos: João Pedro Montelo Menezes, Lucas Jardim e Luiz Cabral</p>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, msg in messages %}
                <div class="alert alert-{{ category }}">{{ msg }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <div class="grid">
        <div class="card">
            <h2>Entrar na Conta (Login)</h2>
            <form action="/login" method="post">
                <label for="login_user">Usuário (Partition Key no DynamoDB)</label>
                <input type="text" id="login_user" name="username" placeholder="Ex.: joaopedro" required>

                <label for="login_pass">Senha</label>
                <input type="password" id="login_pass" name="password" placeholder="Digite sua senha" required>

                <button type="submit">Autenticar via DynamoDB</button>
            </form>
        </div>

        <div class="card">
            <h2>Criar Nova Conta (Cadastro)</h2>
            <form action="/cadastro" method="post">
                <label for="cad_nome">Nome Completo</label>
                <input type="text" id="cad_nome" name="nome" placeholder="Ex.: João Pedro Montelo" required>

                <label for="cad_user">Nome de Usuário (username)</label>
                <input type="text" id="cad_user" name="username" placeholder="Ex.: joaopedro" required>

                <label for="cad_pass">Senha</label>
                <input type="password" id="cad_pass" name="password" placeholder="Crie uma senha" required>

                <button type="submit" class="btn-green">Salvar Usuário no DynamoDB</button>
            </form>
        </div>
    </div>

    <div class="card">
        <h2>Usuários Cadastrados no DynamoDB (<span class="badge">Tabela: {{ tabela }}</span>)</h2>
        {% if usuarios %}
        <table>
            <thead>
                <tr>
                    <th>Username (PK)</th>
                    <th>Nome</th>
                    <th>Criado em</th>
                    <th>Hash de Senha (Werkzeug/PBKDF2)</th>
                </tr>
            </thead>
            <tbody>
                {% for u in usuarios %}
                <tr>
                    <td><strong>{{ u.username }}</strong></td>
                    <td>{{ u.nome }}</td>
                    <td>{{ u.criado_em }}</td>
                    <td><code>{{ u.password_hash[:28] }}...</code></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color:#64748b; font-size:14px;">Nenhum usuário cadastrado ainda na tabela <code>{{ tabela }}</code>. Crie uma conta acima para testar!</p>
        {% endif %}
    </div>
</body>
</html>
"""

GALERIA_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Galeria S3 + DynamoDB + Lambda - LocalStack</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 980px; margin: 32px auto; padding: 0 20px; background: #f0f4f8; color: #1e293b; }
        .topbar { background: linear-gradient(135deg, #0f172a, #1e3a8a); color: #fff; padding: 20px 24px; border-radius: 10px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
        .topbar h1 { margin: 0 0 4px 0; font-size: 21px; }
        .topbar p { margin: 0; font-size: 13px; opacity: 0.85; }
        .user-box { display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.12); padding: 8px 14px; border-radius: 8px; font-size: 13px; }
        .card { background: #fff; padding: 22px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 24px; }
        h2 { margin-top: 0; font-size: 18px; color: #0f172a; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
        button, .btn { background: #0066cc; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; text-decoration: none; cursor: pointer; display: inline-block; font-size: 13px; font-weight: 600; }
        button:hover, .btn:hover { background: #0052a3; }
        .btn-outline { background: #e2e8f0; color: #1e293b; }
        .btn-outline:hover { background: #cbd5e1; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-danger:hover { background: #dc2626; }
        .btn-purple { background: #7c3aed; color: #fff; }
        .btn-purple:hover { background: #6d28d9; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
        .badge-s3 { background: #dcfce7; color: #166534; }
        .badge-lambda { background: #f3e8ff; color: #6b21a8; }
        .alert { padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; font-size: 14px; font-weight: 500; }
        .alert-success { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
        .alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; }
        th { background: #f8fafc; color: #475569; font-size: 13px; }
        img.preview { width: 68px; height: 68px; object-fit: cover; border-radius: 6px; border: 1px solid #cbd5e1; background: #f8fafc; }
        .upload-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
        input[type="file"] { padding: 8px; border: 1px dashed #94a3b8; border-radius: 6px; background: #f8fafc; flex: 1; }
        .meta-tag { display: inline-block; background: #f1f5f9; color: #334155; padding: 2px 7px; border-radius: 4px; font-size: 11px; margin-right: 4px; margin-top: 3px; font-family: monospace; }
    </style>
</head>
<body>
    <div class="topbar">
        <div>
            <h1>Galeria S3 + DynamoDB + Lambda (LocalStack)</h1>
            <p>Alunos: João Pedro Montelo Menezes, Lucas Jardim e Luiz Cabral</p>
        </div>
        <div class="user-box">
            <span>Autenticado via <strong>DynamoDB</strong> como: <strong>{{ usuario.nome }}</strong> (<code>@{{ usuario.username }}</code>)</span>
            <a class="btn btn-danger" href="/logout">Sair</a>
        </div>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, msg in messages %}
                <div class="alert alert-{{ category }}">{{ msg }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <div class="card">
        <h2>
            <span>Atividade #1: Upload de Imagens para o Amazon S3</span>
            <span class="badge badge-s3">Bucket: {{ bucket_origem }}</span>
        </h2>
        <p style="margin: 0 0 10px 0; font-size: 13px; color: #475569;">
            Ao enviar uma imagem para o bucket <code>{{ bucket_origem }}</code>, o S3 dispara automaticamente um evento <code>s3:ObjectCreated:*</code> que aciona a função Serverless <strong>AWS Lambda (<code>{{ lambda_name }}</code>)</strong>.
        </p>
        <form action="/upload" method="post" enctype="multipart/form-data" class="upload-row">
            <input type="file" name="arquivo" accept="image/*" required>
            <button type="submit">Enviar para o S3 e Acionar Lambda</button>
            <a class="btn btn-outline" href="/">Atualizar Listas</a>
        </form>
    </div>

    <div class="card">
        <h2>
            <span>Arquivos Originais no Bucket S3: <code>{{ bucket_origem }}</code></span>
            <span class="badge badge-s3">{{ arquivos_origem|length }} arquivo(s)</span>
        </h2>
        {% if arquivos_origem %}
        <table>
            <thead>
                <tr>
                    <th>Prévia</th>
                    <th>Nome do Arquivo (Key)</th>
                    <th>Tamanho</th>
                    <th>Última Modificação</th>
                    <th>Ação</th>
                </tr>
            </thead>
            <tbody>
                {% for arq in arquivos_origem %}
                <tr>
                    <td><img class="preview" src="/view/origem/{{ arq.Key }}" alt="preview"></td>
                    <td><strong>{{ arq.Key }}</strong></td>
                    <td>{{ (arq.Size / 1024)|round(1) }} KB</td>
                    <td>{{ arq.LastModified.strftime('%d/%m/%Y %H:%M:%S') if arq.LastModified else '-' }}</td>
                    <td><a class="btn" href="/download/origem/{{ arq.Key }}">Download Original</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color:#64748b;">Nenhuma imagem encontrada no bucket de origem <code>{{ bucket_origem }}</code>.</p>
        {% endif %}
    </div>

    <div class="card">
        <h2>
            <span>Atividade #3: Imagens Processadas pela AWS Lambda (Bucket: <code>{{ bucket_processadas }}</code>)</span>
            <span class="badge badge-lambda">Função: {{ lambda_name }}</span>
        </h2>
        <p style="margin: 0 0 10px 0; font-size: 13px; color: #475569;">
            A função Lambda recebe o evento do S3, baixa a imagem original, aplica <strong>Escala de Cinza (Grayscale) + Autocontraste + Moldura Azul</strong> via Pillow e grava o resultado no segundo bucket <code>{{ bucket_processadas }}</code>.
        </p>
        {% if arquivos_processados %}
        <table>
            <thead>
                <tr>
                    <th>Prévia Processada</th>
                    <th>Arquivo Gerado & Metadados da Lambda</th>
                    <th>Tamanho</th>
                    <th>Ação</th>
                </tr>
            </thead>
            <tbody>
                {% for arq in arquivos_processados %}
                <tr>
                    <td><img class="preview" src="/view/processadas/{{ arq.Key }}" alt="preview processada"></td>
                    <td>
                        <strong>{{ arq.Key }}</strong><br>
                        {% if arq.Metadata %}
                            {% for k, v in arq.Metadata.items() %}
                                <span class="meta-tag">{{ k }}: {{ v }}</span>
                            {% endfor %}
                        {% endif %}
                    </td>
                    <td>{{ (arq.Size / 1024)|round(1) }} KB</td>
                    <td><a class="btn btn-purple" href="/download/processadas/{{ arq.Key }}">Download Processada</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color:#64748b;">Nenhuma imagem processada encontrada no bucket <code>{{ bucket_processadas }}</code> ainda. Faça upload de uma imagem acima (e clique em "Atualizar Listas" após 1-2 segundos).</p>
        {% endif %}
    </div>
</body>
</html>
"""


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def listar_usuarios_dynamodb():
    try:
        tabela = dynamodb.Table(TABELA_USUARIOS)
        resp = tabela.scan()
        return resp.get("Items", [])
    except Exception:
        return []


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        tabela = dynamodb.Table(TABELA_USUARIOS)
        resp = tabela.get_item(Key={"username": username})
        item = resp.get("Item")

        if item and check_password_hash(item["password_hash"], password):
            session["usuario"] = {
                "username": item["username"],
                "nome": item.get("nome", item["username"]),
            }
            flash(f"Bem-vindo(a), {item.get('nome', username)}! Autenticação realizada no DynamoDB.", "success")
            return redirect(url_for("index"))
        else:
            flash("Usuário ou senha inválidos no DynamoDB.", "error")

    usuarios = listar_usuarios_dynamodb()
    return render_template_string(AUTH_HTML, tabela=TABELA_USUARIOS, usuarios=usuarios)


@app.route("/cadastro", methods=["POST"])
def cadastro():
    nome = request.form.get("nome", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")

    if not nome or not username or not password:
        flash("Preencha todos os campos para criar a conta.", "error")
        return redirect(url_for("login"))

    tabela = dynamodb.Table(TABELA_USUARIOS)
    existente = tabela.get_item(Key={"username": username}).get("Item")
    if existente:
        flash(f"O usuário '{username}' já está cadastrado no DynamoDB!", "error")
        return redirect(url_for("login"))

    novo_usuario = {
        "username": username,
        "nome": nome,
        "password_hash": generate_password_hash(password),
        "criado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    tabela.put_item(Item=novo_usuario)
    flash(f"Conta '{username}' criada com sucesso no DynamoDB! Faça login ao lado.", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com sucesso.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    resp_origem = s3.list_objects_v2(Bucket=BUCKET_ORIGEM)
    arquivos_origem = resp_origem.get("Contents", [])

    resp_proc = s3.list_objects_v2(Bucket=BUCKET_PROCESSADAS)
    arquivos_processados = resp_proc.get("Contents", [])
    for arq in arquivos_processados:
        try:
            head = s3.head_object(Bucket=BUCKET_PROCESSADAS, Key=arq["Key"])
            arq["Metadata"] = head.get("Metadata", {})
        except ClientError:
            arq["Metadata"] = {}

    return render_template_string(
        GALERIA_HTML,
        usuario=session["usuario"],
        bucket_origem=BUCKET_ORIGEM,
        bucket_processadas=BUCKET_PROCESSADAS,
        lambda_name=LAMBDA_NAME,
        arquivos_origem=arquivos_origem,
        arquivos_processados=arquivos_processados,
    )


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    arquivo = request.files.get("arquivo")
    if arquivo and arquivo.filename:
        s3.upload_fileobj(
            arquivo,
            BUCKET_ORIGEM,
            arquivo.filename,
            ExtraArgs={
                "Metadata": {
                    "enviado-por": session["usuario"]["username"],
                }
            },
        )
        flash(
            f"Imagem '{arquivo.filename}' enviada ao bucket '{BUCKET_ORIGEM}'! "
            f"O gatilho S3 acionou a função Lambda '{LAMBDA_NAME}'.",
            "success",
        )
    return redirect(url_for("index"))


@app.route("/view/<bucket_tipo>/<path:filename>")
@login_required
def view_file(bucket_tipo, filename):
    bucket = BUCKET_PROCESSADAS if bucket_tipo == "processadas" else BUCKET_ORIGEM
    obj = s3.get_object(Bucket=bucket, Key=filename)
    return send_file(io.BytesIO(obj["Body"].read()), download_name=filename, as_attachment=False)


@app.route("/download/<bucket_tipo>/<path:filename>")
@login_required
def download_file(bucket_tipo, filename):
    bucket = BUCKET_PROCESSADAS if bucket_tipo == "processadas" else BUCKET_ORIGEM
    obj = s3.get_object(Bucket=bucket, Key=filename)
    return send_file(io.BytesIO(obj["Body"].read()), download_name=filename, as_attachment=True)


if __name__ == "__main__":
    inicializar_infraestrutura()
    app.run(host="0.0.0.0", port=5000, debug=True)
